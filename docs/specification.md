# AI-Native Legal Gap Assessment — MVP Specification

## 1. Product objective

The application automates first-pass reconciliation between a legal/compliance checklist and the documentary evidence contained in a workspace data room.

The system:

1. Takes an immutable checklist.
2. Takes a snapshot of the workspace data room.
3. Uses Agentic RAG to assess every criterion in the checklist.
4. Finds and links all evidence it considers materially relevant.
5. Allows the reviewer to inspect every evidence citation in the original PDF.
6. Allows the reviewer to accept/reject evidence and make the final `Yes / No / N/A` determination.
7. Reproduces the checklist's scoring model.
8. Identifies confirmed gaps.
9. Generates a client-facing PDF containing those gaps.

The system assesses only the contents of the workspace data room. It must never imply that absence of documentary evidence proves absence in reality.

Therefore:

> "No evidence of X was found in the provided data room."
> 

is valid.

> "X does not exist."
> 

is not.

---

# 2. Technology

### Frontend

Next.js

### Backend

Python + FastAPI

### Database

Supabase Postgres

### Vector retrieval

Supabase `pgvector`

### File storage

Supabase Storage

### Realtime assessment progress

Supabase Realtime

### AI

Mistral

### Background execution

Separate Python worker process.

No Redis/Celery required for the hackathon.

### PDF processing

Text-based PDFs only.

Scanned/image-only PDFs are explicitly out of scope for the MVP.

---

# 3. Authentication

There is no authentication or user model.

The application assumes the reviewer is already authorized to use the system.

Do not add:

- users
- organizations
- RBAC
- login
- sessions
- invitations

Human actions can simply record timestamps without a `user_id`.

---

# 4. Core hierarchy

The checklist hierarchy should be:

```
Checklist
└── Domain
    └── Control
        └── Sub-control
            └── Criterion
```

Example:

```
Domain
D.03 — Consent and Privacy Notice

Control
D.03.S01

Sub-control
Establish a standard clause in Privacy Notice...

Criteria
1. Legal basis is included
2. Purpose of processing is included
3. Types of personal data are included
4. Retention period is included
5. Data subject rights are included
6. Controller/DPO contact is included
```

The **criterion is the smallest AI-assessed and human-reviewed object**.

The sub-control is the smallest scored grouping.

The control aggregates weighted sub-control scores.

The domain aggregates control scores.

For rows that do not currently have explicit identifiers, generate deterministic IDs when loading the template, for example:

```
D.03.S01.SC01
D.03.S01.SC01.C01
D.03.S01.SC01.C02
...
```

These IDs must remain stable because they will be referenced by assessment results, gap IDs, reports, and audit history.

---

# 5. Checklist templates

Templates are entered directly into the database for the hackathon.

No template editor is required.

A checklist is immutable after creation.

Creating a checklist from a template should snapshot the template definition so that later changes to the manually maintained template do not affect an existing checklist.

Each criterion should retain the relevant workbook fields, including:

```
criterion number
criterion text
gap phrasing
key terms
legal references
expected evidence/document description
applicability condition, if explicitly specified
```

Legal references are retained for traceability/display but **are not used by the retrieval agent**.

Column Z / machine-searchable Key Terms are retrieval hints.

They are not hard matching requirements.

---

# 6. Evidence composition rules

This should be represented with two independent dimensions rather than one overloaded `evidence_scope`.

## Evidence binding

```
corpus
same_document
```

### `corpus`

Different criteria may be satisfied by evidence found across different documents.

### `same_document`

The criteria must coexist within the same document.

---

## Population rule

```
any_relevant_document
all_relevant_documents
```

This allows combinations.

For example:

### General requirement

```
evidence_binding = corpus
population_rule = any_relevant_document
```

Evidence can come from anywhere appropriate in the data room.

### Privacy Notice requirement

```
evidence_binding = same_document
population_rule = all_relevant_documents
```

If Customer, Employee and Vendor Privacy Notices are in scope, **each notice must independently contain the required clauses**.

The system cannot combine:

```
Customer Notice → legal basis
Employee Notice → retention
Vendor Notice → DPO contact
```

and conclude that the requirement is met.

Instead it evaluates:

```
Customer Privacy Notice
  ✓ legal basis
  ✓ purpose
  ✓ data types
  ✓ retention
  ✓ rights
  ✓ contact

Employee Privacy Notice
  ✓ legal basis
  ✓ purpose
  ✗ data types
  ✓ retention
  ✓ rights
  ✓ contact

Vendor Privacy Notice
  ...
```

The population fails because the Employee Privacy Notice fails one criterion.

These composition/population rules must come from the checklist configuration. The AI must **not invent them based on legal knowledge**.

---

# 7. Data room

A workspace has one persistent data room.

Supported sources:

- PDF upload
- Google Drive MCP
- iManage MCP

Google Drive and iManage documents are also PDFs.

For imported documents, copy the exact PDF into Supabase Storage.

Once imported, assessments operate against the stored immutable artifact rather than a mutable external link.

Store:

```
document_id
workspace_id
source_type
original_filename
external_document_id
external_version_id
content_hash
fetched_at
uploaded_at
storage_path
```

Duplicate-document detection/deduplication is explicitly out of scope.

---

# 8. Document ingestion

When a PDF enters the data room:

```
PDF
 ↓
extract pages
 ↓
extract text + layout spans
 ↓
build chunks
 ↓
generate embeddings
 ↓
store chunks + pgvector embedding
```

Use a PDF parser that preserves text coordinates, such as PyMuPDF.

Each extracted text span must retain:

```
page
text
x0
y0
x1
y1
```

Prefer storing normalized coordinates relative to page dimensions so PDF.js can render them consistently at different zoom levels.

Chunks should retain references to the underlying spans.

---

# 9. Assessment snapshot

Pressing **Run Assessment** creates an immutable assessment run.

For the demo, each run assesses only the first criterion in checklist order. The run marks this scope as limited; omitted criteria are not silently treated as analyzed. Scores stay provisional, and final report export is unavailable for these scope-limited runs.

Conceptually:

```
Workspace
  ↓
Data Room
  ↓
Data Room Snapshot
  ↓
Assessment Run
```

The snapshot records exactly which document versions were analyzed.

If the data room subsequently changes, the existing assessment does not change.

A new assessment must be run.

Store:

```
assessment_run_id
checklist_id
started_at
completed_at

model_provider
model_name
prompt_version

status

total_criteria
processed_criteria
failed_criteria
```

And a join table:

```
assessment_run_documents

assessment_run_id
document_id
content_hash
storage_path
external_version_id
```

---

# 10. Assessment run states

```
queued
snapshotting
running
completed
completed_with_errors
failed
```

`completed_with_errors` means the overall assessment finished but one or more criteria have `analysis_failed`.

The UI provides:

**Retry failed**

Retrying must reuse the exact same data-room snapshot.

---

# 11. AI criterion states

The AI assessment and human determination must remain separate.

AI states:

```
pending
fulfilled
gap
uncertain
conflict
proposed_not_applicable
analysis_failed
```

### fulfilled

The available evidence sufficiently supports the criterion.

### gap

No sufficient evidence was found.

Display language such as:

> Potential gap — no sufficient evidence was found in the provided data room.
> 

### uncertain

Relevant evidence was found, but the model cannot reliably determine whether the criterion is met.

### conflict

Credible evidence supports contradictory conclusions.

A conflict takes precedence over `fulfilled`.

### proposed_not_applicable

The checklist contains an explicit applicability condition and the agent believes it is not satisfied.

AI cannot invent applicability rules from general legal knowledge.

### analysis_failed

Technical failure.

This is never equivalent to a gap.

---

# 12. Confidence

Do not produce pseudo-precise percentages.

Use:

```
strong_evidence
possible_evidence
insufficient_evidence
```

This signal is informational and does not control scoring.

---

# 13. Agentic RAG

For each criterion/sub-control, the assessment agent should perform:

```
criterion
+ sub-control context
+ machine-searchable key terms
+ explicit evidence/document expectations
        ↓
candidate document discovery
        ↓
hybrid retrieval
        ↓
candidate passage inspection
        ↓
query reformulation when necessary
        ↓
evidence classification
        ↓
criterion adjudication
```

Use both:

- pgvector semantic search
- PostgreSQL lexical/full-text search

Do not use GDPR/legal-reference columns as retrieval queries.

Do not search:

- internet
- external legal databases
- external knowledge bases

The assessed universe is strictly the snapshot of the workspace data room.

The agent may reformulate its searches using the criterion and machine-searchable terms.

---

# 14. Retrieval saturation

"All relevant evidence" does not mean returning every vector-search hit.

The agent searches iteratively until:

- repeated searches stop discovering materially new evidence, or
- a configured search-round limit is reached.

Each candidate passage is adjudicated before becoming evidence.

Vector-search hits that are merely similar are not automatically persisted as evidence.

---

# 15. Evidence classification

Every retained evidence item is classified as:

```
supports
contradicts
contextual
```

An evidence item contains:

```
evidence_id
criterion_result_id
document_id

classification
confidence_signal

quoted_passage
ai_explanation

review_status
```

Where:

```
review_status =
  unreviewed
  accepted
  rejected
```

---

# 16. Evidence anchors

Evidence can span multiple regions/pages.

Therefore use:

```
evidence_anchors
```

with:

```
evidence_id
page_number
text
x0
y0
x1
y1
sort_order
```

An evidence item can have multiple anchors.

Clicking evidence:

1. opens the original immutable PDF;
2. jumps to the first relevant page;
3. highlights every associated region.

The UI should use PDF.js or equivalent.

---

# 17. Mandatory evidence inspection

If the AI returns five evidence citations, the reviewer must inspect all five.

Each citation must transition from:

```
unreviewed
```

to either:

```
accepted
rejected
```

before the criterion can be finalized.

Backend validation must enforce this.

Do not rely only on frontend button disabling.

A rejected citation does **not** automatically make the criterion a gap.

For example:

```
Evidence A → rejected
Evidence B → accepted
Evidence C → accepted
```

may still result in:

```
Final decision = Yes
```

---

# 18. Human review

After all AI evidence is inspected, the reviewer makes the criterion-level determination:

```
Yes
No
N/A
```

This is the source of truth for final scoring and final reporting.

Store AI and human results separately.

Example:

```
AI:
  state = gap

Human:
  final_value = Yes
  decision_type = override
  override_note = "Confirmed during client review meeting."
```

The AI result remains unchanged in the audit history.

---

# 19. Human overrides

A human can override the AI using a note.

The note is **not evidence from the data room**.

Store:

```
decision_type =
  verified_ai
  override

override_note
reviewed_at
```

This distinction prevents the system from implying that a human override was supported by source-document evidence.

---

# 20. N/A

N/A is conditional.

The agent may propose N/A only when an applicability condition is explicitly present in the checklist/template.

Example:

```
If organization is legally required to appoint a DPO...
```

If the prerequisite is not met:

```
AI → proposed_not_applicable
Human → approves N/A
```

The human has final authority.

The AI must not derive additional applicability tests from its own understanding of GDPR.

---

# 21. Scoring

Reproduce the workbook scoring model.

At criterion level:

```
Yes = met and applicable
No  = applicable but not met
N/A = excluded
```

For a sub-control:

```
applicable_count =
    count(Yes) + count(No)

achievement =
    count(Yes) / applicable_count
```

If:

```
applicable_count = 0
```

then the sub-control is:

```
N/A
```

Status:

```
all applicable Yes → Met
zero Yes           → Gap
some Yes           → Partial
no decisions       → Not Assessed
```

Weighted score:

```
subcontrol_score =
    subcontrol_weight × achievement
```

Control score:

```
sum(subcontrol weighted scores)
```

Domain and total scores should reproduce the existing workbook aggregation rules.

Implement the scoring engine deterministically in Python/Postgres.

**Never ask the LLM to calculate compliance scores.**

During an incomplete human review, scores should be visually identified as **provisional**, because not all criteria have final human decisions.

---

# 22. Assessment of document populations

Population-based requirements need an intermediate result.

For example:

```
criterion_document_results
```

with:

```
criterion_result_id
document_id

ai_state
evidence_summary
```

This lets the application represent:

```
Criterion:
"Privacy Notice contains retention period"

Customer Privacy Notice → Yes
Employee Privacy Notice → No
Vendor Privacy Notice   → Yes
Visitor Privacy Notice  → Yes

Aggregated AI result → gap
```

For:

```
population_rule = all_relevant_documents
```

all relevant documents must satisfy the criterion.

---

# 23. Core Supabase tables

Recommended MVP schema:

```
workspaces

documents
document_pages
document_chunks

checklist_templates
template_domains
template_controls
template_subcontrols
template_criteria

checklists
checklist_domains
checklist_controls
checklist_subcontrols
checklist_criteria

assessment_runs
assessment_run_documents

criterion_results
criterion_document_results

evidence_items
evidence_anchors

criterion_reviews

reports
report_items
report_item_gaps
```

`document_chunks.embedding` uses pgvector.

---

# 24. Background worker

Do not perform reconciliation inside a long-running HTTP request.

Flow:

```
Next.js
   ↓
POST /assessment-runs
   ↓
FastAPI creates assessment_run(status=queued)
   ↓
Python worker claims job
   ↓
snapshot + retrieval + AI analysis
   ↓
writes results incrementally to Supabase
   ↓
Supabase Realtime
   ↓
Next.js updates progress
```

Run one separate Python worker for the hackathon.

The worker can process multiple criterion calls concurrently with a controlled concurrency limit.

---

# 25. Progress UX

The assessment page should progressively update:

```
Assessing checklist

83 / 188 criteria processed

✓ 54 evidence found
! 17 potential gaps
? 8 uncertain
⚠ 2 conflicts
✕ 2 failed
```

The reviewer should be able to begin reviewing completed criteria while the remainder of the assessment is still running.

This is significantly better demo UX than waiting for all 188 criteria to finish.

---

# 26. Review interface

The main hackathon screen should be the reconciliation view.

Recommended layout:

```
┌───────────────────────────────────────────────────────────┐
│ D.03 Consent and Privacy Notice             74% reviewed  │
├───────────────────┬───────────────────────────────────────┤
│ Checklist         │ Selected criterion                    │
│                   │                                       │
│ D.03.S01          │ Retention period is included          │
│ ├─ Clause         │                                       │
│ │ ✓ Legal basis   │ AI: Fulfilled / Strong evidence      │
│ │ ✓ Purpose       │                                       │
│ │ ! Data types    │ Evidence                              │
│ │ ✓ Retention ←   │ ┌───────────────────────────────────┐ │
│ │ ...             │ │ Employee Privacy Notice.pdf       │ │
│                   │ │ Page 7                            │ │
│                   │ │ "...retained for seven years..." │ │
│                   │ │                                   │ │
│                   │ │ [Open source] [Accept] [Reject]   │ │
│                   │ └───────────────────────────────────┘ │
│                   │                                       │
│                   │ Final: [Yes] [No] [N/A]              │
└───────────────────┴───────────────────────────────────────┘
```

Clicking **Open source** opens a PDF panel/modal with the exact passage highlighted.

---

# 27. Checklist review progress

Track at least:

```
188 total criteria
121 reviewed
67 remaining
```

A checklist is review-complete only when every applicable criterion has a final human decision or approved N/A.

---

# 28. Gap creation

A confirmed gap exists when:

```
human_final_value = No
```

Every such criterion receives a stable gap ID.

Example:

```
D.03.S01.GAP.004
```

Do not generate gap IDs with the LLM.

---

# 29. Client report

The client-facing output is PDF.

It contains **gaps only**.

Related gaps can be grouped into one client-facing request.

For example four criterion failures:

```
missing retention period
missing DPO details
missing rights wording
missing processing purposes
```

may become:

> Privacy Notice — Outstanding information
> 
> 
> Please provide or update the Privacy Notice to address processing purposes, retention periods, data-subject rights and Controller/DPO contact information.
> 

The report item stores all underlying gap IDs.

---

# 30. Report completeness invariant

This is a hard backend invariant.

Before export:

```
expected_gap_ids =
    all human-final No criteria

mapped_gap_ids =
    all gaps attached to report items
```

Require:

```
expected_gap_ids == mapped_gap_ids
```

If one confirmed gap is absent:

```
PDF generation fails
```

This prevents LLM summarisation/grouping from accidentally dropping a gap.

The LLM may improve wording but cannot decide which gaps appear in the report.

---

# 31. Draft reports

Drafts may be generated before review completion.

Before export, display a warning:

> Review incomplete
> 
> 
> 31 of 188 criteria have not yet been verified. This report may contain provisional findings and should not be sent to the client.
> 

Require explicit confirmation before producing the draft.

The generated PDF must visibly display:

> DRAFT — REVIEW INCOMPLETE
> 

Final/client-ready export requires review completion.

---

# 32. Report-generation pipeline

```
final criterion decisions
        ↓
confirmed gap IDs
        ↓
group by sub-control
        ↓
construct deterministic structured report
        ↓
optional Mistral wording refinement
        ↓
validate every gap ID is represented
        ↓
render PDF
```

Mistral must not be allowed to:

- add new gaps
- remove gaps
- change criterion outcomes
- change scores

---

# 33. FastAPI endpoints

Minimum useful API surface:

```
GET    /workspaces
POST   /workspaces
GET    /workspaces/{workspace_id}

GET    /workspaces/{workspace_id}/documents
POST   /workspaces/{workspace_id}/documents
DELETE /workspaces/{workspace_id}/documents/{document_id}

GET    /checklist-templates

POST   /workspaces/{workspace_id}/checklists
GET    /checklists/{checklist_id}

POST   /checklists/{checklist_id}/assessment-runs
GET    /assessment-runs/{run_id}
GET    /assessment-runs/{run_id}/results
POST   /assessment-runs/{run_id}/retry-failed

PATCH  /evidence/{evidence_id}/review

PUT    /criterion-results/{result_id}/review

POST   /assessment-runs/{run_id}/reports
GET    /reports/{report_id}
POST   /reports/{report_id}/export
```

---

# 34. Critical backend invariants

The backend must enforce these regardless of frontend behavior.

### Immutable run

An assessment run cannot acquire new documents after starting.

### Immutable AI conclusion

Human review never overwrites the stored AI conclusion.

### Evidence review

A criterion cannot be finalized while AI evidence remains `unreviewed`.

### N/A restriction

AI can propose N/A only where the checklist explicitly contains an applicability condition.

### Conflict precedence

Contradictory credible evidence produces `conflict`, not `fulfilled`.

### Failed analysis

`analysis_failed` never becomes `No`.

### Final reports

Client-ready reports contain human-confirmed gaps only.

### Report coverage

Every confirmed gap must appear in the final report.

---

# 35. Explicit MVP non-goals

Do not spend hackathon time on:

- authentication
- user management
- permissions
- collaboration
- comments between reviewers
- checklist-template UI
- scanned PDF OCR
- non-PDF documents
- duplicate detection
- document supersession/version reasoning
- external legal research
- automated interpretation of unstated applicability conditions
- notifications
- enterprise audit infrastructure
- Redis/Celery
- complex workflow orchestration

---

# 36. Primary demo flow

The hackathon demo should optimize for this sequence:

```
1. Open workspace
2. Show populated legal data room
3. Select GDPR checklist
4. Click Run Assessment
5. Watch 188 criteria reconcile progressively
6. Open D.03 Privacy Notice
7. Show that several different Privacy Notices were identified
8. Show one notice that passes all required clauses
9. Show another notice missing one required clause
10. Click supporting evidence
11. PDF jumps directly to highlighted passage
12. Accept/reject every citation
13. Verify criterion
14. Show scoring update immediately
15. Show confirmed gaps
16. Generate gap report
17. Demonstrate grouped gap wording
18. Export client-facing PDF
```

The strongest part of the demo is not merely:

> "AI searched some PDFs."
> 

It is:

> **"The system reconciled 188 individual compliance criteria against an immutable legal data room, understood when every relevant document had to independently satisfy a requirement, produced source-level citations, forced human verification of every cited passage, reproduced the existing scoring methodology, and generated a completeness-checked client gap report."**
> 

That is the MVP boundary.
