# Agent Lab

A practice platform for building AI agents from reusable **skills** and **tools**, running them on
real project documents, and **measuring how good their output is**.

The first agent it ships with, the **Test Plan Agent**, reads a project's Business Requirements
Document (BRD) and architecture diagram and writes a master test plan. Each plan is scored
against a human reference plan, so changes to the prompt, the model or (later) retrieval can be
compared with numbers instead of impressions.

**Roadmap:** prompt engineering (now) → retrieval-augmented generation (RAG) → fine-tuning.

---

## Contents

- [What it does](#what-it-does)
- [How it fits together](#how-it-fits-together)
- [Repository layout](#repository-layout)
- [Backend](#backend-backend)
- [The AI part](#the-ai-part)
- [Frontend](#frontend-frontend)
- [Data](#data-data)
- [Deployment and CI/CD](#deployment-and-cicd)
- [Run it locally](#run-it-locally)
- [Configuration](#configuration)
- [Using the app](#using-the-app)
- [Prompt-engineering experiments](#prompt-engineering-experiments)
- [Tests](#tests)
- [Security and data rules](#security-and-data-rules)

---

## What it does

| Capability | Where |
|---|---|
| Define **tools** (functions the model may call) and **skills** (Markdown instructions plus the tools they need) | Tools and Skills pages |
| Build **agents** from skills, tools and model settings; **publish** them as versions | Agents page, Setup tab |
| Register each published version as an agent in **Azure AI Foundry** (optional) | Publish button |
| **Run** an agent on a project: it lists the folder, reads the BRD (.docx), looks at the diagram (.png), writes the plan | Run tab |
| Pick the **model per agent or per run** (gpt-4.1-mini, gpt-5-mini, …) | Setup tab, Run tab |
| Download any plan as **Word, Excel, PDF or Markdown**, laid out like the reference plans | Run tab |
| **Score** a plan: structure, coverage, similarity, faithfulness and an overall score | Run tab, Scores tab |
| Compare **prompt versions and models** across many projects | `backend/scripts/run_experiment.py`, Scores tab |

---

## How it fits together

```mermaid
flowchart LR
    U[Browser] -->|HTTPS| W[frontend<br/>nginx + React]
    W -->|/api| A[backend<br/>FastAPI]
    A --> DB[(PostgreSQL<br/>agents, skills, runs, scores)]
    A --> S[(Data storage<br/>local folder or Azure Blob)]
    A -->|chat + tools| M[Azure OpenAI models<br/>in Foundry]
    A -->|publish / delete agent| F[Azure AI Foundry<br/>project agents]
    GH[GitHub Actions] -->|test, build, deploy| ACR[Container Registry] --> W & A
```

One run, end to end:

```
Run tab ─► POST /api/agents/{id}/runs ─► saves a "running" row, answers at once (202)
                 └─ background: agent loop
                      model ─► list_files ─► read_file (BRD) ─► view_image (diagram) ─► final plan
                 └─ saves answer, tokens, tool trace (+ .docx/.xlsx/.pdf if chosen)
Score ─► POST /api/runs/{id}/evaluations ─► judge model + checks ─► scores saved
```

---

## Repository layout

```
agent-lab/
├── backend/                 FastAPI service: API, database, agent runtime, scoring
│   ├── app/
│   │   ├── core/            settings, errors, shared schema base
│   │   ├── db/              database engine and sessions, migrations runner
│   │   ├── models/          database tables (SQLAlchemy)
│   │   ├── modules/         the API, one folder per area (router + schemas + service)
│   │   ├── integrations/    Azure OpenAI and Azure AI Foundry clients
│   │   ├── runtime/         the agent loop, tools, storage, dataset, document exporters
│   │   ├── evaluation/      the test-plan scorer
│   │   ├── catalog/         built-in tools, skill and agent; prompt versions
│   │   └── main.py          app startup
│   ├── alembic/             database migrations
│   ├── scripts/             experiment runner and manual checks
│   ├── tests/               unit tests (no database or Azure needed)
│   ├── Dockerfile
│   ├── pyproject.toml, uv.lock
│   └── .env.example
├── frontend/                React app served by nginx
│   ├── src/                 pages, components, API client
│   ├── nginx/               nginx config template + optional site password
│   └── Dockerfile
├── data/                    the practice dataset (raw/) and agent outputs
├── deploy/azure/setup.ps1   one-time Azure setup
├── .github/workflows/       CI/CD pipeline
└── docker-compose.yml       Postgres + backend + frontend, locally
```

---

## Backend (`backend/`)

Python 3.12+, **FastAPI**, async **SQLAlchemy** on **PostgreSQL**, **Alembic** migrations, managed with
**uv** (`uv.lock` pins every package, so laptop, CI and Docker install the same versions).

The code is layered: routers handle HTTP only, services hold the rules, models hold the data. Services
raise `NotFoundError` (404), `ConflictError` (409) or `BadRequestError` (400) and `main.py` turns them
into JSON responses.

### `app/core/`

| File | Purpose |
|---|---|
| `config.py` | `Settings`: every environment variable (database, Azure OpenAI, Foundry, storage, data folder). Read once, cached. |
| `errors.py` | The error types services raise. |
| `schemas.py` | `ApiModel`: base for request/response shapes; converts `snake_case` ↔ `camelCase`. |
| `dependencies.py` | `DbSession`: one database session per request. |

### `app/db/`, `app/models/`, `alembic/`

| Table | Holds |
|---|---|
| `agents` | name, status, published instructions and version, Foundry agent name/version |
| `agent_configurations` | model, temperature, max tokens, max tool rounds |
| `skills`, `skill_tools` | skill instructions (Markdown), trigger phrases, required tools |
| `tools` | name, description, JSON Schema parameters |
| `agent_skills`, `agent_tools` | which skills and tools each agent has (`manual` or `skill`) |
| `agent_runs` | prompt, answer, status, tool-call trace, tokens, duration, model, saved file |
| `evaluations` | the four metrics, overall score, and every point, claim and quote behind them |

All tables live in the schema `al`. Migrations run automatically at startup
(`RUN_ALEMBIC_ON_STARTUP=true`); their history is in `alembic/versions/`.

### `app/modules/` (the API)

Each folder has `router.py` (URLs), `schemas.py` (shapes) and `service.py` (rules). Folders with a
`router.py` are picked up automatically by `app/api/router.py`.

| Module | Endpoints (under `/api`) | Purpose |
|---|---|---|
| `health` | `GET /health` | API and database status |
| `tools` | `/tools` | CRUD; a tool needed by a skill can't be deleted |
| `skills` | `/skills` | CRUD; required tools come along when a skill is attached |
| `agents` | `/agents`, `/agents/{id}/publish`, `/agents/{id}/preview-prompt`, … | Build, configure, **publish** (also to Foundry), preview, delete (also in Foundry) |
| `runs` | `POST /agents/{id}/runs`, `GET /runs/{id}`, `GET /runs/{id}/export?format=docx` | Start a run in the background, poll it, download it |
| `evaluations` | `POST /runs/{id}/evaluations`, `GET /agents/{id}/evaluations` | Score a run; score history |
| `datasets` | `GET /datasets` | The projects found in `data/raw` |
| `models` | `GET /models` | Model deployments for the dropdowns |

Interactive API docs: `http://localhost:8080/docs`.

### `backend/scripts/`

| Script | Purpose |
|---|---|
| `run_experiment.py` | Runs an agent on a split of projects, scores every plan, writes `experiments/<label>-<time>/` (CSV, plans, mean ± std summary) |
| `check_llm.py`, `check_tools.py` | Manual checks that the model answers and the file tools behave |
| `demo_step3.py` | Walkthrough of the tools/skills/agents API |

---

## The AI part

### Agent runtime: `app/runtime/`

| File | Purpose |
|---|---|
| `agent_runner.py` | **The agent loop.** Sends the conversation to the model, runs the tools it asks for, feeds results back, repeats until a final answer or `max_tool_rounds`. Images from `view_image` are attached as a user message. Logs every tool call and sums the tokens. |
| `tools/files.py` | **The four tools:** `list_files`, `read_file` (Word → Markdown, paged), `view_image`, `create_document` (Markdown → .md/.docx/.xlsx/.pdf). Guards: never leave the data root, never read answer keys (`gold/`) or reference plans, write only to `agent-output/`, never overwrite. |
| `tools/registry.py` | The tool table (name, description, JSON Schema, function) and argument checking. |
| `storage.py` | **Where data lives:** `LocalStorage` (a folder, for your laptop) or `BlobStorage` (an Azure Blob container, for Azure, signed in with managed identity). |
| `dataset.py` | Finds projects (`raw/<split>/<Pxx_Name>/`): BRD, diagrams, reference plan, gold file. |
| `exporters.py` | Markdown → Word, Excel, PDF or tidy Markdown, in the reference plans' layout. |
| `background.py` | Keeps runs and scorings running after the HTTP response. |

### How skills reach the model: `app/modules/agents/skill_instructions.py`

- **At publish:** the system message becomes a short index of the agent's skills (name, description, trigger phrases).
- **Per message:** skills whose trigger phrase appears in the message (or the only skill) have their **full instructions** put in front of the user's message.

### Model and Foundry clients: `app/integrations/`

| File | Purpose |
|---|---|
| `azure_openai.py` | The only place that calls the models (Azure OpenAI v1 API). Clear error messages, JSON mode for the judge, retries without temperature for reasoning models. |
| `foundry.py` | Azure AI Foundry agent API: create an agent, add a version, delete it, list model deployments. Signs in with Entra ID (`az login` locally, managed identity on Azure). |

### Scoring: `app/evaluation/`

```
overall = (0.25 × structure + 0.45 × coverage + 0.30 × similarity) × faithfulness
```

| Metric | Meaning | How |
|---|---|---|
| Structure | Share of the 20 required test-plan sections present | Code: `sections.py` maps any heading to one of 24 standard sections |
| Coverage | Share of the reference plan's checkable points the plan covers | LLM judge, in batches, **every judgement backed by a quote that code verifies**; reference points cached per project |
| Similarity | Word overlap with the reference, per section | Code: `text.py` |
| Faithfulness | Share of the plan's project-specific claims backed by the BRD or diagram | LLM judge with verified BRD quotes |

`judge.py` holds the judge prompts and quote checks, `scorer.py` puts it together. Faithfulness
multiplies everything, so a plan that invents facts loses everywhere.

### Ready-made agent and prompts: `app/catalog/`

At startup, `sync.py` creates (if missing) the four built-in tools, the skill **BRD to Test Plan** and
the **Test Plan Agent**. It never overwrites a skill you edited.

| Prompt | Technique |
|---|---|
| `prompts/v1_baseline.md` | Zero-shot: two sentences. The baseline. |
| `prompts/v2_structured.md` | Role, working steps, ground rules (BRD facts only, TBD for gaps), fixed section template |
| `prompts/v3_grounded.md` | v2 + requirement inventory, per-section detail, boundary values, self-check list |
| `prompts/v4_full_skill.md` | The full 22-section skill: requirements and rule tables, architecture-driven tests, AI evaluation, scenarios and traceability |

---

## Frontend (`frontend/`)

React 19, Vite, TypeScript, Tailwind CSS 4, TanStack Query, React Router. Built into static files and
served by **nginx**, which also forwards `/api` to the backend (so there is no CORS to manage).

| Path | Purpose |
|---|---|
| `src/pages/DashboardPage.tsx` | Overview: counts, recent agents, backend status |
| `src/pages/AgentsPage.tsx`, `AgentDetailPage.tsx` | Agent list; agent page with **Setup**, **Run**, **Scores**, **Prompt preview** and **Published instructions** tabs |
| `src/pages/AgentRunsTabs.tsx` | Run tab (project, message, model, output format, tool trace, plan, downloads) and Scores tab (per version, per run) |
| `src/pages/Skills*.tsx`, `Tools*.tsx` | Lists and editors for skills (Markdown with preview) and tools (JSON Schema) |
| `src/components/ScoreCard.tsx` | The score breakdown: formula bar, sections table, missed points, unsupported claims |
| `src/components/AppShell.tsx`, `ui.tsx` | Layout, logo, navigation and shared UI pieces |
| `src/lib/api.ts`, `queries.ts`, `types.ts` | API client, data hooks (with polling while a run is going), types |
| `nginx/default.conf.template` | nginx config; `${BACKEND_URL}` is filled in at start |
| `nginx/40-basic-auth.sh` | Turns on a site password when `BASIC_AUTH_PASSWORD` is set (used on Azure) |

---

## Data (`data/`)

```
data/
├── raw/<split>/<Pxx_Name>/    Pxx_..._BRD.docx, Pxx_..._Architecture.png, Pxx_..._TestPlan.docx
├── gold/<split>/<Pxx_Name>/   gold_testplan.json (optional answer key, preferred for scoring)
├── agent-output/              files agents save (git-ignored)
└── _cache/                    scorer cache (git-ignored)
```

- Splits: **train** P00–P05, **validation** P06–P07, **test** P08–P09. Tune prompts on train and
  validation; use test only for the final comparison.
- Locally the backend reads the folder (`AGENT_STORAGE=local`). On Azure the same layout lives in the
  Blob container `agentdata` (`AGENT_STORAGE=blob`).
- The agent can never see `gold/` or the `*_TestPlan.docx` files: they are what it is scored against.

---

## Deployment and CI/CD

### Azure resources (`deploy/azure/setup.ps1`, run once)

| Resource | Purpose |
|---|---|
| Container Registry | Docker images, built inside Azure |
| Container App `ca-agentlab-api` | Backend; internal only; system-assigned managed identity |
| Container App `ca-agentlab-web` | Frontend; the public URL, protected by a site password |
| PostgreSQL Flexible Server (B1ms) | The database |
| Storage account, Blob container `agentdata` | The dataset, agent outputs and scorer cache |
| Your Foundry resource | Model deployments and published agents |
| GitHub OIDC app registration | Lets GitHub Actions deploy without a stored password |

The backend's managed identity gets **Storage Blob Data Contributor** (storage) and **Azure AI
Developer** (Foundry). No storage key is used. Generated passwords are kept in
`deploy/azure/secrets.local.json` (git-ignored).

```powershell
az login
.\deploy\azure\setup.ps1 -GitHubRepo <owner>/agent-lab
```

### Pipeline (`.github/workflows/ci-cd.yml`)

| When | Jobs |
|---|---|
| Every push and pull request | **Backend tests** (`uv sync --frozen`, `pytest`) and **Frontend build** (`npm ci`, type-check, build) |
| Push to `main`, after both pass | **Deploy:** sign in to Azure (OIDC), `az acr build` both images, `az containerapp update` both apps, smoke-test `/healthz` |

Needs these GitHub settings (printed by `setup.ps1`): secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID`; variables `AZURE_RESOURCE_GROUP`, `ACR_NAME`, `API_APP`, `WEB_APP`.

---

## Run it locally

**Needs:** Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node.js 22+, Docker Desktop, an Azure
OpenAI or Foundry model deployment.

```powershell
# 1. Database (Postgres in Docker, on port 5433)
docker compose up -d postgres

# 2. Backend
cd backend
copy .env.example .env          # then fill in the Azure values (see Configuration)
uv sync
uv run pytest -q
uv run uvicorn app.main:app --reload --port 8080     # always start it from backend/

# 3. Frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

Or everything in Docker: `docker compose up --build -d`, then open http://localhost:3000.

---

## Configuration

`backend/.env` locally; Container App settings on Azure. Values without quotes.

| Variable | Example | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5433/agent_lab_db` | Database |
| `DATABASE_SCHEMA` | `al` | Schema for all tables |
| `RUN_ALEMBIC_ON_STARTUP` | `true` | Apply migrations at startup |
| `AZURE_OPENAI_ENDPOINT` | `https://<resource>.openai.azure.com/openai/v1/` | Models (v1 API) |
| `AZURE_OPENAI_API_KEY` | | Model key (secret) |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4.1-mini` | Default model |
| `AZURE_OPENAI_DEPLOYMENTS` | `gpt-5-mini` | Extra models for the dropdowns (Foundry lists its own automatically) |
| `AZURE_OPENAI_TIMEOUT_SECONDS` | `600` | Long plans need more than the 180 s default |
| `EVAL_JUDGE_DEPLOYMENT` | | Model that scores plans (default: the default model) |
| `FOUNDRY_PROJECT_ENDPOINT` | `https://<resource>.services.ai.azure.com/api/projects/<project>` | Publish registers agents here; empty = publish locally only |
| `FOUNDRY_AUTH_MODE` | `entra` | `az login` locally, managed identity on Azure |
| `AGENT_STORAGE` | `local` / `blob` | Where the data lives |
| `AGENT_DATA_DIR` | `../data` | The folder, when `local` |
| `AZURE_STORAGE_ACCOUNT_URL`, `AZURE_STORAGE_CONTAINER` | `https://<account>.blob.core.windows.net`, `agentdata` | The container, when `blob` |
| `SYNC_CATALOG_ON_STARTUP` | `true` | Create the built-in tools, skill and agent if missing |

For Foundry publishing, your account (locally) or the app's identity (Azure) needs the **Azure AI
Developer** role on the Foundry resource.

---

## Using the app

1. **Agents → Test Plan Agent → Setup:** check the skill and tools; choose the model, temperature,
   max tokens (16000 for v2/v3, 32000 for the v4 skill) and tool rounds; **Save settings**.
2. **Publish.** It also registers the agent in Foundry, if configured. Publish again after every
   prompt change, so each version is scored separately.
3. **Run:** pick a project (e.g. P03), optionally another model and an output format, **Run agent**.
   Watch the tool calls; the plan appears in 1–3 minutes.
4. **Score this plan:** see the score breakdown, missed reference points and unsupported claims.
5. **Download** as Word, Excel, PDF or Markdown. Chosen formats are also saved in `agent-output/`.
6. **Scores tab:** compare versions and models.

---

## Prompt-engineering experiments

```powershell
cd backend
uv run python scripts/run_experiment.py --label v2 --prompt app/catalog/prompts/v2_structured.md --split validation --repeats 2
uv run python scripts/run_experiment.py --label v3 --prompt app/catalog/prompts/v3_grounded.md  --split validation --repeats 2
uv run python scripts/run_experiment.py --label v3-gpt5 --model gpt-5-mini --split validation
```

`--prompt` loads the file into the skill and republishes, so each prompt is its own version.
Against Azure: add `--base-url https://<web-url> --user lab --password <sitePassword>`.
Results go to `backend/experiments/<label>-<time>/`. Compare means, not single runs: the same prompt
scores differently from run to run.

---

## Tests

```powershell
cd backend
uv run pytest -q
```

About 90 unit tests, with no database, network or Azure account needed: the model and Foundry are
faked, and the storage tests run every tool both on a local folder and on a fake Blob container.

| File | Covers |
|---|---|
| `test_files_tools.py`, `test_storage.py` | The four tools and their guards, on both storage backends |
| `test_registry.py`, `test_agent_runner.py` | Argument checks; the agent loop with a fake model |
| `test_skill_instructions.py` | Skill index, trigger phrases, injection |
| `test_sections.py`, `test_scorer.py` | Section mapping; the formula, quote checks, judge batching and cache |
| `test_dataset.py`, `test_exporters.py` | Project discovery; Word, Excel, PDF and Markdown output |
| `test_foundry.py` | Publish, new version, delete, model list, against a fake Foundry |

---

## Security and data rules

- Secrets live only in `backend/.env` (locally) or Container App secrets (Azure). `.env`,
  `secrets.local.json`, `.venv` and `node_modules` are git-ignored and excluded from images.
- On Azure, the backend reaches Blob Storage and Foundry with its **managed identity**: no keys for those.
- The site is password-protected; the backend has no public address.
- The dataset in `data/raw` is a **dummy practice dataset**. Never add real company documents to this
  repository or to a personal Azure account.
