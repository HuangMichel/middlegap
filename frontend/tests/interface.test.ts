import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReviewPane from '../components/ReviewPane';
import ReportDialog from '../components/ReportDialog';
import type { Criterion, Subcontrol, Result, Evidence, Report } from '../lib/types';

const criterion: Criterion = {
  id: 'c1',
  number: 1,
  text: 'Retention period is included',
  gap_phrasing: 'Provide retention information',
  key_terms: ['retention'],
  legal_references: ['Article 13'],
  expected_evidence: 'Privacy notice',
  applicability_condition: null,
};
const subcontrol: Subcontrol = {
  id: 's1',
  code: 'D.03.SC01',
  title: 'Required clauses',
  weight: 10,
  evidence_binding: 'same_document',
  population_rule: 'all_relevant_documents',
  criteria: [criterion],
};
const evidence: Evidence = {
  id: 'e1',
  document_id: 'd1',
  original_filename: 'notice.pdf',
  classification: 'supports',
  confidence_signal: 'strong_evidence',
  quoted_passage: 'Records are retained for seven years.',
  ai_explanation: 'The passage specifies a period.',
  review_status: 'unreviewed',
  anchors: [
    { page_number: 1, text: 'seven years', x0: 0.1, y0: 0.2, x1: 0.7, y1: 0.3, sort_order: 1 },
  ],
};
const result: Result = {
  id: 'r1',
  criterion_id: 'c1',
  criterion_code: 'C1',
  criterion_text: criterion.text,
  subcontrol_id: 's1',
  ai_state: 'fulfilled',
  confidence_signal: 'strong_evidence',
  ai_explanation: 'The notice contains a retention period.',
  gap_id: null,
  document_results: [],
  evidence: [evidence],
  review: null,
};
const noop = async () => {};
function renderReview(value: Result) {
  return renderToStaticMarkup(
    createElement(ReviewPane, {
      criterion,
      subcontrol,
      result: value,
      busy: false,
      onEvidence: noop,
      onSource: () => {},
      onSave: noop,
    }),
  );
}
function buttonDisabled(html: string, label: string) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = html.match(new RegExp(`<button([^>]*)>\\s*${escaped}\\s*</button>`));
  assert.ok(match, `${label} must remain available`);
  return /\bdisabled=/.test(match[1]);
}

test('compact review still requires every citation to be reviewed and offers original sources', () => {
  const html = renderReview({
    ...result,
    evidence: [evidence, { ...evidence, id: 'e2', review_status: 'accepted' }],
  });
  assert.equal(buttonDisabled(html, 'Save determination'), true);
  assert.equal((html.match(/>Open source<\/button>/g) || []).length, 2);
  assert.match(html, /Accept or reject every citation/);
  assert.match(html, /<details class="criterion-context"><summary>Criterion details/);
  assert.doesNotMatch(html, /<details[^>]*\bopen=/);
});

test('reviewed supporting evidence allows finalization while unsupported decisions require rationale', () => {
  assert.equal(
    buttonDisabled(
      renderReview({ ...result, evidence: [{ ...evidence, review_status: 'accepted' }] }),
      'Save determination',
    ),
    false,
  );
  const unsupported = renderReview({ ...result, evidence: [] });
  assert.equal(buttonDisabled(unsupported, 'Save determination'), true);
  assert.match(unsupported, /Override rationale/);
  assert.match(unsupported, /<textarea/);
  assert.equal(
    buttonDisabled(
      renderReview({ ...result, ai_state: 'analysis_failed', evidence: [] }),
      'Save determination',
    ),
    true,
  );
});

test('incomplete report keeps both export gates and explicit draft confirmation', () => {
  const report: Report = {
    id: 'report1',
    run_id: 'run1',
    status: 'ready',
    review_complete: false,
    unreviewed_count: 3,
    gap_count: 0,
    items: [],
  };
  const html = renderToStaticMarkup(
    createElement(ReportDialog, {
      report,
      busy: false,
      error: '',
      onClose: () => {},
      onExport: noop,
      onRegenerate: noop,
    }),
  );
  assert.equal(buttonDisabled(html, 'Download final PDF'), true);
  assert.equal(buttonDisabled(html, 'Download draft PDF'), true);
  assert.match(html, /I confirm the incomplete review/);
  assert.match(html, /No confirmed gaps/);
});
