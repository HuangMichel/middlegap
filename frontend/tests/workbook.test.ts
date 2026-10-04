import test from 'node:test';
import assert from 'node:assert/strict';
import { PreviewRequests, workbookImportError, workbookImportForm } from '../lib/workbook';
import type { WorkbookPreview, WorkbookImportValues } from '../lib/workbook';

const file = new File(['workbook bytes'], 'checklist.xlsx');
const preview: WorkbookPreview = {
  preview_hash: 'immutable-preview-hash',
  source_filename: file.name,
  sheet_name: 'Criteria_Engine',
  counts: { domains: 10, controls: 24, subcontrols: 80, criteria: 188 },
  warnings: [{ code: 'missing_rules', message: 'Assessment rules must be specified.' }],
  subcontrols: [
    {
      id: 'SC01',
      domain_id: 'D01',
      control_id: 'S01',
      title: 'Privacy notice',
      weight: 1,
      criterion_count: 2,
      source_rows: [6, 7],
    },
  ],
};
const values: WorkbookImportValues = {
  file,
  preview,
  name: 'Legal checklist',
  binding: 'corpus',
  population: 'any_relevant_document',
  confirmWarnings: true,
  rules: {},
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

test('an earlier preview cannot replace the later workbook or expose its error', async () => {
  const requests = new PreviewRequests(),
    earlier = deferred<string>(),
    later = deferred<string>();
  let displayed = '';
  const first = requests.resolve(requests.begin(), earlier.promise, (value) => {
    displayed = value;
  });
  requests.invalidate();
  const second = requests.resolve(requests.begin(), later.promise, (value) => {
    displayed = value;
  });
  later.resolve('current workbook');
  assert.equal(await second, true);
  earlier.resolve('previous workbook');
  assert.equal(await first, false);
  assert.equal(displayed, 'current workbook');
  const obsolete = deferred<string>();
  const rejected = requests.resolve(requests.begin(), obsolete.promise, (value) => {
    displayed = value;
  });
  requests.invalidate();
  obsolete.reject(new Error('previous workbook failed'));
  assert.equal(await rejected, false);
  assert.equal(displayed, 'current workbook');
});

test('import requires the current preview, both explicit rule defaults and warning confirmation', () => {
  assert.match(workbookImportError({ ...values, preview: null })!, /Preview this workbook/);
  assert.match(
    workbookImportError({ ...values, file: new File(['new bytes'], 'other.xlsx') })!,
    /Preview this workbook/,
  );
  assert.match(workbookImportError({ ...values, binding: '' })!, /both assessment rule defaults/);
  assert.match(
    workbookImportError({ ...values, population: '' })!,
    /both assessment rule defaults/,
  );
  assert.match(
    workbookImportError({ ...values, confirmWarnings: false })!,
    /Confirm the workbook warnings/,
  );
  assert.throws(() => workbookImportForm({ ...values, confirmWarnings: false }), /Confirm/);
  assert.equal(workbookImportError(values), null);
  assert.equal(
    workbookImportError({
      ...values,
      preview: { ...preview, warnings: [] },
      confirmWarnings: false,
    }),
    null,
  );
});

test('multipart import retains the exact file/hash and chosen per-group overrides', () => {
  const form = workbookImportForm({
    ...values,
    name: '  Legal checklist  ',
    rules: {
      SC01: {
        evidence_binding: 'same_document',
        population_rule: 'all_relevant_documents',
        expected_evidence: '  Privacy notices  ',
      },
      SC02: { expected_evidence: '  ' },
    },
  });
  assert.equal(form.get('file'), file);
  assert.equal(form.get('preview_hash'), preview.preview_hash);
  assert.equal(form.get('default_evidence_binding'), 'corpus');
  assert.equal(form.get('default_population_rule'), 'any_relevant_document');
  assert.equal(form.get('confirm_warnings'), 'true');
  assert.equal(form.get('name'), 'Legal checklist');
  assert.deepEqual(JSON.parse(String(form.get('subcontrol_rules'))), {
    SC01: {
      evidence_binding: 'same_document',
      population_rule: 'all_relevant_documents',
      expected_evidence: 'Privacy notices',
    },
  });
});
