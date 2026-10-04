# MiddleGap service setup

## Verified Supabase project

Project: [middlegap](https://supabase.com/dashboard/project/hltlwyjsaxredjxdhwhy), reference `hltlwyjsaxredjxdhwhy`, region `eu-central-1`. Public API URL: `https://hltlwyjsaxredjxdhwhy.supabase.co`.

On 2026-10-04, the connected Supabase plugin verified a healthy project with no public tables, matching PDF bucket or Storage object policies. Applied `001_initial.sql` (remote version `20261004144046`) and `002_progress_permissions_and_indexes.sql` (remote version `20261004144247`). Do not rerun them on this project. For another fresh project, apply both in order and check any existing `original-pdfs` bucket is private.

SQL verified ten tables with RLS, no anonymous/authenticated legal-table read/write privileges, anonymous progress SELECT only (INSERT/UPDATE/DELETE/TRUNCATE denied), pgvector 0.8.2 with `vector(1024)`, a private `original-pdfs` bucket and `assessment_progress` in the Realtime publication. Templates, documents and workspaces remain empty. No private workbook or sample data was inserted.

The security advisor's nine informational [RLS-without-policy notices](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy) are intentional: legal records use the trusted backend connection; browser roles have no access. Do not add permissive policies to clear them. Missing foreign-key indexes were added; remaining [unused-index notices](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index) reflect the empty database.

## Supabase MCP for Codex

`.codex/config.toml` scopes `middlegap_supabase` to this project with database, documentation, development, debugging and Storage tools. It contains no tokens. Codex parsed this configuration successfully; OAuth/tool startup for this additional server remains unverified.

Reopen the trusted project and authenticate in MCP settings, or run `codex mcp login middlegap_supabase` from this repository in your terminal. Verify it by listing the project's tables. The Supabase plugin used for provisioning was already authenticated; its session is separate.

References: [Supabase project-scoped MCP](https://supabase.com/docs/guides/ai-tools/mcp), [Codex MCP configuration and OAuth](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Application credentials

MCP access does not configure FastAPI. Store backend credentials in `.env` at the repository root. It is Git-ignored; the existing file was preserved without reading or overwriting it. For a fresh checkout, install dependencies and create a blank template:

```sh
cd backend
uv sync
cd ..
backend/.venv/bin/python scripts/start_backend.py --init-env
```

The initializer creates a new file with owner-only permissions and refuses to overwrite an existing file. [config/credentials.example](../config/credentials.example) documents its fields:

- `DATABASE_URL`: Postgres URI from the project Connect panel, including password. Choose direct or session-pooler connectivity appropriate to your network.
- `SUPABASE_SERVICE_ROLE_KEY`: backend Storage credential from API key settings.
- `MISTRAL_API_KEY`: embedding/assessment credential.
- `SUPABASE_URL`: project URL, supplied by the blank template or public project defaults.

Fill values locally, never in chat or Git. Start both backend processes with:

```sh
backend/.venv/bin/python scripts/start_backend.py
```

The launcher loads the root `.env` for both API and worker. Explicit environment variables take precedence; absent public URL/bucket fields fall back to `config/project.toml`. Missing private fields stop startup with their names only. There are no interactive credential prompts. Direct API/worker commands require the same values in their environment.

Supported file syntax is literal `KEY=value`, optional `export`, single/double quotes and comments. Quote values containing spaces or a comment marker. Shell commands and `${VARIABLE}` references are not executed or expanded. Multiline assignments are unsupported. Remove obsolete `APP_MODE` first.

Start the frontend separately: `cd frontend`, `npm ci`, `npm run dev`. It needs no server credentials. Optional `SUPABASE_ANON_KEY` enables the current progress WebSocket client using a legacy anon JWT; polling works without it.

Live API/worker startup, Storage upload and Mistral calls remain unverified: the credential file is protected from agent reads and local server binding is restricted. Remote schema verification is complete.

## Database connection limit recovery

`EMAXCONNSESSION` means the Supabase session pool has reached its client limit. The reported limit for this project is 15. SQLAlchemy's former defaults permitted five persistent connections plus ten overflow connections per process, so the API and worker could collectively exceed that limit. Live read-only inspection observed 15 Supavisor backend connections; their ownership was not inferred from the shared application name.

The application now defaults to `DB_POOL_SIZE=2`, with overflow disabled, and `DB_POOL_TIMEOUT=5` seconds. The API/worker pair permits at most four connections by default; additional processes and tools consume their own quota. Invalid pool settings are rejected before connecting. Failed/replaced engines and shutdown dispose idle connections. Database connection failures or local checkout exhaustion return a sanitized HTTP 503 with `Retry-After: 5`.

Stop the existing API and worker in their terminals (Ctrl+C), then start a single pair:

```sh
backend/.venv/bin/python scripts/start_backend.py
```

Restarting is necessary: code changes cannot resize pools already running in old processes. If capacity errors persist after old MiddleGap processes are stopped, inspect the project's other clients in [Supabase Observability](https://supabase.com/dashboard/project/hltlwyjsaxredjxdhwhy/observability). Do not terminate unowned sessions or change the pooler port as a shortcut.

References: [SQLAlchemy pool sizing](https://docs.sqlalchemy.org/en/21/core/pooling.html), [Supabase connection pooling and limits](https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits).

## Excel and PDFs

Use **Workspace settings → Import Excel template**, preview the `.xlsx`, choose explicit assessment rules and confirm warnings. See [workbook mapping](workbook-import.md). Create a workspace/checklist and upload text PDFs. Google Drive and iManage are deferred; no document connector controls or routes are active.
