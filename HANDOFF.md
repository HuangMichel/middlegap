# Handoff

## Objective and current scope

Build the legal gap assessment MVP in ordered phases with separate frontend/backend ownership. The user supplied the actual Excel workbook, selected Supabase project `hltlwyjsaxredjxdhwhy`, deferred iManage, then deferred Google Drive: PDF uploads only. Keep the decluttered UI and no demo mode. Full repository publication remains a prior incomplete request.

## Integrated result

Excel preview and confirmed import are in Workspace settings. The actual Criteria Engine maps 10 domains, 24 controls, 80 sub-controls and 188 criteria. Import requires explicit reviewer-selected evidence/population rules and source-warning acknowledgement; optional group rules remain closed. Reparse/hash validation prevents importing a changed source. Templates retain source provenance and literal scoring policy; checklists freeze definitions. Missing evidence/applicability and broken RefLookup remain explicit warnings, not invented data. Native Excel recalculation is unverified.

Google Drive/iManage controls, discovery calls and runtime import/fetch routes are removed. Uploads remain; historical external metadata and the isolated unused adapter remain intact.

Supabase live setup is complete: `middlegap_initial` version `20261004144046`, `middlegap_progress_permissions_and_indexes` version `20261004144247`. Verified ten RLS tables, legal-role privileges revoked, progress SELECT-only for anon, pgvector 0.8.2/vector(1024), private original-pdfs bucket, Realtime publication, five added FK indexes. Workspaces/templates/documents remain empty. Advisor notices are intentional policy absence and unused indexes in the empty project.

Project `.codex/config.toml` scopes Supabase MCP to this project; Codex parsed it. The already-authenticated Supabase plugin provisioned the database; OAuth/tool initialization of the additional project server is still pending. `config/project.toml` contains public coordinates only. `scripts/start_backend.py` now loads keys from the root Git-ignored `.env` and starts/stops API+worker together; explicit environment values take precedence. It no longer prompts. The existing protected file was preserved without reading or overwriting it. No secrets or workbook have been committed.

## Verification

Backend: 55 tests passed including readonly supplied-workbook checks, six literal source-formula cases, upload-only route rejection and archive/XML validation. Compilation and offline lock validation (33 packages) passed. Frontend: 12 tests, formatting, zero-warning lint, typecheck and exact-source production build passed. Actual-workbook API integration passed in an isolated memory database: preview, confirmed import, required rules, checksum, frozen checklist and score response. Private launcher configuration: five tests passed, including refusal before visible-input fallback. Integration runner: four tests passed; current socket-free API plus separate-worker smoke passed all 12 workflow invariants; evidence is /private/tmp/middlegap-final-integration/run-o2jxnzpv. Isolated connector protocol: six tests passed in the previous verified state; adapter unchanged. Independent code review found no remaining workbook/UI/migration/launcher defects; the terminal echo fallback finding was fixed and retested.

Source formula validation and derived oracles are not native Excel recalculation. Remote SQL verification is not an application Storage/Mistral call. Local server binding remains restricted, so actual browser/PDF/mobile acceptance remains pending. Python Ruff acquisition was declined: do not work around that denial; Ruff checks remain unexecuted.

## Pending gates and next action

Fill DATABASE_URL, SUPABASE_SERVICE_ROLE_KEY and MISTRAL_API_KEY locally in the root .env (or existing runtime environment); authenticate the new project MCP connection in Codex. Start frontend separately. Import the supplied Excel in UI with deliberate rule choices, upload PDFs and verify real assessment/citations/reports on a machine permitting server/browser access. See docs/setup.md and docs/verification.md.

GitHub Actions is prepared, not run. Publication remains incomplete: last verified remote change was AGENTS.md on codex/phased-mvp; full source/current changes remain local. Preserve existing staged/unstaged work and license; do not claim a push or CI result. No PR was created.

## Phase 8 implementation

The user requested the last phase and excluded an additional original-workbook check. Preserve the prior workbook and Supabase evidence above; this run did not repeat those external checks or modify live services.

`scripts/verify_integration.py` is the shared local/CI entrypoint. Default HTTP transport builds the UI with its isolated API URL, chooses loopback ports, starts separate API/worker/UI processes and invokes API/browser checks. It strips live provider configuration, creates temporary fixtures, retains per-run evidence, fails on failed checks and terminates process groups before fixture cleanup. `--transport in-process` uses TestClient and a separate worker; records explicitly state partial API-only verification.

The harness uses SQLite WAL/foreign keys, idempotent fixture seeding and null public Realtime configuration. Test-only health identifies the provider as synthetic; production health remains Mistral. Playwright 1.63.0 is pinned. Browser checks verify rendered canvas pixels/anchor bounds, citation gating, draft confirmation and PDF banner, all human determinations, score, review invalidation, final PDF and mobile navigation. Failures retain screenshot/HTML/trace/JSON diagnostics. Independent review findings on provider labeling, cleanup and unverified Python style gating were addressed. Existing Python style is a separate explicitly non-gating CI audit; Ruff remains unexecuted.

Current checks: 48 backend tests pass, seven original-workbook tests skip; 12 frontend tests and five runner isolation/cleanup checks pass. The API/separate-worker smoke passes with socket-free transport, including population outcome, draft/final PDF text, score and stale export rejection. HTTP startup fails at socket binding (`EPERM`); Chromium launch independently fails with `bootstrap_check_in` permission denied (1100). Actual browser acceptance and remote CI remain unverified.

Final source production build, with the isolated API endpoint set at build time, passed at `/private/tmp/middlegap-phase8-build-vrh1emhi/frontend`. Root formatting/JavaScript lint, six connector protocol tests and five current launcher checks also pass. Passing socket-free evidence is at `artifacts/integration/run-izc37kb9/verification.json`; the blocked HTTP attempt is separately recorded at `artifacts/integration/run-14l12zsn/verification.json`. Evidence directories are Git-ignored.

Next phase-8 check: run `backend/.venv/bin/python scripts/verify_integration.py` on a machine allowing local servers and Chromium, or execute the prepared GitHub workflow after publication. Production service acceptance uses the launcher and remains separate from the synthetic harness. All prior staged/unstaged changes are preserved; no commit or push was made in this phase.

## Operational constraints

No authentication subsystem or OCR; one separate worker, sequential criteria, 20-minute recovery lease. Immutable document membership/artifacts and explicit human review gates remain. Public Realtime exposes counters only. Never read denied .env/key files or collect credentials in chat. Follow AGENTS.md ownership, API contract and PHASES.md.

## Latest credential configuration change

User requested keys in `.env`. Implemented literal file loading in the production launcher only, preserving application import/test isolation. Added config/credentials.example and --init-env exclusive creation with mode 0600; initialization reported an existing file and left it unchanged. No actual .env was read by agents. Existing Git ignores cover the root/backend .env paths. Nine synthetic configuration tests pass: file loading, environment precedence, quoting/comments/literal shell text, missing file/deploy settings, safe errors, size bounds, control-character rejection and overwrite/permission protection. No dependency changes or live provider calls. Prior prompt tests are historical; current tests exercise file configuration. See docs/setup.md.

Independent review confirmed the control-character rejection fix and found no remaining actionable loader defects. Review used source and synthetic values only.
