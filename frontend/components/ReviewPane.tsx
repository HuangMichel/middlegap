'use client';
import { useEffect, useState } from 'react';
import type { Criterion, Subcontrol, Result, Evidence, FinalValue } from '../lib/types';
import {
  stateLabels,
  formatList,
  requiresOverride,
  reviewBlockReason,
  suggestedValue,
} from '../lib/review';
export function Status({ state }: { state: string }) {
  return (
    <span className={`status status-${state}`}>
      {stateLabels[state as keyof typeof stateLabels] || state.replaceAll('_', ' ')}
    </span>
  );
}
export default function ReviewPane({
  criterion,
  subcontrol,
  result,
  busy,
  onEvidence,
  onSource,
  onSave,
  population,
}: {
  criterion: Criterion;
  subcontrol: Subcontrol;
  result: Result | null;
  busy: boolean;
  onEvidence: (e: Evidence, status: 'accepted' | 'rejected') => Promise<void>;
  onSource: (e: Evidence) => void;
  onSave: (r: Result, value: FinalValue, override: boolean, note: string) => Promise<void>;
  population?: React.ReactNode;
}) {
  const [value, setValue] = useState<FinalValue>('Yes'),
    [note, setNote] = useState(''),
    [forceOverride, setForceOverride] = useState(false);
  useEffect(() => {
    setValue(result?.review?.final_value || suggestedValue(result?.ai_state || 'pending') || 'Yes');
    setNote(result?.review?.override_note || '');
    setForceOverride(result?.review?.decision_type === 'override');
  }, [
    result?.id,
    result?.ai_state,
    result?.review?.reviewed_at,
    result?.review?.final_value,
    result?.review?.override_note,
    result?.review?.decision_type,
  ]);
  const block = reviewBlockReason(result),
    override = !!result && (requiresOverride(result, value) || forceOverride);
  return (
    <article className="criterion-pane">
      <div className="criterion-header">
        <div className="criterion-code mono">
          {subcontrol.code} · C{criterion.number}
        </div>
        <h1>{criterion.text}</h1>
      </div>
      <details className="criterion-context">
        <summary>Criterion details</summary>
        <dl>
          <dt>Sub-control</dt>
          <dd>{subcontrol.title}</dd>
          <dt>Evidence binding</dt>
          <dd>
            {subcontrol.evidence_binding === 'same_document'
              ? 'Clauses must coexist in one document'
              : 'Evidence across the data room'}
          </dd>
          <dt>Document population</dt>
          <dd>
            {subcontrol.population_rule === 'all_relevant_documents'
              ? 'Every relevant document'
              : 'Any relevant document'}
          </dd>
          <dt>Expected evidence</dt>
          <dd>{formatList(criterion.expected_evidence)}</dd>
          <dt>Search hints</dt>
          <dd>{formatList(criterion.key_terms)}</dd>
          <dt>Legal references · traceability only</dt>
          <dd>{formatList(criterion.legal_references)}</dd>
          <dt>Applicability condition</dt>
          <dd>{criterion.applicability_condition || 'No explicit condition configured'}</dd>
        </dl>
      </details>
      <section className="ai-findings" aria-labelledby="ai-title">
        <div className="section-heading">
          <h2 id="ai-title">Assessment</h2>
          <Status state={result?.ai_state || 'pending'} />
        </div>
        {result ? (
          <>
            {result.ai_state !== 'pending' && result.ai_state !== 'analysis_failed' && (
              <p className="confidence">{result.confidence_signal.replaceAll('_', ' ')}</p>
            )}
            <p>
              {result.ai_state === 'pending'
                ? 'Assessment in progress.'
                : result.ai_state === 'gap'
                  ? 'No sufficient evidence was found in the provided data room.'
                  : result.ai_explanation}
            </p>
            {result.ai_state === 'analysis_failed' && (
              <p className="error">Retry the failed analysis before making a determination.</p>
            )}
          </>
        ) : (
          <p className="muted">Run an assessment to find evidence.</p>
        )}
      </section>
      {population}
      <section className="evidence-section" aria-labelledby="evidence-title">
        <div className="section-heading">
          <h2 id="evidence-title">Citations</h2>
          <span className="muted">{result?.evidence.length || 0}</span>
        </div>
        {result?.evidence.length ? (
          result.evidence.map((evidence) => (
            <article
              className={`evidence-item evidence-${evidence.review_status}`}
              key={evidence.id}
            >
              <header>
                <div>
                  <strong>{evidence.original_filename}</strong>
                  <p className="mono">
                    {evidence.anchors.length
                      ? `Page ${Array.from(new Set(evidence.anchors.map((a) => a.page_number))).join(', ')}`
                      : 'Source anchor unavailable'}
                  </p>
                </div>
                <span className={`tag evidence-class-${evidence.classification}`}>
                  {evidence.classification}
                </span>
              </header>
              <blockquote>{evidence.quoted_passage}</blockquote>
              <details className="citation-details">
                <summary>Citation details</summary>
                <p>{evidence.ai_explanation}</p>
                <p className="confidence">{evidence.confidence_signal.replaceAll('_', ' ')}</p>
              </details>
              <footer>
                <button onClick={() => onSource(evidence)}>Open source</button>
                <div className="citation-actions">
                  <span className="review-label">
                    {evidence.review_status === 'unreviewed'
                      ? 'Needs review'
                      : evidence.review_status}
                  </span>
                  <button
                    disabled={busy}
                    className={evidence.review_status === 'accepted' ? 'accepted' : ''}
                    aria-pressed={evidence.review_status === 'accepted'}
                    onClick={() => void onEvidence(evidence, 'accepted')}
                  >
                    Accept
                  </button>
                  <button
                    disabled={busy}
                    className={evidence.review_status === 'rejected' ? 'rejected' : ''}
                    aria-pressed={evidence.review_status === 'rejected'}
                    onClick={() => void onEvidence(evidence, 'rejected')}
                  >
                    Reject
                  </button>
                </div>
              </footer>
            </article>
          ))
        ) : (
          <p className="empty-inline">
            {result && result.ai_state !== 'pending'
              ? 'No citations found in this data room.'
              : 'Citations will appear as assessment progresses.'}
          </p>
        )}
      </section>
      <section className="human-review" aria-labelledby="review-title">
        <div className="section-heading">
          <h2 id="review-title">Final determination</h2>
          {result?.review && (
            <span className="status status-reviewed">Saved · {result.review.final_value}</span>
          )}
        </div>
        <fieldset disabled={busy || !!block}>
          <legend className="sr-only">Final value</legend>
          <div className="decision-options">
            {(['Yes', 'No', 'N/A'] as FinalValue[]).map((option) => (
              <label key={option} className={value === option ? 'selected' : ''}>
                <input
                  type="radio"
                  name="final-value"
                  value={option}
                  checked={value === option}
                  onChange={() => setValue(option)}
                />
                {option}
              </label>
            ))}
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={forceOverride}
              onChange={(event) => setForceOverride(event.target.checked)}
            />
            Record a human override
          </label>
          {override && (
            <label className="field-label">
              Override rationale <span>Required</span>
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Explain your decision."
                rows={3}
              />
            </label>
          )}
        </fieldset>
        {block && <p className="review-guidance">{block}</p>}
        <button
          className="primary"
          disabled={busy || !!block || (override && !note.trim())}
          onClick={() => result && void onSave(result, value, override, note)}
        >
          {busy ? 'Saving…' : 'Save determination'}
        </button>
        {result?.review?.override_note && (
          <p className="human-note">
            <strong>Human note:</strong> {result.review.override_note}
          </p>
        )}
      </section>
    </article>
  );
}
