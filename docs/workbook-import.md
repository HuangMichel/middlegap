# Criteria Engine workbook mapping

Source: `(Criteria Engine -  Anthony Request - To Use) GDPR Gap Analysis Working Paper + Key Terms (1).xlsx`, sheet `2b. Criteria Engine`. The private source was read only and is not committed. The importer supports this validated layout, not arbitrary Excel files.

## Import flow

In **Workspace settings → Import Excel template**, select the workbook and preview it: 10 domains, 24 controls, 80 sub-controls and 188 criteria. Enter a name, choose both evidence rule defaults, acknowledge warnings and confirm. Optional group overrides and expected document descriptions stay in the closed **Assessment rules** panel. No command or JSON file is needed.

Defaults start blank. `corpus` permits evidence across documents; `same_document` requires clauses to coexist. `any_relevant_document` requires a qualifying document; `all_relevant_documents` requires each relevant document. These choices affect conclusions and are not inferred from the source.

Preview does not persist. Confirmation reparses and compares SHA-256, then creates a new template ID. Provenance retains source rows/formulas/hash/filename/warnings and confirmed rules. Checklist creation freezes the definition.

## Source mapping and warnings

| Cells               | Mapping                                                 |
| ------------------- | ------------------------------------------------------- |
| A12:A199 / B12:B199 | Domain headings / forward-filled control IDs            |
| C12:D199            | Sub-control starts and fixed weights                    |
| E12:F199            | Criterion numbers and text, 188 rows                    |
| I12:I199            | Expected evidence; all supplied cells blank             |
| O12:O199            | Gap phrasing                                            |
| W12:W199            | GDPR references, display only                           |
| Z12:Z199            | Semicolon-separated retrieval terms                     |
| Q12:R21             | Domain summary, independent of criterion-row membership |
| J12:M199            | Achievement, weighted/control scores and status         |
| S12:S21 / S23       | Domain means / overall mean                             |

Stable IDs combine control ID, sub-control ordinal and criterion number. No evidence-binding, population or explicit applicability rules are present. Expected evidence stays empty unless supplied by the reviewer; discovery then starts from the whole snapshot rather than invented document requirements. AI cannot propose N/A without a condition; human N/A requires an override rationale.

`RefLookup` is defined as `#REF!`; V/X/Y supporting-guidance/legal-basis formulas are unusable. Their text is retained, never evaluated. W references remain display-only and excluded from retrieval.

## Literal scoring policy

Known J/K/L/M/S structures and shared formulas are validated before assigning `criteria_engine_v1`. Arbitrary formulas are never executed; cached results are not trusted.

1. Achievement is Yes/(Yes+No); blanks and N/A are excluded. No assessed applicable decisions gives zero.
2. Multiply by original fixed weight, then sum contributions per control. N/A does not redistribute weights.
3. Domain means exclude a control when its **first sub-control** is N/A or Not Assessed, even if later groups are reviewed. This unusual source behavior is disclosed and preserved.
4. Overall score averages **all ten domains**, including zeros. Display ratios as percentages; incomplete review remains provisional.

Six actual-source formula cases pass: all Yes → 100%; all N/A → 0%; only row 17 Yes → overall 6%; first group N/A and later Yes → 0%; first group blank and later Yes → 0%; first group Yes and next group N/A → overall 6%. Native Excel recalculation has not run.

The optional administrative JSON loader remains available; legacy templates retain `weighted_sum`. It is unnecessary for the Excel UI flow.
