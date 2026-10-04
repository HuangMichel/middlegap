-- Execute once in a fresh Supabase project before connected application startup.
-- Exact checklist hierarchy and normalized source spans are immutable JSON snapshots.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
SET search_path = public, extensions;
CREATE TABLE workspaces (id text PRIMARY KEY, name text NOT NULL, created_at text NOT NULL);
CREATE TABLE checklist_templates (id text PRIMARY KEY, definition jsonb NOT NULL);
CREATE TABLE checklists (id text PRIMARY KEY, workspace_id text NOT NULL REFERENCES workspaces(id), definition jsonb NOT NULL);
CREATE TABLE documents (
 id text PRIMARY KEY, workspace_id text NOT NULL REFERENCES workspaces(id), original_filename text NOT NULL,
 source_type text NOT NULL, content_hash text NOT NULL, uploaded_at text NOT NULL, fetched_at text,
 external_document_id text, external_version_id text, page_count integer NOT NULL DEFAULT 0,
 status text NOT NULL, storage_path text NOT NULL, removed boolean NOT NULL DEFAULT false, spans jsonb NOT NULL
);
CREATE TABLE document_chunks (id text PRIMARY KEY, document_id text NOT NULL REFERENCES documents(id), text text NOT NULL, spans jsonb NOT NULL, embedding vector(1024));
CREATE INDEX document_chunks_document ON document_chunks(document_id);
CREATE INDEX document_chunks_lexical ON document_chunks USING gin(to_tsvector('english',text));
CREATE INDEX document_chunks_vector ON document_chunks USING hnsw(embedding vector_cosine_ops);
CREATE TABLE assessment_runs (
 id text PRIMARY KEY, checklist_id text NOT NULL REFERENCES checklists(id), status text NOT NULL,
 started_at text NOT NULL, completed_at text, model_provider text NOT NULL, model_name text NOT NULL,
 prompt_version text NOT NULL, snapshot jsonb NOT NULL, populations jsonb NOT NULL DEFAULT '{}', lease_until text, review_revision integer NOT NULL DEFAULT 0,
 total_criteria integer NOT NULL DEFAULT 0, processed_criteria integer NOT NULL DEFAULT 0, failed_criteria integer NOT NULL DEFAULT 0
);
CREATE INDEX assessment_queue ON assessment_runs(status,started_at);
CREATE TABLE criterion_results (
 id text PRIMARY KEY, run_id text NOT NULL REFERENCES assessment_runs(id), criterion_id text NOT NULL,
 subcontrol_id text NOT NULL, ai_state text NOT NULL, confidence_signal text NOT NULL, ai_explanation text NOT NULL,
 document_results jsonb NOT NULL DEFAULT '[]', review jsonb, gap_id text NOT NULL, UNIQUE(run_id,criterion_id)
);
CREATE TABLE evidence_items (
 id text PRIMARY KEY, result_id text NOT NULL REFERENCES criterion_results(id), document_id text NOT NULL REFERENCES documents(id),
 classification text NOT NULL CHECK(classification IN ('supports','contradicts','contextual')),
 confidence_signal text NOT NULL, quoted_passage text NOT NULL, ai_explanation text NOT NULL,
 review_status text NOT NULL CHECK(review_status IN ('unreviewed','accepted','rejected')), anchors jsonb NOT NULL
);
CREATE INDEX evidence_result ON evidence_items(result_id);
CREATE TABLE reports (id text PRIMARY KEY, run_id text NOT NULL REFERENCES assessment_runs(id), items jsonb NOT NULL, review_revision integer NOT NULL DEFAULT 0);
CREATE TABLE assessment_progress (run_id text PRIMARY KEY REFERENCES assessment_runs(id), status text NOT NULL, total_criteria integer NOT NULL, processed_criteria integer NOT NULL, failed_criteria integer NOT NULL);
-- Disable anonymous legal-data access; API uses trusted database connection.
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['workspaces','checklist_templates','checklists','documents','document_chunks','assessment_runs','criterion_results','evidence_items','reports'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',tab);
  EXECUTE format('REVOKE ALL ON TABLE %I FROM anon, authenticated',tab);
 END LOOP;
END $$;
ALTER TABLE assessment_progress ENABLE ROW LEVEL SECURITY;
GRANT SELECT ON assessment_progress TO anon;
CREATE POLICY progress_read ON assessment_progress FOR SELECT TO anon USING (true);
ALTER PUBLICATION supabase_realtime ADD TABLE assessment_progress;
INSERT INTO storage.buckets (id,name,public) VALUES ('original-pdfs','original-pdfs',false) ON CONFLICT(id) DO NOTHING;
