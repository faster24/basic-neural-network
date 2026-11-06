// JSON POST to the Flask API (auth travels in the __session cookie). Throws Error(message) on failure.
export async function post(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (res.status === 401) {
    location.reload(); // token expired: page reload re-runs sign-in
    throw new Error('Signing in again…');
  }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

// Fire-and-forget event that survives page unload.
export function beacon(path, body) {
  const blob = new Blob([JSON.stringify(body)], { type: 'application/json' });
  if (!navigator.sendBeacon?.(path, blob)) {
    fetch(path, { method: 'POST', body: blob, keepalive: true }).catch(() => {});
  }
}
