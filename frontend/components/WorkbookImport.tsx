'use client';
import { useEffect, useRef, useState } from 'react';
import { request } from '../lib/api';
import type { Template } from '../lib/types';
import { PreviewRequests, workbookImportError, workbookImportForm } from '../lib/workbook';
import type {
  EvidenceBinding,
  PopulationRule,
  WorkbookPreview,
  SubcontrolRule,
} from '../lib/workbook';

export default function WorkbookImport({
  disabled,
  onImported,
  onBusyChange,
}: {
  disabled: boolean;
  onImported: (template: Template) => Promise<void>;
  onBusyChange: (busy: boolean) => void;
}) {
  const [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState<WorkbookPreview | null>(null),
    [name, setName] = useState(''),
    [binding, setBinding] = useState<EvidenceBinding | ''>(''),
    [population, setPopulation] = useState<PopulationRule | ''>(''),
    [rules, setRules] = useState<Record<string, SubcontrolRule>>({}),
    [confirmed, setConfirmed] = useState(false),
    [previewing, setPreviewing] = useState(false),
    [importing, setImporting] = useState(false),
    [imported, setImported] = useState(false),
    [error, setError] = useState('');
  const previews = useRef(new PreviewRequests()),
    importPending = useRef(false),
    previewPending = useRef<number | null>(null);
  useEffect(() => {
    const requests = previews.current;
    return () => requests.invalidate();
  }, []);
  const selectFile = (selected: File | null) => {
    previews.current.invalidate();
    previewPending.current = null;
    setFile(selected);
    setPreview(null);
    setName(selected?.name.replace(/\.xlsx$/i, '') || '');
    setBinding('');
    setPopulation('');
    setRules({});
    setConfirmed(false);
    setPreviewing(false);
    setImported(false);
    setError('');
  };
  const loadPreview = async () => {
    if (!file || disabled || importPending.current || previewPending.current !== null) return;
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      setError('Select an Excel .xlsx workbook.');
      return;
    }
    const requestId = previews.current.begin();
    previewPending.current = requestId;
    setPreviewing(true);
    setPreview(null);
    setConfirmed(false);
    setError('');
    const form = new FormData();
    form.append('file', file);
    try {
      await previews.current.resolve(
        requestId,
        request<WorkbookPreview>('/checklist-templates/workbook/preview', {
          method: 'POST',
          body: form,
        }),
        setPreview,
      );
    } catch (reason) {
      if (previews.current.isCurrent(requestId)) setError((reason as Error).message);
    } finally {
      if (previews.current.isCurrent(requestId)) {
        previewPending.current = null;
        setPreviewing(false);
      }
    }
  };
  const updateRule = (id: string, field: keyof SubcontrolRule, value: string) =>
    setRules((previous) => {
      const rule = { ...previous[id], [field]: value };
      if (!value) delete rule[field];
      const next = { ...previous, [id]: rule };
      if (!Object.keys(rule).length) delete next[id];
      return next;
    });
  const values = { file, preview, name, binding, population, confirmWarnings: confirmed, rules };
  const validation = workbookImportError(values);
  const submit = async () => {
    if (disabled || importPending.current || previewing || imported) return;
    if (validation) {
      setError(validation);
      return;
    }
    importPending.current = true;
    setImporting(true);
    onBusyChange(true);
    setError('');
    try {
      const template = await request<Template>('/checklist-templates/workbook', {
        method: 'POST',
        body: workbookImportForm(values),
      });
      setImported(true);
      await onImported(template);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      importPending.current = false;
      setImporting(false);
      onBusyChange(false);
    }
  };
  const locked = disabled || importing || imported;
  return (
    <details className="settings-section workbook-import">
      <summary>Import Excel template</summary>
      <div className="settings-form">
        <label htmlFor="workbook-file">Excel workbook</label>
        <input
          id="workbook-file"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          disabled={disabled || importing}
          onChange={(event) => selectFile(event.target.files?.[0] || null)}
        />
        <button disabled={locked || !file || previewing} onClick={() => void loadPreview()}>
          {previewing ? 'Reading workbook…' : 'Preview workbook'}
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {preview && (
        <form
          className="workbook-confirmation"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <p className="workbook-source">
            <strong>{preview.source_filename}</strong> · {preview.sheet_name}
          </p>
          <p className="workbook-counts" role="status">
            {preview.counts.criteria} criteria · {preview.counts.subcontrols} sub-controls ·{' '}
            {preview.counts.controls} controls · {preview.counts.domains} domains
          </p>
          {preview.warnings.length > 0 && (
            <div className="workbook-warnings">
              <h3>Workbook warnings</h3>
              <ul>
                {preview.warnings.map((warning, index) => (
                  <li key={`${warning.code}:${index}`}>{warning.message}</li>
                ))}
              </ul>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={locked}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                I have reviewed these warnings and confirm the import.
              </label>
            </div>
          )}
          <fieldset disabled={locked} className="workbook-defaults">
            <legend>Assessment rule defaults</legend>
            <p className="muted">
              Choose how evidence must satisfy the checklist. These rules apply unless overridden
              below.
            </p>
            <label htmlFor="workbook-name">Template name</label>
            <input
              id="workbook-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={160}
              required
            />
            <label htmlFor="workbook-binding">Evidence binding</label>
            <select
              id="workbook-binding"
              value={binding}
              onChange={(event) => setBinding(event.target.value as EvidenceBinding | '')}
              required
            >
              <option value="">Choose evidence binding</option>
              <option value="corpus">Across the data room</option>
              <option value="same_document">Within the same document</option>
            </select>
            <label htmlFor="workbook-population">Document population</label>
            <select
              id="workbook-population"
              value={population}
              onChange={(event) => setPopulation(event.target.value as PopulationRule | '')}
              required
            >
              <option value="">Choose document population</option>
              <option value="any_relevant_document">Any relevant document</option>
              <option value="all_relevant_documents">Every relevant document</option>
            </select>
          </fieldset>
          <details className="workbook-rules">
            <summary>
              Assessment rules <span className="muted">· optional per sub-control</span>
            </summary>
            <div className="workbook-rules-scroll">
              <table>
                <caption className="sr-only">
                  Assessment rule overrides and expected documents for each sub-control
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Sub-control</th>
                    <th scope="col">Evidence binding</th>
                    <th scope="col">Document population</th>
                    <th scope="col">Expected documents</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.subcontrols.map((subcontrol) => (
                    <tr key={subcontrol.id}>
                      <th scope="row">
                        <span className="mono">{subcontrol.id}</span>
                        <span>{subcontrol.title}</span>
                        <small>{subcontrol.criterion_count} criteria</small>
                      </th>
                      <td>
                        <select
                          aria-label={`Evidence binding for ${subcontrol.id}`}
                          value={rules[subcontrol.id]?.evidence_binding || ''}
                          disabled={locked}
                          onChange={(event) =>
                            updateRule(subcontrol.id, 'evidence_binding', event.target.value)
                          }
                        >
                          <option value="">Use default</option>
                          <option value="corpus">Across the data room</option>
                          <option value="same_document">Same document</option>
                        </select>
                      </td>
                      <td>
                        <select
                          aria-label={`Document population for ${subcontrol.id}`}
                          value={rules[subcontrol.id]?.population_rule || ''}
                          disabled={locked}
                          onChange={(event) =>
                            updateRule(subcontrol.id, 'population_rule', event.target.value)
                          }
                        >
                          <option value="">Use default</option>
                          <option value="any_relevant_document">Any relevant document</option>
                          <option value="all_relevant_documents">Every relevant document</option>
                        </select>
                      </td>
                      <td>
                        <textarea
                          aria-label={`Expected documents for ${subcontrol.id}`}
                          value={rules[subcontrol.id]?.expected_evidence || ''}
                          disabled={locked}
                          onChange={(event) =>
                            updateRule(subcontrol.id, 'expected_evidence', event.target.value)
                          }
                          rows={2}
                          placeholder="Describe the documents expected for this sub-control."
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          {imported ? (
            <p className="notice settings-notice" role="status">
              Template imported and selected. Create a checklist from it when ready.
            </p>
          ) : (
            <>
              <p className="muted">{validation}</p>
              <button className="primary" disabled={locked || previewing || !!validation}>
                {importing ? 'Importing…' : 'Confirm and import template'}
              </button>
            </>
          )}
        </form>
      )}
    </details>
  );
}
