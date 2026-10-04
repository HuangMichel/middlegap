import test from 'node:test';
import assert from 'node:assert/strict';
import { formatScore } from '../lib/score';

test('workbook fractions render as percentages including weighted sub-control achievement', () => {
  assert.equal(formatScore(0.625, 1, 'criteria_engine_v1'), '62.5%');
  assert.equal(formatScore(1, 1, 'criteria_engine_v1'), '100.0%');
  assert.equal(formatScore(0, 1, 'criteria_engine_v1'), '0.0%');
  assert.equal(formatScore(0.15, 0.3, 'criteria_engine_v1'), '50.0%');
  assert.equal(formatScore(0, 0, 'criteria_engine_v1'), 'N/A');
});

test('legacy templates keep weighted point display', () => {
  assert.equal(formatScore(7.5, 10), '7.5 / 10.0');
  assert.equal(formatScore(0, 0), '0.0 / 0.0');
});
