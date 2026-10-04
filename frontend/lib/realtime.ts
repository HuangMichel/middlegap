/** Public progress channel only. API reads remain the source of truth. */
export function subscribeProgress(
  url: string,
  anonKey: string,
  runId: string,
  onChange: () => void,
  onStatus: (live: boolean) => void,
): () => void {
  let socket: WebSocket;
  try {
    const endpoint = new URL('/realtime/v1/websocket', url);
    endpoint.protocol = endpoint.protocol === 'https:' ? 'wss:' : 'ws:';
    endpoint.searchParams.set('apikey', anonKey);
    endpoint.searchParams.set('vsn', '1.0.0');
    socket = new WebSocket(endpoint);
  } catch {
    onStatus(false);
    return () => {};
  }
  let ref = 1;
  const topic = `realtime:assessment-${runId}`;
  const send = (event: string, payload: unknown, channel = topic) => {
    if (socket.readyState === WebSocket.OPEN)
      socket.send(JSON.stringify({ topic: channel, event, payload, ref: String(ref++) }));
  };
  socket.onopen = () =>
    send('phx_join', {
      config: {
        broadcast: { ack: false, self: false },
        presence: { key: '' },
        postgres_changes: [
          {
            event: '*',
            schema: 'public',
            table: 'assessment_progress',
            filter: `run_id=eq.${runId}`,
          },
        ],
        private: false,
      },
      access_token: anonKey,
    });
  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.event === 'phx_reply' && message.ref === '1')
        onStatus(message.payload?.status === 'ok');
      if (message.event === 'postgres_changes') onChange();
      if (message.event === 'system' && message.payload?.status === 'error') onStatus(false);
    } catch {
      onStatus(false);
    }
  };
  socket.onerror = () => onStatus(false);
  socket.onclose = () => onStatus(false);
  const heartbeat = setInterval(() => send('heartbeat', {}, 'phoenix'), 25000);
  return () => {
    clearInterval(heartbeat);
    socket.onclose = null;
    send('phx_leave', {});
    socket.close();
  };
}
