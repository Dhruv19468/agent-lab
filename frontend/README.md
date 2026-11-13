# Agent Lab frontend

React 19 + Vite + TypeScript + Tailwind CSS 4, with TanStack Query for data and React Router for pages.

## Pages

| Page | What it does |
|---|---|
| Overview | Counts, recently changed agents, backend status, the four steps to a first agent |
| Agents | List with status filter; create an agent |
| Agent | Attach/detach skills and tools, model settings, publish, **prompt preview**, published instructions |
| Skills / skill editor | Markdown instructions with preview, trigger phrases, required tools |
| Tools / tool editor | Name, description, JSON Schema parameters, backend-only config |

## Run in development

Needs Node.js 22+. The backend must run on port 8080.

```powershell
cd frontend
npm install        # first time, creates package-lock.json
npm run dev        # http://localhost:3000
```

Vite forwards `/api`, `/docs` and `/openapi.json` to `http://localhost:8080`
(change with `VITE_BACKEND_URL` in `frontend/.env`).

Other scripts: `npm run build` (static site in `dist/`), `npm run typecheck`.

## Run in Docker

From the repository root: `docker compose up --build -d`, then open http://localhost:3000.
nginx serves the built site and forwards `/api` to the `backend` service.

## Layout

```
src/
  main.tsx            entry: React Query + toasts + router
  router.tsx          URL -> page
  app.css             Tailwind + design tokens (colours, fonts)
  lib/                api client, React Query hooks, types, date formatting
  components/         AppShell (sidebar), ui (buttons, fields, tables, dialogs), TagInput, JsonField, toasts
  pages/              one file per screen
```
