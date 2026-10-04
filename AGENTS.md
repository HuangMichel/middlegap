# Working in MiddleGap

## Scope and sources

Follow the current user request and its approval scope. Reviews and proposals authorize analysis; implementation requires an action request. Preserve existing edits and established decisions.

Before changing product behavior, read the relevant sections of [the specification](docs/specification.md) and [architecture.md](architecture.md). Before changing an endpoint or shared data shape, read [the API contract](docs/api-contract.md). Before changing the review interface, read [design.md](design.md).

## Orchestration and ownership

The main agent owns the integrated outcome, shared contracts, root documentation and integration checks. Delegate when independent work provides a concrete benefit:

- `frontend_engineer`: `frontend/**`, interface behavior, accessibility, client integration and frontend verification.
- `backend_engineer`: `backend/**`, persistence/migrations, ingestion, worker, retrieval, review rules, scoring, reports and backend verification.
- `architecture_reviewer`: independent review of boundaries, shared contracts, data ownership and costly decisions.
- `code_reviewer`: independent review of consequential code changes and missing behavioral coverage.

Each assignment must name its files, expected result, dependencies and acceptance criteria. Tell implementers that others share the workspace. One writer owns each file at a time; overlapping changes run sequentially, with the second agent rereading the updated file. Coordinate contract changes before dependent work proceeds.

## Build phases and completion

Use [PHASES.md](PHASES.md) as the ordered checkpoint tracker. Finish each dependency before declaring its dependent phase accepted. Record actual test evidence and distinguish implemented code, locally verified behavior and pending external checks.

Check frontend and backend together after shared changes. Resolve actionable review findings within scope. Live Supabase/Mistral/MCP behavior and original-workbook scoring require their own evidence; sample data and mocks cannot establish those outcomes.

Before a planned stop or context handoff, update [HANDOFF.md](HANDOFF.md) with progress, local changes, decisions, checks, blockers and the next action. On resuming, compare it with the actual files. Keep [README.md](README.md) links and launch instructions aligned with the implementation.

## Product invariants

- Freeze the checklist definition and assessment document membership. Existing runs use retained original PDF artifacts, including after removal from the live data room.
- Ground evidence quotes and normalized anchors in stored source spans. Retrieval stays inside the run snapshot and uses configured criterion/context/key terms/document expectations; legal references are display-only.
- Apply evidence binding and population rules from the checklist configuration. Keep document populations consistent and require clause coexistence when configured. An empty population cannot pass.
- Preserve AI conclusions separately from human decisions. Technical failure is distinct from a documentary gap. AI N/A requires an explicit applicability condition. Credible contradictions take precedence over fulfillment.
- Finalize a criterion only after every citation is accepted or rejected. Enforce this in the backend. A later citation change invalidates its dependent human decision atomically. Human overrides require a rationale kept separate from documentary evidence.
- Compute scores deterministically from human Yes/No/N/A; mark incomplete reviews provisional. Validate actual workbook aggregation before claiming parity.
- Reports contain human-confirmed No gaps only. Verify exact gap coverage and current review revision before export. Final export requires complete review; incomplete drafts require explicit confirmation and a visible draft banner.

## Configuration and communication

Keep server credentials out of browser configuration, logs, fixtures and committed files. Public Realtime data contains progress counters only; legal records and original PDFs remain backend-controlled. The application requires Supabase/Mistral; do not restore demo mode, automatic sample seeding or simulated provider fallbacks. Keep test databases and provider fakes under test code.

Respond in the user's language with concrete findings, relevant evidence and limitations. Ask only for information that materially changes scope, correctness or consequences, and continue independent authorized work while waiting. Preserve the MVP boundary in the specification; expand scope only when requested.
