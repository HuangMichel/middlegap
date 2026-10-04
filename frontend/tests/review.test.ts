import test from 'node:test';
import assert from 'node:assert/strict';
import { requiresOverride, reviewBlockReason } from '../lib/review';
import type { Result, Evidence } from '../lib/types';
const result: Result = {
  id: '1',
  criterion_id: 'c',
  criterion_code: 'C1',
  criterion_text: 'retention',
  subcontrol_id: 's',
  ai_state: 'fulfilled',
  confidence_signal: 'strong_evidence',
  ai_explanation: '',
  gap_id: null,
  document_results: [],
  evidence: [],
  review: null,
};
const evidence: Evidence = {
  id: 'e',
  document_id: 'd',
  original_filename: 'a.pdf',
  classification: 'supports',
  confidence_signal: 'strong_evidence',
  quoted_passage: 'text',
  ai_explanation: '',
  review_status: 'unreviewed',
  anchors: [],
};
test('all citations must be individually reviewed; technical failure is never finalizable', () => {
  assert.match(reviewBlockReason({ ...result, evidence: [evidence] })!, /every citation/);
  assert.equal(
    reviewBlockReason({ ...result, evidence: [{ ...evidence, review_status: 'rejected' }] }),
    null,
  );
  assert.match(reviewBlockReason({ ...result, ai_state: 'analysis_failed' })!, /Retry/);
});
test('Yes requires accepted supporting evidence and an AI match', () => {
  assert.equal(requiresOverride(result, 'Yes'), true);
  assert.equal(
    requiresOverride({ ...result, evidence: [{ ...evidence, review_status: 'accepted' }] }, 'Yes'),
    false,
  );
  assert.equal(
    requiresOverride(
      {
        ...result,
        evidence: [{ ...evidence, review_status: 'accepted', classification: 'contextual' }],
      },
      'Yes',
    ),
    true,
  );
  assert.equal(
    requiresOverride(
      { ...result, ai_state: 'conflict', evidence: [{ ...evidence, review_status: 'accepted' }] },
      'Yes',
    ),
    true,
  );
  assert.equal(requiresOverride({ ...result, ai_state: 'gap' }, 'N/A'), true);
});
