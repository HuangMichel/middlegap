-- Supabase default grants include privileges that row policies do not govern.
-- Expose only SELECT on the deliberately public progress projection.
REVOKE ALL ON TABLE public.assessment_progress FROM anon, authenticated;
GRANT SELECT ON TABLE public.assessment_progress TO anon;

CREATE INDEX assessment_runs_checklist ON public.assessment_runs(checklist_id);
CREATE INDEX checklists_workspace ON public.checklists(workspace_id);
CREATE INDEX documents_workspace ON public.documents(workspace_id);
CREATE INDEX evidence_document ON public.evidence_items(document_id);
CREATE INDEX reports_run ON public.reports(run_id);
