"""Step 3 check: drive the whole API over HTTP, the way the frontend will.

Start the backend first (uvicorn on :8080, or docker compose), then from backend/:
    uv run python scripts/demo_step3.py            # build the demo agent and keep it
    uv run python scripts/demo_step3.py --cleanup  # ...and delete everything it created
"""

from __future__ import annotations

import json
import sys
import uuid

import httpx

BASE = "http://localhost:8080/api"
CLEANUP = "--cleanup" in sys.argv


def call(client: httpx.Client, method: str, path: str, expect: int, body: dict | None = None) -> dict | None:
    response = client.request(method, f"{BASE}{path}", json=body)
    ok = response.status_code == expect
    print(f"  {'OK ' if ok else '!! '} {method:6} {path:45} -> {response.status_code}"
          + ("" if ok else f" (expected {expect}): {response.text}"))
    if not ok:
        sys.exit(1)
    return response.json() if response.content else None


def main() -> None:
    suffix = uuid.uuid4().hex[:6]
    with httpx.Client(timeout=30) as client:
        print("1) Tools")
        read_file = call(client, "POST", "/tools", 201, {
            "name": f"read_file_{suffix}",
            "description": "Read a text file from the project data folder.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path inside data/"}},
                "required": ["path"],
            },
        })
        create_doc = call(client, "POST", "/tools", 201, {
            "name": f"create_document_{suffix}",
            "description": "Save a Markdown document to the agent output folder.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        })
        list_files = call(client, "POST", "/tools", 201, {
            "name": f"list_files_{suffix}",
            "description": "List files in a data folder.",
        })
        call(client, "POST", "/tools", 422, {"name": "bad name", "description": "x"})  # pattern fails

        print("2) Skills")
        skill = call(client, "POST", "/skills", 201, {
            "name": f"BRD to Test Plan {suffix}",
            "description": "Turns a BRD and an architecture description into a test plan.",
            "instructions": "# BRD to Test Plan\n\n1. Read the BRD with read_file.\n2. Write the plan.\n",
            "triggerPhrases": ["test plan", "generate test plan", " Test Plan ", ""],
            "requiredToolIds": [read_file["id"], create_doc["id"]],
        })
        print(f"     trigger phrases cleaned to: {skill['triggerPhrases']}")
        other = call(client, "POST", "/skills", 201, {
            "name": f"Say Hello {suffix}",
            "description": "Greets the user.",
            "instructions": "Answer with a friendly hello.",
            "triggerPhrases": ["say hello"],
        })
        call(client, "POST", "/skills", 409, {"name": skill["name"], "instructions": "dup"})  # same name

        print("3) Agent")
        agent = call(client, "POST", "/agents", 201, {
            "name": f"Test Plan Agent {suffix}",
            "description": "Writes test plans from BRDs.",
            "configuration": {"temperature": 0.2, "maxTokens": 8000},
        })
        agent_id = agent["id"]
        call(client, "POST", f"/agents/{agent_id}/publish", 409)  # no skills yet

        print("4) Attach skills and tools")
        detail = call(client, "POST", f"/agents/{agent_id}/skills", 200, {"skillId": skill["id"]})
        print(f"     tools after attaching the skill: {[(t['name'], t['source']) for t in detail['tools']]}")
        call(client, "POST", f"/agents/{agent_id}/skills", 200, {"skillId": other["id"]})
        call(client, "POST", f"/agents/{agent_id}/tools", 200, {"toolId": list_files["id"]})
        call(client, "DELETE", f"/agents/{agent_id}/tools/{read_file['id']}", 409)  # a skill needs it

        print("5) Publish")
        detail = call(client, "POST", f"/agents/{agent_id}/publish", 200)
        print(f"     status={detail['status']} version={detail['publishedVersion']}")
        print("     published instructions:\n" + "\n".join("       | " + line for line in detail["publishedInstructions"].splitlines()))

        print("6) Preview what the LLM would receive")
        preview = call(client, "POST", f"/agents/{agent_id}/preview-prompt", 200,
                       {"message": "Generate test plan for project P06"})
        print(f"     matched skills: {preview['matchedSkills']}   tools: {preview['tools']}")
        print("     user message:\n" + "\n".join("       | " + line for line in preview["userMessage"].splitlines()))

        print("7) Detach the skill: its tools go, the manual tool stays")
        detail = call(client, "DELETE", f"/agents/{agent_id}/skills/{skill['id']}", 200)
        print(f"     tools now: {[(t['name'], t['source']) for t in detail['tools']]}")

        if CLEANUP:
            print("8) Cleanup")
            call(client, "DELETE", f"/agents/{agent_id}", 204)
            call(client, "DELETE", f"/skills/{skill['id']}", 204)
            call(client, "DELETE", f"/skills/{other['id']}", 204)
            for tool in (read_file, create_doc, list_files):
                call(client, "DELETE", f"/tools/{tool['id']}", 204)
        else:
            print(f"\nKept. Open http://localhost:8080/docs and try GET /api/agents/{agent_id}")
            print(json.dumps({"agentId": agent_id, "skillId": skill["id"]}, indent=2))


if __name__ == "__main__":
    main()
