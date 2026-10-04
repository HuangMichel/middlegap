'use client';
import { useEffect, useRef, useState } from 'react';
import type { Report } from '../lib/types';
export default function ReportDialog({
  report,
  busy,
  error,
  onClose,
  onExport,
  onRegenerate,
}: {
  report: Report;
  busy: boolean;
  error: string;
  onClose: () => void;
  onExport: (draft: boolean, confirm: boolean) => Promise<void>;
  onRegenerate: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    [confirmed, setConfirmed] = useState(false);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => {
      element?.close();
      previous?.focus();
    };
  }, []);
  useEffect(() => setConfirmed(false), [report.id, report.unreviewed_count]);
  return (
    <dialog
      ref={dialog}
      className="report-dialog"
      aria-labelledby="report-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header className="drawer-header">
        <div>
          <h2 id="report-title">Gap report</h2>
        </div>
        <button onClick={onClose}>Close ×</button>
      </header>
      <div className="report-body">
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <p>
          {report.gap_count} human-confirmed gaps · {report.items.length} grouped requests
        </p>
        {!report.review_complete && (
          <div className="draft-warning">
            <strong>Review incomplete</strong>
            <p>
              {report.unreviewed_count} criteria are unreviewed. This draft should not be sent to
              the client.
            </p>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              I confirm the incomplete review and want a draft marked “DRAFT — REVIEW INCOMPLETE”.
            </label>
          </div>
        )}
        {report.items.length ? (
          report.items.map((item) => (
            <section className="report-item" key={item.id}>
              <h3>{item.title}</h3>
              <p>{item.request_text}</p>
              <details className="report-references">
                <summary>Gap references</summary>
                <p className="mono">{item.gap_ids.join(' · ')}</p>
              </details>
            </section>
          ))
        ) : (
          <section className="report-item">
            <h3>No confirmed gaps</h3>
            <p>
              No criterion currently has a final human “No” determination. The PDF will state that
              there are no confirmed gaps.
            </p>
          </section>
        )}
      </div>
      <footer className="report-footer">
        <button disabled={busy} onClick={() => void onRegenerate()}>
          Regenerate report
        </button>
        <button
          disabled={busy || (!report.review_complete && !confirmed)}
          onClick={() => void onExport(true, confirmed)}
        >
          {busy ? 'Preparing…' : 'Download draft PDF'}
        </button>
        <button
          className="primary"
          disabled={busy || !report.review_complete}
          onClick={() => void onExport(false, false)}
        >
          Download final PDF
        </button>
      </footer>
    </dialog>
  );
}
