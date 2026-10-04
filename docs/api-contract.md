# Integration contract

FastAPI is the source of truth. Base URL: `http://localhost:8000`. Next.js: `http://localhost:3000`. No authentication or user model. JSON keys use snake_case. IDs are strings. Dates are ISO-8601 UTC. Errors use `{ "detail": "Actionable explanation" }`. Both engineers own their respective folders; the orchestrator owns this contract and root documents. Changes to this contract must be coordinated.

## Service configuration

`GET /health` → `{status:"ok", ai_provider:"mistral"}`. The application uses Supabase Postgres/Storage and Mistral exclusively. Configuration must be supplied before startup; no sample template or local assessment mode is created automatically.

`GET /runtime-config` → `{supabase_url:null|string,supabase_anon_key:null|string}`. Only public progress configuration may be returned. Subscribe to `assessment_progress` filtered by `run_id`; never expose legal evidence/checklists via anonymous Supabase reads.

Temporary database connection failures or pool-checkout exhaustion return HTTP 503 with `{detail:string}` and `Retry-After: 5`. Responses omit database URLs, credentials, SQL and raw provider errors. Writes are not retried automatically; callers can retry after the service recovers. Schema/programming and constraint errors are not classified as temporary capacity failures.

## Workspaces, templates, documents

- `GET /workspaces` → array of `{id,name,created_at}`.
- `POST /workspaces` body `{name}` → workspace.
- `GET /workspaces/{id}` → workspace.
- `GET /checklist-templates` → array of `{id,name,description,criterion_count}`.
- `POST /checklist-templates/workbook/preview` → multipart `file` (`.xlsx`, max 5 MiB). Returns `{preview_hash,source_filename,sheet_name,counts:{domains,controls,subcontrols,criteria},warnings:[{code,message}],subcontrols:[{id,domain_id,control_id,title,weight,criterion_count,source_rows}]}`. Does not persist a template or evaluate formulas.
- `POST /checklist-templates/workbook` → multipart `file`, `name`, `preview_hash`, `default_evidence_binding` (`corpus|same_document`), `default_population_rule` (`any_relevant_document|all_relevant_documents`), `confirm_warnings` and optional `subcontrol_rules`. The last field is a serialized object keyed by sub-control ID with optional binding, population and `expected_evidence` description overrides. Both default rules and acknowledgement are required. Reparse and SHA-256 comparison reject a changed source with 409. Returns `{id,name,description,criterion_count}`. Each import creates a new immutable template ID.
- `GET /workspaces/{id}/documents` → array of `{id,workspace_id,original_filename,source_type,content_hash,uploaded_at,page_count,status,storage_path}`. status is ready or failed; failed documents are excluded from new runs.
- `POST /workspaces/{id}/documents` → multipart field `file` containing a text PDF.
- `DELETE /workspaces/{id}/documents/{document_id}` → soft removal from future runs; existing snapshots retain the artifact.
- `GET /documents/{document_id}/file` → original PDF bytes, including removed documents retained in a snapshot.
- `POST /workspaces/{id}/checklists` body `{template_id}` → checklist.
- `GET /workspaces/{id}/checklists` → array of checklist summaries `{id,name,workspace_id}`.
- `GET /checklists/{id}` → `{id,name,workspace_id,domains:[{id,code,title,controls:[{id,code,title,subcontrols:[{id,code,title,weight,evidence_binding,population_rule,criteria:[{id,number,text,gap_phrasing,key_terms,legal_references,expected_evidence,applicability_condition}]}]}]}]}`.

Templates may carry `scoring_policy` (`weighted_sum|criteria_engine_v1`) and source `provenance`. The Excel importer supports the validated `2b. Criteria Engine` layout, preserves source rows/formulas/hash, and does not invent empty applicability/evidence values. See [workbook mapping](workbook-import.md). PDF documents enter only through uploads; `/imports`, `/connectors` and connector fetch routes are unavailable.

## Assessment

- `POST /checklists/{id}/assessment-runs` → run. For the demo, the run contains only the first checklist criterion. `scope_limited` is true when criteria were omitted. Snapshot membership is frozen at this request so uploads/deletions before worker execution cannot mutate it.
- `GET /checklists/{id}/assessment-runs` → runs newest first.
- `GET /assessment-runs/{id}` → `{id,checklist_id,status,started_at,completed_at,model_provider,model_name,prompt_version,total_criteria,processed_criteria,failed_criteria,scope_limited,snapshot_documents:[{document_id,original_filename,content_hash}],counts:{fulfilled,gap,uncertain,conflict,proposed_not_applicable,analysis_failed},reviewed_criteria,score}`. Scope-limited runs remain provisional and cannot produce a final report export.
- `GET /assessment-runs/{id}/results` → array of result objects below.
- `POST /assessment-runs/{id}/retry-failed` → same run; retries failed criteria against identical snapshot; preserve successful results and human reviews.
- UI subscribes to Supabase Realtime if public configuration is supplied, and refreshes run/results on changes. Polling remains an available fallback for progress updates.

Run status: queued, snapshotting, running, completed, completed_with_errors, failed.

Result: `{id,criterion_id,criterion_code,criterion_text,subcontrol_id,ai_state,confidence_signal,ai_explanation,gap_id,document_results:[{document_id,original_filename,ai_state,evidence_summary}],evidence:[{id,document_id,original_filename,classification,confidence_signal,quoted_passage,ai_explanation,review_status,anchors:[{page_number,text,x0,y0,x1,y1,sort_order}]}],review:null|{final_value,decision_type,override_note,reviewed_at}}`.

AI states: pending, fulfilled, gap, uncertain, conflict, proposed_not_applicable, analysis_failed. Confidence: strong_evidence, possible_evidence, insufficient_evidence. Evidence classification: supports, contradicts, contextual. Anchors have page numbers starting at 1 and coordinates normalized to 0–1, origin at the top left.

## Human review and score

- `PATCH /evidence/{id}/review` body `{review_status:"accepted"|"rejected"}` → evidence. Changing a citation after criterion finalization must invalidate that human decision and update score/report eligibility.
- `PUT /criterion-results/{id}/review` body `{final_value:"Yes"|"No"|"N/A",decision_type:"verified_ai"|"override",override_note:null|string}` → result. Backend refuses pending or failed analysis, unreviewed evidence, and override without a note. A decision differing from the AI must be an override. Yes additionally requires accepted supporting citations to use verified_ai. No may verify an AI gap with no evidence; N/A may verify an explicitly configured AI proposed_not_applicable. AI conclusions never change. Human N/A is allowed with an override rationale; AI N/A requires explicit applicability configuration.
- Score object: `{aggregation:"weighted_sum"|"criteria_engine_v1",provisional:boolean,reviewed_criteria,total_criteria,total_score,max_score,domains:[{id,code,title,score,max_score,controls:[{id,code,title,score,max_score,subcontrols:[{id,code,title,status,achievement,score,max_score,applicable_count,yes_count,no_count,na_count,unreviewed_count}]}]}]}`. Deterministic Python scoring. Legacy templates sum weighted sub-control scores. Imported workbook templates sum fixed weights per control, average eligible controls per domain using the first sub-control status filter, then average all ten domain scores. N/A never redistributes workbook weights. Ratios use maximum 1 at control/domain/overall levels and display as percentages. Incomplete review remains provisional.

## Reports

- `POST /assessment-runs/{id}/reports` body `{}` → report; deterministic grouping by sub-control.
- `GET /reports/{id}` → `{id,run_id,status,review_complete,unreviewed_count,gap_count,items:[{id,title,request_text,gap_ids:[string]}]}`.
- For a scope-limited demo run, reports include confirmed gaps from analyzed criteria only; omitted criteria count as unreviewed. Export is draft-only and requires explicit incomplete-review confirmation.
- `POST /reports/{id}/export` body `{draft:boolean,confirm_incomplete:boolean}` → PDF bytes. Final export requires all criteria reviewed. Incomplete draft requires explicit confirmation and a visible DRAFT — REVIEW INCOMPLETE banner. Pin a review revision at report creation and reject changed revisions at export even if the gap ID set stays equal. Revalidate current run decisions and exact gap coverage at export; stale report mappings fail, so UI can regenerate. Reports contain human-confirmed No gaps only. No gaps produces an explicit zero-gap PDF, not invented findings.

## Cross-cutting invariants

AI evidence must be grounded in retained PDF spans; retrieval restricted to snapshot. Legal references never used in retrieval input. Conflict overrides fulfilled. Failed analysis never creates a human No automatically. Same-document/population rules come from template configuration. No credentials in browser; only public Supabase URL/anon key for progress, with tightly scoped read policy. Service keys stay backend-only.

Use one consistent discovered document population per sub-control per run. `same_document` + `any_relevant_document` must find a common document satisfying the applicable criteria; independent successes in different documents cannot pass the group. An empty population never passes vacuously. Worker claims need a recoverable lease and idempotent incremental writes, so restart can continue a crashed run without changing its snapshot.
