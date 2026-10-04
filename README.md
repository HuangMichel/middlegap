# MiddleGap

AI-assisted reconciliation of an immutable legal checklist against the PDFs in a workspace data room. Reviewers inspect every citation and make the final Yes / No / N/A decision. Scores and confirmed-gap PDF reports are computed and validated by the backend.

Start with [the ordered phases and acceptance checks](PHASES.md). Read [agent working rules](AGENTS.md), [architecture](architecture.md), [design](design.md), [the frontend/backend contract](docs/api-contract.md), and [the preserved specification](docs/specification.md). The current scope uses PDF uploads only; Google Drive and iManage are deferred.

## Project structure

- `frontend/`: Next.js application, PDF.js source viewer, optional Supabase progress subscription.
- `backend/`: FastAPI, separate Python assessment worker, persistence, PDF ingestion, Mistral retrieval/adjudication, deterministic scoring and reports.
- `scripts/`: backend launcher and isolated API/worker/browser acceptance runner.
- `docs/`: original specification, integration contract and verification evidence.

Frontend and backend have independent dependency installations and processes. There is no authentication/user subsystem, template editor, OCR, external legal research or Redis/Celery.

## Setup

Requirements: Node.js 22 or newer, Python 3.11 or newer, `uv`, and configured Supabase/Mistral services. The application requires Supabase Postgres/pgvector, private Storage and Mistral. There is no local database, local file storage or simulated assessment fallback.

The [MiddleGap Supabase project](https://supabase.com/dashboard/project/hltlwyjsaxredjxdhwhy) has been provisioned: ten tables with RLS, pgvector, a private `original-pdfs` bucket and public read-only progress counters. Both checked-in migrations have been applied; do not rerun them on this project. [Service setup](docs/setup.md) explains the verified state, project MCP connection and credentials still needed at runtime.

Install backend dependencies:

```sh
cd backend
uv sync
```

Keep backend keys in `.env` at the repository root. The existing file is preserved and Git-ignored. For a fresh checkout, create a blank file with `backend/.venv/bin/python scripts/start_backend.py --init-env`, then fill the fields shown in [the credential template](config/credentials.example). The launcher reads this file for both API and worker; existing process environment variables take precedence. Missing keys produce an error naming the required fields, with no interactive prompt. Remove obsolete `APP_MODE` first.

```sh
backend/.venv/bin/python scripts/start_backend.py
```

Database connections default to two per process with no overflow, so the API/worker pair uses at most four. If an older process reports `EMAXCONNSESSION`, stop the old API and worker, then run this launcher once. See [connection-limit recovery](docs/setup.md#database-connection-limit-recovery).

Start the frontend in a separate terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open [the application](http://127.0.0.1:3000). In **Workspace settings → Import Excel template**, select the supplied workbook, preview it, choose assessment rules and confirm the source warnings. No command or JSON file is needed. The workbook contains 188 criteria, 24 controls and 80 sub-controls; [workbook mapping](docs/workbook-import.md) explains its scoring and missing rule fields. The original workbook is not copied into Git or seeded automatically.

Create a workspace, upload PDFs and create a checklist from the imported template. Run the assessment, inspect citations and save each final decision. Document results, criterion configuration and assessment history are available in closed details panels. Final PDF export requires complete review; an incomplete draft requires confirmation.

## Verification

Format and lint the frontend:

```sh
cd frontend
npm run format
npm run format:check
npm run lint
```

From the repository root, check shared documentation, configuration and browser scripts:

```sh
node frontend/node_modules/prettier/bin/prettier.cjs --check '*.md' '*.json' '*.mjs' 'docs/**/*.md' '.github/**/*.yml' 'scripts/**/*.mjs'
node frontend/node_modules/eslint/bin/eslint.js scripts/*.mjs eslint.config.mjs --max-warnings 0
uvx ruff@0.16.10 format --check --config backend/pyproject.toml backend scripts
uvx ruff@0.16.10 check --config backend/pyproject.toml backend scripts
```

To format Python, remove `--check` from the Ruff formatting command. The preserved source specification and generated files are excluded from Prettier. Python lint and formatting require Ruff; local execution is pending because package access failed and the standalone download was declined. Existing Python style is not normalized, so CI records its findings in a separate non-gating audit until that work is verified.

```sh
cd backend
uv run pytest
```

Integration scripts run against the isolated test harness only. Its fixtures and fake provider adapters live under `backend/tests/`; they are not an application mode. They exercise snapshot retention, population failure, citation gating, draft/final exports, score updates, report coverage and stale review rejection. Actual-workbook tests check the source formulas and scoring cases; native Excel recalculation and live provider accuracy remain separate checks.

After installing backend/frontend dependencies, run the complete integration check from the repository root:

```sh
cd frontend
npm exec playwright install chromium
cd ..
backend/.venv/bin/python scripts/verify_integration.py
```

The runner builds the UI for an isolated API URL, chooses unused loopback ports, and starts separate API/worker/UI processes. It uses a fresh temporary fixture database and PDF storage, excludes live service configuration, and stops its process groups before removing fixtures. Each run retains logs, a verification record, browser traces, screenshots and exported PDFs under `artifacts/integration/run-*/`. Failed checks exit unsuccessfully and retain diagnostics.

For environments that prohibit local sockets, use the explicitly partial check:

```sh
backend/.venv/bin/python scripts/verify_integration.py --transport in-process
backend/.venv/bin/python scripts/test_integration_runner.py
```

This exercises actual API routes through TestClient with a separate worker subprocess. Its record says `passed_api_only` and `browser: not_run`; it cannot establish HTTP or browser acceptance. Actual-workbook tests require `WORKBOOK_TEST_PATH`; this phase's checks omit that private source as requested, so seven tests skip.

```sh
cd frontend
npm test
npm run typecheck
npm run build
```

[PHASES.md](PHASES.md) and [the verification record](docs/verification.md) distinguish local checks from live Supabase/Mistral/MCP and workbook acceptance. [GitHub Actions](.github/workflows/verify.yml) runs the same integrated runner with pinned Playwright and retained artifacts. It checks PDF canvas pixels and normalized highlight positions, citation enforcement, incomplete draft confirmation/banner, human review invalidation, scoring, final report download and mobile navigation. Use [HANDOFF.md](HANDOFF.md) for the current work state and next input gates.
