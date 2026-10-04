// Acceptance against the explicitly isolated API and separate-worker harness.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium } = require('playwright');
const api = process.env.SMOKE_API_URL || 'http://127.0.0.1:8000';
const ui = process.env.SMOKE_UI_URL || 'http://127.0.0.1:3000';
const output = resolve(process.env.SMOKE_ARTIFACT_DIR || 'artifacts/browser');
await mkdir(output, { recursive: true });
const errors = [],
  failedRequests = [],
  checks = [];
let browser, context, page, run, failure;
const waitFor = async (test, label) => {
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline) {
    if (await test()) return;
    await new Promise((done) => setTimeout(done, 250));
  }
  throw new Error(`Timeout: ${label}`);
};
const get = async (path) => {
  const response = await page.request.get(api + path);
  assert(response.ok(), `${path}: ${response.status()}`);
  return response.json();
};
const downloadPDF = async (button, filename) => {
  const pending = page.waitForEvent('download');
  await button.click();
  const download = await pending;
  assert.equal(await download.failure(), null);
  const path = resolve(output, filename);
  await download.saveAs(path);
  const bytes = await readFile(path);
  assert.equal(bytes.subarray(0, 5).toString(), '%PDF-');
  const pdfjs = await import(pathToFileURL(require.resolve('pdfjs-dist/legacy/build/pdf.mjs')));
  const pdf = await pdfjs.getDocument({ data: new Uint8Array(bytes), useSystemFonts: true })
    .promise;
  try {
    const text = [];
    for (let n = 1; n <= pdf.numPages; n++) {
      const content = await (await pdf.getPage(n)).getTextContent();
      text.push(content.items.map((item) => item.str || '').join(' '));
    }
    return text.join('\n');
  } finally {
    await pdf.destroy();
  }
};
try {
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.tracing.start({ screenshots: true, snapshots: true });
  page = await context.newPage();
  page.setDefaultTimeout(45000);
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('requestfailed', (request) =>
    failedRequests.push({ url: request.url(), error: request.failure()?.errorText }),
  );
  const health = await get('/health');
  assert.equal(health.test_harness, true, 'Browser acceptance requires isolated test harness');
  assert.equal(
    health.ai_provider,
    'synthetic',
    'Never claim live Mistral acceptance from fixtures',
  );
  await page.goto(ui, { waitUntil: 'networkidle' });
  await page
    .getByLabel('Workspace', { exact: true })
    .selectOption({ label: 'Integration legal data room' });
  await page
    .locator('.workspace-bar')
    .getByRole('button', { name: 'Workspace settings', exact: true })
    .click();
  await page.getByText('Create checklist from template', { exact: true }).click();
  await page.getByRole('button', { name: 'Create checklist', exact: true }).click();
  await page.getByRole('button', { name: 'Close workspace settings' }).click();
  const started = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      /\/checklists\/[^/]+\/assessment-runs$/.test(new URL(response.url()).pathname),
  );
  await page.getByRole('button', { name: /Run assessment/ }).click();
  const response = await started;
  assert(response.ok(), 'Assessment start');
  run = await response.json();
  await waitFor(async () => {
    run = await get(`/assessment-runs/${run.id}`);
    return ['completed', 'completed_with_errors', 'failed'].includes(run.status);
  }, 'separate worker completes assessment');
  assert.equal(run.status, 'completed');
  assert.equal(run.processed_criteria, 4);
  assert.equal(run.snapshot_documents.length, 2);
  await waitFor(
    async () =>
      (await page.locator('.population-panel tbody tr').count()) === 2 &&
      (await page.locator('.evidence-item').count()) > 0,
    'assessment appears in UI',
  );
  checks.push('real UI/API/separate-worker flow with synthetic providers');
  for (const selector of ['.run-audit', '.criterion-context', '.population-panel']) {
    assert.equal(
      await page.locator(selector).getAttribute('open'),
      null,
      `${selector} initially closed`,
    );
  }
  await page.locator('.population-panel > summary').click();
  await page.screenshot({ path: resolve(output, 'document-population.png'), fullPage: true });
  await page.locator('.population-panel > summary').click();
  checks.push('two-document population and secondary disclosures');

  const results = await get(`/assessment-runs/${run.id}/results`);
  const first = results.find((result) => result.criterion_text === 'Legal basis is included');
  assert(first?.evidence.length > 0, 'Fixture must exercise citation gate');
  const save = page.getByRole('button', { name: 'Save determination', exact: true });
  assert(await save.isDisabled(), 'Unreviewed citations disable human finalization');
  const blocked = await page.request.put(`${api}/criterion-results/${first.id}/review`, {
    data: { final_value: 'Yes', decision_type: 'verified_ai', override_note: null },
  });
  assert.equal(blocked.status(), 409, 'Backend also enforces citation gate');
  checks.push('UI and backend citation gate');

  const source = page.getByRole('button', { name: 'Open source', exact: true }).first();
  await source.click();
  await waitFor(
    async () =>
      (await page.locator('.pdf-scroll').getAttribute('aria-busy')) === 'false' &&
      (await page.locator('.pdf-highlight').count()) > 0,
    'source page render',
  );
  assert.equal(await page.locator('.source-drawer .error').count(), 0);
  const rendered = await page.locator('.pdf-page').evaluate((element) => {
    const canvas = element.querySelector('canvas');
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0,
      paper = 0;
    for (let offset = 0; offset < pixels.length; offset += 4) {
      if (pixels[offset + 3] > 0) {
        if (pixels[offset] < 180 && pixels[offset + 1] < 180 && pixels[offset + 2] < 180) ink++;
        if (pixels[offset] > 240 && pixels[offset + 1] > 240 && pixels[offset + 2] > 240) paper++;
      }
    }
    const parent = element.getBoundingClientRect();
    return {
      width: canvas.width,
      height: canvas.height,
      ink,
      paper,
      highlights: Array.from(element.querySelectorAll('.pdf-highlight')).map((highlight) => {
        const bounds = highlight.getBoundingClientRect();
        return {
          x0: (bounds.left - parent.left) / parent.width,
          y0: (bounds.top - parent.top) / parent.height,
          x1: (bounds.right - parent.left) / parent.width,
          y1: (bounds.bottom - parent.top) / parent.height,
        };
      }),
    };
  });
  assert(
    rendered.width > 100 && rendered.height > 100 && rendered.ink > 100 && rendered.paper > 1000,
    'Canvas contains rendered PDF text and page pixels',
  );
  const anchors = first.evidence[0].anchors.filter(
    (anchor) => anchor.page_number === first.evidence[0].anchors[0].page_number,
  );
  assert.equal(rendered.highlights.length, anchors.length);
  for (const [index, anchor] of anchors.entries()) {
    for (const coordinate of ['x0', 'y0', 'x1', 'y1'])
      assert(
        Math.abs(rendered.highlights[index][coordinate] - anchor[coordinate]) < 0.003,
        `Highlight ${index} ${coordinate} matches stored normalized source anchor`,
      );
  }
  await writeFile(resolve(output, 'source-render.json'), JSON.stringify(rendered, null, 2));
  await page.screenshot({ path: resolve(output, 'source-highlight.png'), fullPage: true });
  await page.keyboard.press('Escape');
  await page.locator('.source-drawer').waitFor({ state: 'detached' });
  assert(
    await source.evaluate((element) => element === globalThis.document.activeElement),
    'Source drawer restores keyboard focus',
  );
  checks.push(
    'nonblank PDF canvas, normalized anchor geometry, keyboard close and focus restoration',
  );

  await page.getByRole('button', { name: 'Gap report', exact: true }).click();
  const report = page.locator('.report-dialog');
  const draft = report.getByRole('button', { name: 'Download draft PDF', exact: true });
  assert(await draft.isDisabled(), 'Incomplete draft requires explicit confirmation');
  assert(
    await report.getByRole('button', { name: 'Download final PDF', exact: true }).isDisabled(),
    'Incomplete final is disabled',
  );
  await report.getByRole('checkbox', { name: /I confirm the incomplete review/ }).check();
  const draftText = await downloadPDF(draft, 'incomplete-draft.pdf');
  assert.match(draftText, /DRAFT\s*[—–-]\s*REVIEW INCOMPLETE/);
  assert.match(draftText, /No human-confirmed documentary gaps/i);
  await page.screenshot({
    path: resolve(output, 'incomplete-draft-confirmation.png'),
    fullPage: true,
  });
  await page.keyboard.press('Escape');
  checks.push('incomplete draft explicit confirmation, PDF banner and zero-gap content');

  const names = [
    'Legal basis is included',
    'Purpose of processing is included',
    'Retention period is included',
    'Controller contact is included',
  ];
  for (const name of names) {
    await page
      .locator('.checklist-index')
      .getByRole('button', { name: new RegExp(name) })
      .click();
    await page.getByRole('heading', { name, exact: true }).waitFor();
    const citations = page.locator('.evidence-item');
    for (let index = 0; index < (await citations.count()); index++) {
      await citations.nth(index).getByRole('button', { name: 'Accept', exact: true }).click();
      await waitFor(
        async () =>
          (await citations
            .nth(index)
            .getByRole('button', { name: 'Accept', exact: true })
            .getAttribute('aria-pressed')) === 'true',
        'citation accepted',
      );
    }
    const value = name.includes('Retention') ? 'No' : 'Yes';
    await page.getByRole('radio', { name: value, exact: true }).check();
    await save.click();
    await page.getByText(`Saved · ${value}`, { exact: true }).waitFor();
  }
  await waitFor(
    async () => !(await page.locator('.score-overview').textContent()).includes('Provisional'),
    'final human score',
  );
  run = await get(`/assessment-runs/${run.id}`);
  assert.equal(run.reviewed_criteria, 4);
  assert.equal(run.score.provisional, false);
  assert.equal(run.score.total_score / run.score.max_score, 0.75);
  checks.push('four human determinations and deterministic 75 percent score');

  await page
    .locator('.checklist-index')
    .getByRole('button', { name: /Legal basis is included/ })
    .click();
  await page.getByText('Saved · Yes', { exact: true }).waitFor();
  await page
    .locator('.evidence-item')
    .first()
    .getByRole('button', { name: 'Reject', exact: true })
    .click();
  await waitFor(
    async () =>
      (await page.getByText('Saved · Yes', { exact: true }).count()) === 0 &&
      (await page.locator('.score-overview').textContent()).includes('Provisional'),
    'citation change invalidates human decision',
  );
  const invalidated = (await get(`/assessment-runs/${run.id}/results`)).find(
    (result) => result.id === first.id,
  );
  assert.equal(invalidated.review, null);
  assert.equal(invalidated.ai_state, first.ai_state);
  await page
    .locator('.evidence-item')
    .first()
    .getByRole('button', { name: 'Accept', exact: true })
    .click();
  await waitFor(async () => !(await save.isDisabled()), 'citation reaccepted');
  await save.click();
  await page.getByText('Saved · Yes', { exact: true }).waitFor();
  checks.push('citation changes invalidate dependent human review and preserve AI conclusion');

  await page.getByRole('button', { name: 'Gap report', exact: true }).click();
  const finalText = await downloadPDF(
    report.getByRole('button', { name: 'Download final PDF', exact: true }),
    'verified-gap-report.pdf',
  );
  assert.doesNotMatch(finalText, /REVIEW INCOMPLETE/);
  assert.match(finalText, /retention/i);
  await page.keyboard.press('Escape');
  await page.screenshot({ path: resolve(output, 'reconciliation-desktop.png'), fullPage: true });
  checks.push('final PDF contains human-confirmed retention gap');

  await page.setViewportSize({ width: 390, height: 844 });
  const browse = page.getByRole('button', { name: 'Browse checklist', exact: true });
  await browse.click();
  await page
    .locator('.checklist-index')
    .getByRole('button', { name: /Retention period is included/ })
    .click();
  await page.getByRole('heading', { name: 'Retention period is included', exact: true }).waitFor();
  assert(await browse.isVisible(), 'Mobile checklist closes after criterion navigation');
  assert.equal(
    await page.evaluate(
      () => globalThis.document.documentElement.scrollWidth > globalThis.innerWidth + 1,
    ),
    false,
    'No mobile page horizontal overflow',
  );
  await page.screenshot({ path: resolve(output, 'reconciliation-mobile.png'), fullPage: true });
  await page.locator('.checklist-index').waitFor({ state: 'hidden' });
  await browse.click();
  await page
    .locator('.checklist-index')
    .getByRole('button', { name: /Legal basis is included/ })
    .click();
  await page.getByRole('button', { name: 'Open source', exact: true }).first().click();
  await waitFor(
    async () => (await page.locator('.pdf-scroll').getAttribute('aria-busy')) === 'false',
    'mobile PDF render',
  );
  assert.equal(await page.locator('.source-drawer .error').count(), 0);
  await page.screenshot({ path: resolve(output, 'source-mobile.png'), fullPage: true });
  await page.keyboard.press('Escape');
  checks.push('mobile checklist navigation and source drawer');
  assert.deepEqual(errors, [], 'No browser page errors');
  console.log(`Browser integration passed; artifacts in ${output}`);
} catch (error) {
  failure = error;
  if (page) {
    await page.screenshot({ path: resolve(output, 'failure.png'), fullPage: true }).catch(() => {});
    await writeFile(resolve(output, 'failure.html'), await page.content().catch(() => '')).catch(
      () => {},
    );
  }
} finally {
  await context?.tracing.stop({ path: resolve(output, 'trace.zip') }).catch(() => {});
  await browser?.close();
  await writeFile(
    resolve(output, 'verification.json'),
    JSON.stringify(
      {
        status: failure ? 'failed' : 'passed',
        checks,
        api,
        ui,
        scope:
          'isolated synthetic provider harness; live Supabase/Mistral/MCP and original workbook parity are not established',
        error: failure?.stack,
        browserErrors: errors,
        failedRequests,
      },
      null,
      2,
    ),
  );
}
if (failure) throw failure;
