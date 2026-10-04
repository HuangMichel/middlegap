export type AIState =
  | 'pending'
  | 'fulfilled'
  | 'gap'
  | 'uncertain'
  | 'conflict'
  | 'proposed_not_applicable'
  | 'analysis_failed';
export type FinalValue = 'Yes' | 'No' | 'N/A';
export type Workspace = { id: string; name: string; created_at: string };
export type Template = { id: string; name: string; description: string; criterion_count: number };
export type Document = {
  id: string;
  original_filename: string;
  status: string;
  page_count: number;
  source_type: string;
  content_hash: string;
};
export type Criterion = {
  id: string;
  number: number;
  text: string;
  gap_phrasing: string;
  key_terms: string[] | string;
  legal_references: string[] | string;
  expected_evidence: string;
  applicability_condition: string | null;
};
export type Subcontrol = {
  id: string;
  code: string;
  title: string;
  weight: number;
  evidence_binding: string;
  population_rule: string;
  criteria: Criterion[];
};
export type Control = { id: string; code: string; title: string; subcontrols: Subcontrol[] };
export type Domain = { id: string; code: string; title: string; controls: Control[] };
export type Checklist = { id: string; name: string; workspace_id: string; domains: Domain[] };
export type ChecklistSummary = Pick<Checklist, 'id' | 'name' | 'workspace_id'>;
export type Anchor = {
  page_number: number;
  text: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  sort_order: number;
};
export type Evidence = {
  id: string;
  document_id: string;
  original_filename: string;
  classification: string;
  confidence_signal: string;
  quoted_passage: string;
  ai_explanation: string;
  review_status: 'unreviewed' | 'accepted' | 'rejected';
  anchors: Anchor[];
};
export type Result = {
  id: string;
  criterion_id: string;
  criterion_code: string;
  criterion_text: string;
  subcontrol_id: string;
  ai_state: AIState;
  confidence_signal: string;
  ai_explanation: string;
  gap_id: string | null;
  document_results: {
    document_id: string;
    original_filename: string;
    ai_state: AIState;
    evidence_summary: string;
  }[];
  evidence: Evidence[];
  review: null | {
    final_value: FinalValue;
    decision_type: 'verified_ai' | 'override';
    override_note: string | null;
    reviewed_at: string;
  };
};
export type SubcontrolScore = {
  id: string;
  code: string;
  title: string;
  status: string;
  achievement: number;
  score: number;
  max_score: number;
  applicable_count: number;
  yes_count: number;
  no_count: number;
  na_count: number;
  unreviewed_count: number;
};
export type Score = {
  aggregation?: 'criteria_engine_v1';
  provisional: boolean;
  reviewed_criteria: number;
  total_criteria: number;
  total_score: number;
  max_score: number;
  domains: {
    id: string;
    code: string;
    title: string;
    score: number;
    max_score: number;
    controls: {
      id: string;
      code: string;
      title: string;
      score: number;
      max_score: number;
      subcontrols: SubcontrolScore[];
    }[];
  }[];
};
export type Run = {
  id: string;
  checklist_id: string;
  status: string;
  started_at: string;
  model_provider: string;
  model_name: string;
  prompt_version: string;
  total_criteria: number;
  scope_limited: boolean;
  processed_criteria: number;
  failed_criteria: number;
  snapshot_documents: { document_id: string; original_filename: string; content_hash: string }[];
  counts: Record<string, number>;
  reviewed_criteria: number;
  score: Score | null;
};
export type Report = {
  id: string;
  run_id: string;
  status: string;
  review_complete: boolean;
  unreviewed_count: number;
  gap_count: number;
  items: { id: string; title: string; request_text: string; gap_ids: string[] }[];
};
