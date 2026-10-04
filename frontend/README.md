# MiddleGap frontend

The Next.js workbench reads the FastAPI API described in [the contract](../docs/api-contract.md). It requires the configured Supabase and Mistral backend. Missing configuration or an unavailable service is shown as an error; no substitute results are generated.

```sh
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:3000 with the API at http://127.0.0.1:8000. To use another API origin, set `NEXT_PUBLIC_API_URL` in the process environment before starting/building. This is a public URL; never put service keys in frontend configuration.

```sh
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

The postinstall command copies the installed PDF.js worker, standard font assets and image decoders into `public/` (the worker is `pdf.worker.min.mjs`), so PDF viewing works without a CDN. Original PDFs load from the backend and normalized citation anchors overlay the rendered page. System fonts require no network downloads.

Polling refreshes progress and results every 2.5 seconds. The backend can return public Supabase settings from `/runtime-config`; the client subscribes only to the `assessment_progress` table filtered by run ID, using the public Realtime WebSocket protocol, then reads results through the backend. Polling continues if realtime fails.

Human review controls scoring. Citations must all be reviewed before a determination is saved. Unsupported Yes, changes from AI suggestions, and discretionary N/A require an override rationale. Changing a citation invalidates its earlier determination. The backend enforces these rules and exact report coverage at export.

Browser integration, PDF highlights, keyboard focus, report exports and responsive checks are separate verification gates from compilation. The root phase tracker records current evidence.

Data-room documents enter through local text-based PDF uploads. The original artifact is retained for assessment snapshots and citation inspection.

Use `npm run format` to apply the repository Prettier style. `npm run lint` checks the Next.js core web vitals and TypeScript rules with zero warnings allowed. Dependencies and formatter/linter versions are pinned in the lockfile.

The review view prioritizes the selected criterion, citations and final determination. Workspace creation, PDF uploads and template selection are available through **Workspace settings**. **Import Excel template** previews your `.xlsx` workbook before creating a reusable template: choose both evidence rule defaults, review and confirm source warnings, and optionally set per-sub-control rules or expected document descriptions under **Assessment rules**. Source changes clear the preview and rule choices; stale preview responses are ignored. Assessment history, status counts and snapshot metadata remain under **Assessment details**; population comparisons under **Document results**; checklist rules and legal references under **Criterion details**. These sections stay closed during normal review.

Workbooks with the `criteria_engine_v1` aggregation display total, domain, control and sub-control scores as percentages. Older templates retain their weighted-point display. The backend remains the sole scoring authority.
