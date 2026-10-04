'use client';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { subscribeProgress } from '../lib/realtime';
import { request, downloadReport } from '../lib/api';
import type {
  Workspace,
  Template,
  Document,
  ChecklistSummary,
  Checklist,
  Run,
  Result,
  Evidence,
  Report,
  FinalValue,
  Subcontrol,
} from '../lib/types';
import { stateLabels } from '../lib/review';
import ReviewPane, { Status } from './ReviewPane';
import SourceDrawer from './SourceDrawer';
import ReportDialog from './ReportDialog';
import PanelDialog from './PanelDialog';
import WorkbookImport from './WorkbookImport';
import { formatScore } from '../lib/score';
export default function Workbench() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]),
    [templates, setTemplates] = useState<Template[]>([]),
    [workspaceId, setWorkspaceId] = useState(''),
    [documents, setDocuments] = useState<Document[]>([]),
    [checklists, setChecklists] = useState<ChecklistSummary[]>([]),
    [checklistId, setChecklistId] = useState(''),
    [checklist, setChecklist] = useState<Checklist | null>(null),
    [runs, setRuns] = useState<Run[]>([]),
    [runId, setRunId] = useState(''),
    [run, setRun] = useState<Run | null>(null),
    [results, setResults] = useState<Result[]>([]),
    [selectedId, setSelectedId] = useState(''),
    [templateId, setTemplateId] = useState(''),
    [workspaceName, setWorkspaceName] = useState(''),
    [source, setSource] = useState<Evidence | null>(null),
    [report, setReport] = useState<Report | null>(null),
    [reportOpen, setReportOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [liveMode, setLiveMode] = useState('Polling'),
    [indexOpen, setIndexOpen] = useState(false),
    [settingsOpen, setSettingsOpen] = useState(false),
    [populationOpen, setPopulationOpen] = useState(false),
    [config, setConfig] = useState<{ supabase_url?: string; supabase_anon_key?: string } | null>(
      null,
    );
  const refreshSequence = useRef(0),
    workspaceEpoch = useRef(0),
    runEpoch = useRef(0),
    fileInput = useRef<HTMLInputElement>(null);
  const invalidateRunRequests = useCallback(() => {
    ++refreshSequence.current;
    ++runEpoch.current;
  }, []);
  const initialize = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [, workspaceData, templateData] = await Promise.all([
        request<{ status: string; ai_provider: 'mistral' }>('/health'),
        request<Workspace[]>('/workspaces'),
        request<Template[]>('/checklist-templates'),
      ]);
      setWorkspaces(workspaceData);
      setTemplates(templateData);
      setTemplateId((previous) => previous || templateData[0]?.id || '');
      setWorkspaceId((previous) => previous || workspaceData[0]?.id || '');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void initialize();
    void request<typeof config>('/runtime-config')
      .then(setConfig)
      .catch(() => {});
  }, [initialize]);
  useEffect(() => {
    const epoch = ++workspaceEpoch.current;
    setDocuments([]);
    setChecklists([]);
    setChecklistId('');
    setChecklist(null);
    setRunId('');
    setRun(null);
    setResults([]);
    setReport(null);
    setReportOpen(false);
    setError('');
    if (!workspaceId) return;
    setLoading(true);
    Promise.all([
      request<Document[]>(`/workspaces/${workspaceId}/documents`),
      request<ChecklistSummary[]>(`/workspaces/${workspaceId}/checklists`),
    ])
      .then(([docs, lists]) => {
        if (epoch !== workspaceEpoch.current) return;
        setDocuments(docs);
        setChecklists(lists);
        setChecklistId(lists[0]?.id || '');
      })
      .catch((reason) => {
        if (epoch === workspaceEpoch.current) setError(reason.message);
      })
      .finally(() => {
        if (epoch === workspaceEpoch.current) setLoading(false);
      });
  }, [workspaceId]);
  useEffect(() => {
    let cancelled = false;
    ++runEpoch.current;
    ++refreshSequence.current;
    setChecklist(null);
    setRun(null);
    setRunId('');
    setRuns([]);
    setResults([]);
    setSelectedId('');
    setReport(null);
    setReportOpen(false);
    if (!checklistId) return;
    setLoading(true);
    Promise.all([
      request<Checklist>(`/checklists/${checklistId}`),
      request<Run[]>(`/checklists/${checklistId}/assessment-runs`),
    ])
      .then(([list, history]) => {
        if (cancelled) return;
        setChecklist(list);
        setRuns(history);
        setRunId(history[0]?.id || '');
        setSelectedId(list.domains[0]?.controls[0]?.subcontrols[0]?.criteria[0]?.id || '');
      })
      .catch((reason) => {
        if (!cancelled) setError(reason.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [checklistId]);
  const refreshRun = useCallback(async () => {
    if (!runId) return;
    const seq = ++refreshSequence.current,
      epoch = runEpoch.current;
    const [nextRun, nextResults] = await Promise.all([
      request<Run>(`/assessment-runs/${runId}`),
      request<Result[]>(`/assessment-runs/${runId}/results`),
    ]);
    if (seq !== refreshSequence.current || epoch !== runEpoch.current) return;
    setRun(nextRun);
    setResults(nextResults);
  }, [runId]);
  useEffect(() => {
    ++runEpoch.current;
    ++refreshSequence.current;
    setRun(null);
    setResults([]);
    setReport(null);
    setReportOpen(false);
    if (!runId) return;
    let cancelled = false;
    const refresh = () =>
      void refreshRun().catch((reason) => {
        if (!cancelled) setError(`Progress could not be refreshed: ${reason.message}`);
      });
    refresh();
    const interval = setInterval(refresh, 2500);
    return () => {
      cancelled = true;
      clearInterval(interval);
      invalidateRunRequests();
    };
  }, [runId, refreshRun, invalidateRunRequests]);
  useEffect(() => {
    setLiveMode('Polling');
    if (!runId || !config?.supabase_url || !config.supabase_anon_key) return;
    return subscribeProgress(
      config.supabase_url,
      config.supabase_anon_key,
      runId,
      () => void refreshRun().catch(() => {}),
      (live) => setLiveMode(live ? 'Realtime + polling' : 'Polling'),
    );
  }, [runId, config, refreshRun]);
  const criteria = useMemo(
    () =>
      checklist?.domains.flatMap((domain) =>
        domain.controls.flatMap((control) =>
          control.subcontrols.flatMap((subcontrol) =>
            subcontrol.criteria.map((criterion) => ({ criterion, subcontrol, domain, control })),
          ),
        ),
      ) || [],
    [checklist],
  );
  const selected = criteria.find((item) => item.criterion.id === selectedId),
    result = results.find((item) => item.criterion_id === selectedId) || null,
    resultMap = useMemo(() => new Map(results.map((item) => [item.criterion_id, item])), [results]);
  const confirmedGaps = results.filter((item) => item.review?.final_value === 'No'),
    selectedSubcontrol = selected?.subcontrol;
  useEffect(() => setPopulationOpen(false), [selectedSubcontrol?.id]);
  const act = async (work: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await work();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const createWorkspace = async () =>
    act(async () => {
      const workspace = await request<Workspace>('/workspaces', {
        method: 'POST',
        body: JSON.stringify({ name: workspaceName.trim() }),
      });
      setWorkspaces((previous) => [...previous, workspace]);
      setWorkspaceId(workspace.id);
      setWorkspaceName('');
      setNotice('Workspace created.');
    });
  const createChecklist = async () =>
    act(async () => {
      const list = await request<ChecklistSummary>(`/workspaces/${workspaceId}/checklists`, {
        method: 'POST',
        body: JSON.stringify({ template_id: templateId }),
      });
      setChecklists((previous) => [...previous, list]);
      setChecklistId(list.id);
      setNotice('Checklist created.');
    });
  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    const selectedFiles = Array.from(files);
    await act(async () => {
      let uploaded = 0;
      try {
        for (const file of selectedFiles) {
          if (!file.name.toLowerCase().endsWith('.pdf'))
            throw new Error(`${file.name} is not a PDF. Select text-based PDF files.`);
          const form = new FormData();
          form.append('file', file);
          await request(`/workspaces/${workspaceId}/documents`, { method: 'POST', body: form });
          uploaded++;
        }
      } finally {
        setDocuments(await request<Document[]>(`/workspaces/${workspaceId}/documents`));
        if (fileInput.current) fileInput.current.value = '';
        if (uploaded) setNotice(`${uploaded} PDF${uploaded === 1 ? '' : 's'} added.`);
      }
    });
  };
  const removeDocument = async (document: Document) =>
    act(async () => {
      await request(`/workspaces/${workspaceId}/documents/${document.id}`, { method: 'DELETE' });
      setDocuments((previous) => previous.filter((item) => item.id !== document.id));
      setNotice(`${document.original_filename} removed from future assessments.`);
    });
  const startRun = async () =>
    act(async () => {
      const assessment = await request<Run>(`/checklists/${checklistId}/assessment-runs`, {
        method: 'POST',
        body: '{}',
      });
      setRuns((previous) => [assessment, ...previous]);
      setRunId(assessment.id);
      setNotice('Assessment started.');
    });
  const reviewEvidence = async (evidence: Evidence, status: 'accepted' | 'rejected') =>
    act(async () => {
      await request(`/evidence/${evidence.id}/review`, {
        method: 'PATCH',
        body: JSON.stringify({ review_status: status }),
      });
      setReport(null);
      setReportOpen(false);
      await refreshRun();
      setNotice(
        `Citation ${status}.${result?.review ? ' Previous determination cleared; review again.' : ''}`,
      );
    });
  const saveReview = async (item: Result, value: FinalValue, override: boolean, note: string) =>
    act(async () => {
      await request(`/criterion-results/${item.id}/review`, {
        method: 'PUT',
        body: JSON.stringify({
          final_value: value,
          decision_type: override ? 'override' : 'verified_ai',
          override_note: override ? note.trim() : null,
        }),
      });
      setReport(null);
      setReportOpen(false);
      await refreshRun();
      setNotice(`Determination saved: ${value}.`);
    });
  const generateReport = async () =>
    act(async () => {
      const next = await request<Report>(`/assessment-runs/${runId}/reports`, {
        method: 'POST',
        body: '{}',
      });
      setReport(next);
      setReportOpen(true);
    });
  const exportReport = async (draft: boolean, confirm: boolean) =>
    act(async () => {
      if (!report) return;
      await downloadReport(report.id, draft, confirm);
      setNotice(`${draft ? 'Draft' : 'Final'} PDF downloaded.`);
    });
  return (
    <main>
      <header className="app-header">
        <Link className="brand" href="/" aria-label="MiddleGap home">
          MiddleGap
        </Link>
      </header>
      <section className="workspace-bar" aria-label="Workspace and checklist">
        <div className="select-field">
          <label htmlFor="workspace-select">Workspace</label>
          <select
            id="workspace-select"
            value={workspaceId}
            disabled={busy || !workspaces.length}
            onChange={(event) => setWorkspaceId(event.target.value)}
          >
            <option value="">Select workspace</option>
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
        </div>
        <div className="select-field checklist-select">
          <label htmlFor="checklist-select">Checklist</label>
          <select
            id="checklist-select"
            value={checklistId}
            disabled={busy || !checklists.length}
            onChange={(event) => setChecklistId(event.target.value)}
          >
            <option value="">Select checklist</option>
            {checklists.map((list) => (
              <option key={list.id} value={list.id}>
                {list.name}
              </option>
            ))}
          </select>
        </div>
        <button className="settings-button" onClick={() => setSettingsOpen(true)}>
          Workspace settings
        </button>
        <div className="toolbar-actions">
          <button
            className="primary"
            disabled={
              busy ||
              !checklistId ||
              !documents.some((document) => document.status === 'ready') ||
              ['queued', 'snapshotting', 'running'].includes(run?.status || '')
            }
            onClick={() => void startRun()}
          >
            Run assessment
          </button>
          <button disabled={busy || !runId} onClick={() => void generateReport()}>
            Gap report
          </button>
        </div>
      </section>
      {error && !settingsOpen && !reportOpen && (
        <div className="feedback error" role="alert">
          <span>{error}</span>
          <button disabled={busy} onClick={() => void (runId ? act(refreshRun) : initialize())}>
            Retry refresh
          </button>
          <button aria-label="Dismiss error" onClick={() => setError('')}>
            ×
          </button>
        </div>
      )}
      {notice && !settingsOpen && (
        <div className="feedback notice" role="status">
          <span>{notice}</span>
          <button aria-label="Dismiss notice" onClick={() => setNotice('')}>
            ×
          </button>
        </div>
      )}
      {loading && (
        <p className="loading-line" role="status">
          Loading…
        </p>
      )}
      {!checklist && !loading && !error && (
        <section className="welcome-empty">
          <h1>{workspaceId ? 'Prepare this workspace' : 'Open a workspace'}</h1>
          <p>
            {workspaceId
              ? 'Add PDF documents and create a checklist in workspace settings.'
              : 'Create a workspace to begin reviewing your documents.'}
          </p>
        </section>
      )}
      {checklist && (
        <>
          <section className="progress-strip" aria-label="Assessment and review progress">
            <div>
              <span>Assessment</span>
              <strong>
                {run?.processed_criteria || 0}/{run?.total_criteria || criteria.length}
              </strong>
              <progress
                aria-label="Assessment criteria processed"
                value={run?.processed_criteria || 0}
                max={run?.total_criteria || criteria.length || 1}
              />
            </div>
            <div>
              <span>Reviewed</span>
              <strong>
                {run?.reviewed_criteria || 0}/{run?.total_criteria || criteria.length}
              </strong>
              <progress
                aria-label="Criteria reviewed by human"
                value={run?.reviewed_criteria || 0}
                max={run?.total_criteria || criteria.length || 1}
              />
            </div>
            <div className="score-overview">
              <span>{run?.score?.provisional !== false ? 'Provisional score' : 'Score'}</span>
              <strong>
                {run?.score
                  ? formatScore(run.score.total_score, run.score.max_score, run.score.aggregation)
                  : '—'}
              </strong>
            </div>
            <span className="confirmed-gaps">{confirmedGaps.length} confirmed gaps</span>
            {run && run.failed_criteria > 0 && (
              <button
                disabled={busy}
                onClick={() =>
                  void act(async () => {
                    await request(`/assessment-runs/${runId}/retry-failed`, {
                      method: 'POST',
                      body: '{}',
                    });
                    await refreshRun();
                    setNotice('Retry started.');
                  })
                }
              >
                Retry {run.failed_criteria} failed
              </button>
            )}
          </section>
          {run?.scope_limited && (
            <div className="feedback" role="status">
              <span>
                Demo assessment: only the first checklist criterion is analyzed. Scores and
                reports cover this partial assessment.
              </span>
            </div>
          )}
          {run && (
            <details className="run-audit">
              <summary>Assessment details</summary>
              <div className="audit-body">
                <div className="run-tools">
                  <label htmlFor="run-select">Assessment history</label>
                  <select
                    id="run-select"
                    value={runId}
                    disabled={busy}
                    onChange={(event) => setRunId(event.target.value)}
                  >
                    {runs.map((history) => (
                      <option key={history.id} value={history.id}>
                        {new Date(history.started_at).toLocaleString()} · {history.id.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="muted">
                  {run.status.replaceAll('_', ' ')} · {liveMode} · {run.model_provider}/
                  {run.model_name}
                </p>
                <div className="run-counts">
                  {Object.entries(run.counts || {}).map(([state, count]) => (
                    <span key={state}>
                      <b>{count}</b>{' '}
                      {stateLabels[state as keyof typeof stateLabels] || state.replaceAll('_', ' ')}
                    </span>
                  ))}
                </div>
                <h3>Snapshot · {run.snapshot_documents.length} documents</h3>
                <ul className="snapshot-list">
                  {run.snapshot_documents.map((document) => (
                    <li key={document.document_id}>
                      <span>{document.original_filename}</span>
                      <code title={document.content_hash}>{document.content_hash}</code>
                    </li>
                  ))}
                </ul>
                <p className="mono">
                  Prompt {run.prompt_version} · run {run.id}
                </p>
              </div>
            </details>
          )}
          <button
            className="mobile-index-toggle"
            aria-expanded={indexOpen}
            onClick={() => setIndexOpen(!indexOpen)}
          >
            {indexOpen ? 'Hide checklist' : 'Browse checklist'}
          </button>
          <div className="workbench">
            <aside
              className={`checklist-index ${indexOpen ? 'index-open' : ''}`}
              aria-label="Checklist criteria"
            >
              <div className="index-title">
                <h2>{checklist.name}</h2>
              </div>
              {checklist.domains.map((domain) => (
                <section className="domain-group" key={domain.id}>
                  <h3>
                    <span className="mono">{domain.code}</span>
                    {domain.title}
                  </h3>
                  {domain.controls.map((control) => (
                    <div className="control-group" key={control.id}>
                      <p className="control-label">
                        <span className="mono">{control.code}</span> {control.title}
                      </p>
                      {control.subcontrols.map((subcontrol) => (
                        <div className="subcontrol-group" key={subcontrol.id}>
                          <p className="subcontrol-label">{subcontrol.title}</p>
                          <ol>
                            {subcontrol.criteria.map((criterion) => {
                              const item = resultMap.get(criterion.id);
                              return (
                                <li key={criterion.id}>
                                  <button
                                    className={selectedId === criterion.id ? 'active' : ''}
                                    aria-current={selectedId === criterion.id ? 'true' : undefined}
                                    onClick={() => {
                                      setSelectedId(criterion.id);
                                      setIndexOpen(false);
                                    }}
                                  >
                                    <span
                                      className={`index-indicator status-${item?.review ? 'reviewed' : item?.ai_state || 'pending'}`}
                                      aria-hidden="true"
                                    >
                                      {item?.review
                                        ? '✓'
                                        : item?.ai_state === 'gap'
                                          ? '!'
                                          : item?.ai_state === 'conflict'
                                            ? '↔'
                                            : item?.ai_state === 'fulfilled'
                                              ? '•'
                                              : '○'}
                                    </span>
                                    <span>
                                      {criterion.text}
                                      <small>
                                        {item?.review
                                          ? `Final ${item.review.final_value}`
                                          : stateLabels[item?.ai_state || 'pending']}
                                      </small>
                                    </span>
                                    <span className="criterion-number">{criterion.number}</span>
                                  </button>
                                </li>
                              );
                            })}
                          </ol>
                        </div>
                      ))}
                    </div>
                  ))}
                </section>
              ))}
            </aside>
            <div className="review-workspace">
              {selected && (
                <>
                  <ReviewPane
                    key={selectedId}
                    population={
                      selectedSubcontrol && (
                        <PopulationMatrix
                          subcontrol={selectedSubcontrol}
                          results={resultMap}
                          selectedId={selectedId}
                          onSelect={setSelectedId}
                          open={populationOpen}
                          onToggle={setPopulationOpen}
                        />
                      )
                    }
                    criterion={selected.criterion}
                    subcontrol={selected.subcontrol}
                    result={result}
                    busy={busy}
                    onEvidence={reviewEvidence}
                    onSource={setSource}
                    onSave={saveReview}
                  />
                </>
              )}
              {!selected && <p className="empty-inline">Select a criterion from the checklist.</p>}
              {run?.score && (
                <details className="score-breakdown">
                  <summary>Score details</summary>
                  {run.score.domains.map((domain) => (
                    <div key={domain.id}>
                      <h3>
                        {domain.code} · {domain.title}
                        <span>
                          {formatScore(domain.score, domain.max_score, run.score?.aggregation)}
                        </span>
                      </h3>
                      {domain.controls.map((control) => (
                        <section className="score-control" key={control.id}>
                          <h4>
                            {control.code} · {control.title}
                            <span>
                              {formatScore(
                                control.score,
                                control.max_score,
                                run.score?.aggregation,
                              )}
                            </span>
                          </h4>
                          {control.subcontrols.map((subcontrol) => (
                            <p key={subcontrol.id}>
                              <span>{subcontrol.title}</span>
                              <span>
                                {subcontrol.status} · {subcontrol.yes_count} Yes /{' '}
                                {subcontrol.no_count} No / {subcontrol.na_count} N/A ·{' '}
                                {formatScore(
                                  subcontrol.score,
                                  subcontrol.max_score,
                                  run.score?.aggregation,
                                )}
                              </span>
                            </p>
                          ))}
                        </section>
                      ))}
                    </div>
                  ))}
                </details>
              )}
            </div>
          </div>
        </>
      )}
      {settingsOpen && (
        <PanelDialog onClose={() => setSettingsOpen(false)}>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="notice settings-notice" role="status">
              {notice}
            </p>
          )}
          <details className="settings-section">
            <summary>New workspace</summary>
            <form
              className="settings-form"
              onSubmit={(event) => {
                event.preventDefault();
                void createWorkspace();
              }}
            >
              <label htmlFor="workspace-name">Workspace name</label>
              <input
                id="workspace-name"
                value={workspaceName}
                onChange={(event) => setWorkspaceName(event.target.value)}
                placeholder="Client matter or project"
                maxLength={160}
                required
              />
              <button disabled={busy || !workspaceName.trim()}>Create workspace</button>
            </form>
          </details>
          <WorkbookImport
            disabled={busy}
            onBusyChange={setBusy}
            onImported={async (template) => {
              setTemplates((previous) =>
                previous.some((item) => item.id === template.id)
                  ? previous
                  : [...previous, template],
              );
              setTemplateId(template.id);
              setNotice('Excel template imported and selected.');
              try {
                setTemplates(await request<Template[]>('/checklist-templates'));
              } catch (reason) {
                setError(
                  `Template imported, but the list could not be refreshed. ${(reason as Error).message}`,
                );
              }
            }}
          />
          {workspaceId && (
            <>
              <section className="settings-documents">
                <div className="section-heading">
                  <h3>
                    Data room <span className="muted">· {documents.length} PDFs</span>
                  </h3>
                  <label className="upload-button">
                    Add PDFs
                    <input
                      ref={fileInput}
                      type="file"
                      accept="application/pdf,.pdf"
                      multiple
                      disabled={busy}
                      onChange={(event) => void upload(event.target.files)}
                    />
                  </label>
                </div>
                <p className="muted">Text-based PDFs only. Changes apply to future assessments.</p>
                <ul className="document-list">
                  {documents.map((document) => (
                    <li key={document.id}>
                      <span>
                        <strong>{document.original_filename}</strong>
                        <small>
                          {document.page_count} pages · {document.source_type.replaceAll('_', ' ')}{' '}
                          · {document.status}
                        </small>
                      </span>
                      <button
                        disabled={busy}
                        aria-label={`Remove ${document.original_filename} from future runs`}
                        onClick={() => void removeDocument(document)}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                  {!documents.length && <li className="empty-inline">No PDFs uploaded.</li>}
                </ul>
              </section>
              <details className="settings-section">
                <summary>Create checklist from template</summary>
                <div className="settings-form">
                  <label htmlFor="template-select">Template</label>
                  <select
                    id="template-select"
                    value={templateId}
                    disabled={busy}
                    onChange={(event) => setTemplateId(event.target.value)}
                  >
                    {templates.map((template) => (
                      <option key={template.id} value={template.id}>
                        {template.name} · {template.criterion_count} criteria
                      </option>
                    ))}
                  </select>
                  <p className="muted">
                    {templates.find((template) => template.id === templateId)?.description}
                  </p>
                  {!templates.length && (
                    <p className="muted">
                      No checklist templates are available. Use “Import Excel template” above to add
                      your workbook.
                    </p>
                  )}
                  <button disabled={busy || !templateId} onClick={() => void createChecklist()}>
                    Create checklist
                  </button>
                </div>
              </details>
            </>
          )}
        </PanelDialog>
      )}
      {source && <SourceDrawer evidence={source} onClose={() => setSource(null)} />}
      {reportOpen && report && (
        <ReportDialog
          report={report}
          busy={busy}
          error={error}
          onClose={() => setReportOpen(false)}
          onExport={exportReport}
          onRegenerate={generateReport}
        />
      )}
    </main>
  );
}
function PopulationMatrix({
  subcontrol,
  results,
  selectedId,
  onSelect,
  open,
  onToggle,
}: {
  subcontrol: Subcontrol;
  results: Map<string, Result>;
  selectedId: string;
  onSelect: (id: string) => void;
  open: boolean;
  onToggle: (open: boolean) => void;
}) {
  const documents = new Map<string, string>();
  subcontrol.criteria.forEach((criterion) =>
    results
      .get(criterion.id)
      ?.document_results.forEach((document) =>
        documents.set(document.document_id, document.original_filename),
      ),
  );
  if (!documents.size) return null;
  return (
    <details
      className="population-panel"
      open={open}
      onToggle={(event) => onToggle(event.currentTarget.open)}
    >
      <summary>
        Document results <span className="muted">· {documents.size} PDFs</span>
      </summary>
      <div className="matrix-scroll">
        <table>
          <caption className="sr-only">
            Assessment results for each document and criterion in the selected sub-control
          </caption>
          <thead>
            <tr>
              <th scope="col">Original document</th>
              {subcontrol.criteria.map((criterion) => (
                <th key={criterion.id} scope="col">
                  <button
                    className={selectedId === criterion.id ? 'matrix-selected' : ''}
                    onClick={() => onSelect(criterion.id)}
                    title={criterion.text}
                  >
                    C{criterion.number}
                    <span>{criterion.text}</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from(documents).map(([id, name]) => (
              <tr key={id}>
                <th scope="row">{name}</th>
                {subcontrol.criteria.map((criterion) => {
                  const entry = results
                    .get(criterion.id)
                    ?.document_results.find((document) => document.document_id === id);
                  return (
                    <td key={criterion.id}>
                      <span title={entry?.evidence_summary || 'Not yet assessed'}>
                        {entry ? (
                          <Status state={entry.ai_state} />
                        ) : (
                          <span className="muted">Pending</span>
                        )}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="matrix-note">
        {subcontrol.population_rule === 'all_relevant_documents'
          ? 'Every relevant document must meet each clause.'
          : 'Results for the relevant document population.'}
      </p>
    </details>
  );
}
