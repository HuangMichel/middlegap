# Design

MiddleGap is a legal evidence workbench for a reviewer reconciling a checklist against a fixed data room. Its main job is to inspect a cited passage, review every citation, and make a final determination.

## Direction

Use the structure of a legal case file: a hierarchical checklist index on the left, the selected criterion and evidence in the center, and the original PDF in a source drawer. A compact progress row shows assessment and human review separately. Avoid a dashboard landing page. A closed document-results panel reveals the population matrix when the reviewer needs to compare source documents.

Colors: ink `#182F43`, workspace `#EDF2F6`, paper `#FFFFFF`, evidence blue `#285F9B`, confirmed green `#28705B`, attention amber `#9A641C`. Red is reserved for technical failure and conflicts, not every potential gap. Typeface roles: restrained Georgia for workspace/criterion titles, system sans-serif for working controls, monospace for stable IDs and page references. Use local/system fonts so startup does not depend on font downloads.

## Primary flow

1. Import the Excel workbook through Workspace settings: preview, choose both assessment rule defaults, confirm source warnings; optional group overrides stay closed. Open/create a workspace, upload text PDFs, create an immutable checklist from the imported template.
2. Run assessment, see frozen document membership and progressive criterion results.
3. Select criterion, inspect per-document results and evidence; open original PDF at anchored page with highlights.
4. Accept/reject every citation, then save Yes/No/N/A. Overrides require a separate rationale, clearly identified as a human note.
5. See deterministic provisional score and human-confirmed gaps.
6. Generate grouped gap report. Export final after review completes, or explicitly confirm an incomplete draft.

## Required states

- Explain service failures and empty setup states with an actionable message; never substitute sample results.
- Treat AI potential gaps separately from confirmed gaps. Use “No sufficient evidence was found in the provided data room.”
- Display pending, uncertain, conflict and technical failure with explicit meanings; offer retry for failed criteria.
- Show provisional scoring whenever human review is incomplete.
- Handle empty workspaces/documents, upload rejection, network errors, and zero-gap reports with concrete next actions.
- Responsive layout: three working areas on desktop; checklist and source drawer collapsible on smaller screens. Visible focus, labelled form fields, semantic buttons, non-color status labels, reduced-motion support, and keyboard-operable source drawer.

## Review checkpoint

The design is accepted only after the real frontend/backend flow is exercised, with PDF highlighting, human-review enforcement, draft confirmation, and a mobile viewport checked. Build/type checks alone do not establish visual acceptance.

## Decluttered workbench

Keep a compact brand header, one workspace/checklist toolbar and one progress row. The selected criterion, citations and final decision occupy the main view. Workspace creation, PDF uploads, Excel template import and checklist creation belong in a workspace-settings dialog. Document connectors are deferred and have no visible controls. Keep the 80-group assessment rules table closed until requested. Workbook source warnings must be acknowledged explicitly. Keep assessment counts, history, snapshot identifiers and score breakdown in secondary disclosures. Criterion rules and legal references stay in criterion details. Avoid repeated instructions, decorative eyebrows and implementation labels such as polling transport or model names in the primary flow.

Keep every citation's accept/reject control visible alongside its quote. Preserve technical failure messages, retry, required override rationale and incomplete-draft confirmation. Secondary placement must not remove access to document populations, source PDFs, historical runs or scoring details. On narrow screens, open the checklist index deliberately and retain visible keyboard focus and dialog focus restoration.
