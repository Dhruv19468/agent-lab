# Step 5: run the Test Plan Agent, score it, and deploy to Azure

## What this adds

| Area | Files | What it does |
|---|---|---|
| Agent loop | `app/runtime/agent_runner.py`, `runtime/tools/registry.py`, `runtime/background.py` | Sends the conversation to Azure OpenAI, runs the tools the model asks for, repeats. Runs in the background; the API answers at once and you poll. |
| Runs API | `app/modules/runs/` | `POST /api/agents/{id}/runs`, `GET /api/agents/{id}/runs`, `GET /api/runs/{id}` |
| Datasets API | `app/modules/datasets/`, `runtime/dataset.py` | `GET /api/datasets` lists P00–P09 from `data/raw` |
| Scorer | `app/evaluation/`, `app/modules/evaluations/`, `models/evaluation.py`, migration `e7a41c2b9f10` | `overall = (0.25·structure + 0.45·coverage + 0.30·similarity) × faithfulness`; every LLM judgement must quote text that really exists |
| Catalogue | `app/catalog/` | At startup it creates the 4 built-in tools, the skill **BRD to Test Plan** (prompt v2) and the **Test Plan Agent**, if they're missing |
| Prompts | `app/catalog/prompts/v1_baseline.md`, `v2_structured.md`, `v3_grounded.md` | The prompt versions you compare |
| Experiments | `scripts/run_experiment.py` | Runs a split, scores each plan, writes CSV and a mean ± std summary |
| Tests | `backend/tests/` (54 tests) | Tools, registry, agent loop (fake model), section mapping, scorer, dataset; no DB, no Azure |
| Frontend | `pages/AgentRunsTabs.tsx`, `components/ScoreCard.tsx` | **Run** tab (pick project, run, tool trace, plan, score) and **Scores** tab (per-version means) |
| Azure | `deploy/azure/setup.ps1`, `frontend/nginx/*` | Registry, PostgreSQL, Storage (Azure Files with your data), Container Apps, password-protected site |
| CI/CD | `.github/workflows/ci-cd.yml` | Tests on every push/PR; on `main`, builds images in Azure and rolls out |

`docx_to_text` now also treats short all-bold paragraphs as headings, because the BRDs use bold
"Normal" text, not Word heading styles.

## 1. Merge into your project

Extract the zip **over** `C:\dev\agent-lab` (say yes to replace). Then delete `frontend\nginx.conf`
(it is now `frontend\nginx\default.conf.template`).

No new Python or npm packages are needed.

## 2. Run locally

```powershell
cd C:\dev\agent-lab\backend
uv run pytest -q                       # 54 passed
uv run uvicorn app.main:app --reload --port 8080
```

Startup log should show the migration to `e7a41c2b9f10` and
`Catalog: created and published agent 'Test Plan Agent'`.

```powershell
cd ..\frontend
npm run typecheck
npm run dev                            # http://localhost:3000
```

Open **Agents → Test Plan Agent → Run**, pick **P06**, press **Run agent**. After 1–3 minutes the
plan appears; press **Score this plan** (about a minute).

## 3. Prompt-engineering experiments

Use train/validation while you tune. Keep test (P08, P09) for the final comparison.

```powershell
cd C:\dev\agent-lab\backend
uv run python scripts/run_experiment.py --label v1 --prompt app/catalog/prompts/v1_baseline.md --split validation --repeats 2
uv run python scripts/run_experiment.py --label v2 --prompt app/catalog/prompts/v2_structured.md --split validation --repeats 2
uv run python scripts/run_experiment.py --label v3 --prompt app/catalog/prompts/v3_grounded.md --split validation --repeats 2
```

Each run of the script republishes the agent, so every prompt is a separate version on the
**Scores** tab. Results go to `backend/experiments/<label>-<time>/`.

Cost is roughly 50k tokens per plan plus 30k for scoring on gpt-4.1-mini: cents per run.

## 4. Deploy to Azure (one time)

Needs PowerShell 7 (`winget install Microsoft.PowerShell`) and the Azure CLI (`winget install Microsoft.AzureCLI`).

```powershell
cd C:\dev\agent-lab
az login
.\deploy\azure\setup.ps1 -Location eastus2 -GitHubRepo <your-github-user>/agent-lab
```

It prints the site URL. Log in as `lab` with `sitePassword` from `deploy\azure\secrets.local.json`
(git-ignored; keep it). Approximate monthly cost when idle: PostgreSQL B1ms ≈ $15, Container
Registry Basic ≈ $5, storage cents; the Container Apps scale to zero.

To stop paying: `az group delete -n rg-agent-lab`.

## 5. CI/CD from GitHub

1. Make a **private** repo `agent-lab` on GitHub and push (check `git status` shows no `.env`).
2. Run the `gh secret set` / `gh variable set` lines that `setup.ps1` printed (or add them in the
   repo's Settings → Secrets and variables → Actions).
3. Every push runs the tests; a push to `main` also builds both images in Azure and deploys them.

Experiments against Azure:

```powershell
uv run python scripts/run_experiment.py --base-url https://<web-url> --user lab --password <sitePassword> --label v3-azure
```

## Notes

- The score is relative, not absolute: the same judge model scores every version, so compare
  versions with each other. The reference points are cached in `data/_cache/`, so every version is
  checked against the same list.
- Faithfulness multiplies the rest: a plan that invents a number loses everywhere.
- If `data/gold/<split>/<P>/gold_testplan.json` exists, it is used as the reference; otherwise the
  human `*_TestPlan.docx` is.
