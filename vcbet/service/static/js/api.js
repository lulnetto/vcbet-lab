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

function fetchConfigPresets() {
  return api('/api/config-presets');
}

function fetchConfigPreset(name) {
  return api(`/api/config-presets/${encodeURIComponent(name)}`);
}

function createConfigPreset(payload) {
  return api('/api/config-presets', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
}

function saveConfigPreset(name, payload) {
  return api(`/api/config-presets/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
}

function validateConfigPreset(name, payload) {
  return api(`/api/config-presets/${encodeURIComponent(name)}/validate`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
}

function cloneConfigPreset(name, payload) {
  return api(`/api/config-presets/${encodeURIComponent(name)}/clone`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
}

function deleteConfigPreset(name) {
  return api(`/api/config-presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
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

function fetchTeamRegistryPending() {
  return api('/api/team-registry/pending');
}

function fetchTeamRegistryApproved() {
  return api('/api/team-registry/approved');
}

function fetchTeamRegistryLeagues() {
  return api('/api/team-registry/leagues');
}

function syncTeamRegistry(payload) {
  return api('/api/team-registry/sync', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
}

function syncAllTeamRegistry(payload = {}) {
  return api('/api/team-registry/sync-all', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
}

function approveTeamRegistryAlias(payload) {
  return api('/api/team-registry/approve', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
}

function rejectTeamRegistryAlias(payload) {
  return api('/api/team-registry/reject', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
}

function updateTeamRegistryAlias(payload) {
  return api('/api/team-registry/update', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
}
