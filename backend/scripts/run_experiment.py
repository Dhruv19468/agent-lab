"""Prompt-engineering experiment: run the Test Plan Agent on several projects, score every plan.

It only talks to the API, so it works the same against your laptop and against Azure:

    # from backend/, with the API running locally
    uv run python scripts/run_experiment.py --label v2 --split validation --repeats 2

    # try another prompt version (updates the skill's instructions and republishes the agent first)
    uv run python scripts/run_experiment.py --label v3 --prompt app/catalog/prompts/v3_grounded.md

    # same prompt, another model (it must be deployed in your Azure OpenAI / Foundry resource)
    uv run python scripts/run_experiment.py --label v3-gpt41 --model gpt-4.1

    # against Azure (the frontend URL; nginx forwards /api to the backend)
    uv run python scripts/run_experiment.py --base-url https://<frontend>.azurecontainerapps.io \
        --user lab --password <password> --label v3-azure

Each experiment writes backend/experiments/<label>-<time>/:
    results.csv   one row per run: scores, tokens, seconds
    plans/        every generated plan as Markdown
    summary.md    mean ± standard deviation per metric (paste it into your notes)

Use train/validation projects while you change prompts. Run the test split (P08, P09) only
for the final comparison, so you don't tune your prompt to the test set.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

METRICS = ["structure", "coverage", "similarity", "faithfulness", "overall"]
POLL_SECONDS = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8080", help="API or frontend URL")
    parser.add_argument("--user", help="basic-auth user (Azure frontend)")
    parser.add_argument("--password", help="basic-auth password (Azure frontend)")
    parser.add_argument("--agent", default="Test Plan Agent")
    parser.add_argument("--skill", default="BRD to Test Plan", help="skill whose instructions --prompt replaces")
    parser.add_argument("--prompt", type=Path, help="Markdown file to use as the skill's instructions")
    parser.add_argument("--model", help="deployment for these runs, e.g. gpt-4.1 (default: the agent's model)")
    parser.add_argument("--split", default="validation", choices=["train", "validation", "test", "all"])
    parser.add_argument("--projects", help="comma-separated, e.g. P06,P07 (overrides --split)")
    parser.add_argument("--repeats", type=int, default=1, help="runs per project (LLMs vary; 2-3 is better)")
    parser.add_argument("--label", default="experiment", help="name for this experiment's folder")
    parser.add_argument("--no-score", action="store_true", help="only generate plans")
    parser.add_argument("--timeout-minutes", type=float, default=15)
    return parser.parse_args()


class Api:
    def __init__(self, base_url: str, user: str | None, password: str | None) -> None:
        auth = (user, password) if user and password else None
        self.client = httpx.Client(base_url=base_url.rstrip("/") + "/api", auth=auth, timeout=60)

    def call(self, method: str, path: str, json: dict | None = None):
        response = self.client.request(method, path, json=json)
        if response.status_code >= 400:
            sys.exit(f"{method} {path} -> {response.status_code}: {response.text[:500]}")
        return response.json() if response.content else None

    def wait(self, path: str, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            item = self.call("GET", path)
            if item["status"] != "running":
                return item
            if time.monotonic() > deadline:
                return {**item, "status": "failed", "error": "timed out waiting (still running on the server)"}
            time.sleep(POLL_SECONDS)


def find_by_name(items: list[dict], name: str, kind: str) -> dict:
    match = next((item for item in items if item["name"] == name), None)
    if match is None:
        sys.exit(f"No {kind} named '{name}'. Start the backend once so the catalog creates it.")
    return match


def summarise(rows: list[dict], label: str, prompt: str) -> str:
    models = sorted({str(row.get("model")) for row in rows})
    lines = [f"# Experiment {label}", "", f"- prompt: {prompt}", f"- model: {', '.join(models)}", f"- runs: {len(rows)}", ""]
    scored = [row for row in rows if row.get("overall") not in (None, "")]
    lines += ["| metric | mean | std | min | max |", "|---|---|---|---|---|"]
    for metric in METRICS:
        values = [float(row[metric]) for row in scored]
        if values:
            std = statistics.stdev(values) if len(values) > 1 else 0.0
            lines.append(
                f"| {metric} | {statistics.mean(values):.3f} | {std:.3f} | {min(values):.3f} | {max(values):.3f} |"
            )
    lines += ["", "| project | run | status | overall | structure | coverage | similarity | faithfulness | s |"]
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        cells = [row["project"], str(row["repeat"]), row["status"]] + [
            f"{float(row[m]):.3f}" if row.get(m) not in (None, "") else "–"
            for m in ["overall", "structure", "coverage", "similarity", "faithfulness"]
        ]
        lines.append("| " + " | ".join(cells + [str(row["seconds"])]) + " |")
    failed = sum(row["status"] != "completed" for row in rows)
    if failed:
        lines += ["", f"{failed} run(s) failed or were not scored; see the error column in results.csv."]
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    api = Api(args.base_url, args.user, args.password)
    agent = find_by_name(api.call("GET", "/agents"), args.agent, "agent")

    prompt_name = "current skill instructions"
    if args.prompt:
        skill = find_by_name(api.call("GET", "/skills"), args.skill, "skill")
        api.call("PUT", f"/skills/{skill['id']}", {"instructions": args.prompt.read_text(encoding="utf-8")})
        agent = api.call("POST", f"/agents/{agent['id']}/publish")
        prompt_name = args.prompt.name
        print(f"Skill '{args.skill}' now uses {args.prompt}; agent published as v{agent['publishedVersion']}.")

    projects = api.call("GET", "/datasets")["projects"]
    if args.projects:
        wanted = {p.strip().upper() for p in args.projects.split(",")}
        projects = [p for p in projects if p["project"] in wanted]
    elif args.split != "all":
        projects = [p for p in projects if p["split"] == args.split]
    if not projects:
        sys.exit("No matching projects. Is data/raw/<split>/Pxx there (locally or on the Azure file share)?")

    folder = Path("experiments") / f"{args.label}-{datetime.now():%Y%m%d-%H%M}"
    (folder / "plans").mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    timeout = args.timeout_minutes * 60

    for project in projects:
        for repeat in range(1, args.repeats + 1):
            started = time.monotonic()
            print(f"{project['project']} run {repeat}/{args.repeats}: generating…", flush=True)
            body = {"message": project["suggestedMessage"], "model": args.model}
            run = api.call("POST", f"/agents/{agent['id']}/runs", body)
            run = api.wait(f"/runs/{run['id']}", timeout)
            row: dict = {
                "project": project["project"],
                "split": project["split"],
                "repeat": repeat,
                "run_id": run["id"],
                "agent_version": run["agentVersion"],
                "model": run["model"],
                "status": run["status"],
                "tool_rounds": run["toolRounds"],
                "prompt_tokens": run["promptTokens"],
                "completion_tokens": run["completionTokens"],
                "error": run.get("error") or "",
            }
            if run.get("answer"):
                plan_file = folder / "plans" / f"{project['project']}_run{repeat}.md"
                plan_file.write_text(run["answer"], encoding="utf-8")

            if run["status"] == "completed" and not args.no_score and project["hasReference"]:
                print(f"{project['project']} run {repeat}: scoring…", flush=True)
                evaluation = api.call("POST", f"/runs/{run['id']}/evaluations", {"project": project["project"]})
                evaluation = api.wait(f"/evaluations/{evaluation['id']}", timeout)
                if evaluation["status"] == "completed":
                    row.update({metric: evaluation[metric] for metric in METRICS})
                    row["judge_tokens"] = evaluation["promptTokens"] + evaluation["completionTokens"]
                else:
                    row["status"] = "score-failed"
                    row["error"] = evaluation.get("error") or "evaluation failed"

            row["seconds"] = round(time.monotonic() - started)
            rows.append(row)
            score = f"overall {row['overall']:.3f}" if row.get("overall") is not None else row["error"][:100]
            print(f"{project['project']} run {repeat}: {row['status']} – {score}", flush=True)

    columns = list(dict.fromkeys(key for row in rows for key in row))
    with (folder / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    summary = summarise(rows, args.label, prompt_name)
    (folder / "summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    print(f"Saved to {folder}")


if __name__ == "__main__":
    main()
