function qs(params) {
  const url = new URLSearchParams();
  Object.entries(params).forEach(([k,v]) => {
    if (v === '' || v === null || v === undefined) return;
    url.set(k, v);
  });
  return url.toString();
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const text = await res.text();
  let payload;
  try { payload = text ? JSON.parse(text) : {}; } catch { payload = text; }
  if (!res.ok) {
    const detail = typeof payload === 'object' ? (payload.detail || JSON.stringify(payload)) : payload;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return payload;
}

function fetchConfigs() {
  return api('/api/entities/configs');
}

function fetchLedgers() {
  return api('/api/entities/ledgers');
}

function fetchRuns() {
  return api('/api/entities/runs?limit=300');
}

function fetchReplays() {
  return api('/api/entities/replays?limit=300');
}
