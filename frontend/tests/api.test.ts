import test from 'node:test';
import assert from 'node:assert/strict';
import { request } from '../lib/api';

test('an unavailable service produces a recovery message rather than substitute data', async (context) => {
  context.mock.method(globalThis, 'fetch', async () => {
    throw new TypeError('Failed to fetch');
  });
  await assert.rejects(request('/health'), /Unable to reach the assessment service.*retry/);
});

test('backend configuration failures remain visible to the reviewer', async (context) => {
  context.mock.method(globalThis, 'fetch', async () =>
    Response.json({ detail: 'Supabase configuration is incomplete.' }, { status: 503 }),
  );
  await assert.rejects(request('/workspaces'), /Supabase configuration is incomplete/);
});
