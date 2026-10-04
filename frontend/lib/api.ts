export const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
    cache: 'no-store',
  }).catch(() => {
    throw new Error(
      'Unable to reach the assessment service. Check the backend connection and retry.',
    );
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === 'string'
        ? body.detail
        : `Request failed (${response.status}). Please retry.`,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export async function downloadReport(id: string, draft: boolean, confirmed: boolean) {
  const response = await fetch(`${API}/reports/${id}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft, confirm_incomplete: confirmed }),
  }).catch(() => {
    throw new Error('Unable to reach the report service. Check the backend connection and retry.');
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === 'string'
        ? body.detail
        : 'Export failed. Regenerate the report and try again.',
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `middlegap-${draft ? 'draft' : 'final'}-${id}.pdf`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
