async function loadTeamRegistry(forceReload = false) {
  const statusEl = document.getElementById('teamRegistryStatus');
  const summaryEl = document.getElementById('teamRegistrySummary');
  state.teamRegistry.loading = true;
  state.teamRegistry.error = '';
  if (forceReload && statusEl) statusEl.textContent = 'Carregando registry...';
  try {
    const [pendingPayload, approvedPayload] = await Promise.all([
      fetchTeamRegistryPending(),
      fetchTeamRegistryApproved(),
    ]);
    const leaguesPayload = await fetchTeamRegistryLeagues();
    state.teamRegistry.pending = pendingPayload.items || [];
    state.teamRegistry.approved = approvedPayload.items || [];
    state.teamRegistry.leagues = leaguesPayload.items || [];
    state.teamRegistry.pendingByLeague = pendingPayload.by_league || {};
    state.teamRegistry.approvedByLeague = approvedPayload.by_league || {};
    state.teamRegistry.error = '';
    delete state.loadErrors.teamRegistry;
    if (summaryEl) summaryEl.innerHTML = renderTeamRegistrySummary(state.teamRegistry);
    if (statusEl) {
      statusEl.textContent = JSON.stringify({
        pending_file: pendingPayload.file,
        pending_total: pendingPayload.total,
        approved_file: approvedPayload.file,
        approved_total: approvedPayload.total,
        last_sync: state.teamRegistry.syncResult,
      }, null, 2);
    }
    renderTeamRegistryLeagueSelect();
    renderTeamRegistryReview();
  } catch (err) {
    state.teamRegistry.pending = [];
    state.teamRegistry.approved = [];
    state.teamRegistry.error = err.message;
    state.loadErrors.teamRegistry = err.message;
    if (summaryEl) summaryEl.innerHTML = '<div class="state-box"><strong>Registry não carregado.</strong>Veja o erro no status.</div>';
    if (statusEl) statusEl.textContent = `Registry não verificado: ${err.message}`;
    renderTeamRegistryReview();
  } finally {
    state.teamRegistry.loading = false;
    renderTodayCockpit();
  }
}

function renderTeamRegistryLeagueSelect() {
  const el = document.getElementById('teamRegistryLeague');
  if (!el) return;
  const current = el.value || state.teamRegistry.selectedLeague;
  el.innerHTML = '';
  if (!state.teamRegistry.leagues.length) {
    el.innerHTML = '<option value="">Nenhuma liga configurada</option>';
    return;
  }
  state.teamRegistry.leagues.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.name || item.id || '';
    opt.textContent = `${item.label || item.name} | pend=${item.pending_count || 0} | aprov=${item.approved_count || 0}`;
    el.appendChild(opt);
  });
  if ([...el.options].some(o => o.value === current)) el.value = current;
  state.teamRegistry.selectedLeague = el.value;
  el.onchange = () => { state.teamRegistry.selectedLeague = el.value; };
}

async function syncSelectedTeamRegistryLeague(league = null) {
  const selected = league || document.getElementById('teamRegistryLeague')?.value || state.teamRegistry.selectedLeague;
  if (!selected || state.teamRegistry.syncing) return;
  const statusEl = document.getElementById('teamRegistryStatus');
  state.teamRegistry.syncing = true;
  setRegistrySyncButtons(true);
  if (statusEl) statusEl.textContent = `Sincronizando ${selected}...`;
  try {
    const result = await syncTeamRegistry({league: selected, source: 'configured_url'});
    state.teamRegistry.syncResult = result;
    if (statusEl) statusEl.textContent = JSON.stringify(result, null, 2);
  } catch (err) {
    state.teamRegistry.syncResult = {league: selected, status: 'error', error: err.message};
    if (statusEl) statusEl.textContent = `Erro ao sincronizar ${selected}: ${err.message}`;
  }
  state.teamRegistry.syncing = false;
  setRegistrySyncButtons(false);
  await loadTeamRegistry(false);
}

async function syncAllTeamRegistryLeagues() {
  if (state.teamRegistry.syncing) return;
  const statusEl = document.getElementById('teamRegistryStatus');
  state.teamRegistry.syncing = true;
  setRegistrySyncButtons(true);
  if (statusEl) statusEl.textContent = 'Sincronizando todas as ligas configuradas...';
  try {
    const result = await syncAllTeamRegistry({});
    state.teamRegistry.syncResult = result;
    const failed = result.failed || [];
    if (statusEl) statusEl.textContent = JSON.stringify({
      status: result.status,
      total: result.total,
      failed: failed.map(item => ({league: item.league, coverage_status: item.coverage_status, debug_reason: item.debug_reason || item.error || '', debug_artifact: item.debug_artifact || ''})),
      items: result.items,
    }, null, 2);
  } catch (err) {
    state.teamRegistry.syncResult = {status: 'error', error: err.message};
    if (statusEl) statusEl.textContent = `Erro ao sincronizar todas as ligas: ${err.message}`;
  }
  state.teamRegistry.syncing = false;
  setRegistrySyncButtons(false);
  await loadTeamRegistry(false);
}

function setRegistrySyncButtons(disabled) {
  ['teamRegistrySyncLeagueBtn', 'teamRegistrySyncAllBtn'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = disabled;
  });
}

function renderTeamRegistryReview() {
  const items = state.teamRegistry.pending || [];
  const countEl = document.getElementById('teamRegistryPendingCount');
  const emptyEl = document.getElementById('teamRegistryEmptyState');
  const wrapEl = document.getElementById('teamRegistryTableWrap');
  if (countEl) countEl.textContent = `${items.length} pendência(s)`;
  if (!items.length) {
    if (emptyEl) emptyEl.style.display = 'block';
    if (wrapEl) wrapEl.style.display = 'none';
    const table = document.getElementById('tableTeamRegistryPending');
    if (table) table.innerHTML = '';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';
  if (wrapEl) wrapEl.style.display = 'block';
  renderTeamRegistryPendingTable(items);
}

function registryPayloadAt(index, useEdited = false) {
  const item = state.teamRegistry.pending?.[index];
  if (!item) return null;
  const selected = document.querySelector(`.registry-candidate-select[data-registry-index="${index}"]`)?.value || '';
  const edited = document.querySelector(`.registry-footy-input[data-registry-index="${index}"]`)?.value || '';
  return {
    league: item.league || '',
    betano_name: item.betano_name || '',
    betano_team_id: item.betano_team_id || '',
    betano_url: item.betano_url || '',
    suggested_footystats_name: item.suggested_footystats_name || '',
    footystats_name: (useEdited ? edited : (selected || item.suggested_footystats_name || edited)).trim(),
    top_score: item.top_score || '',
    review_reason: item.review_reason || '',
    ambiguous_options: item.ambiguous_options || '',
    source: item.source || 'ui_review',
    coverage_status: item.coverage_status || '',
  };
}

function removeRegistryPendingAt(index) {
  if (!Array.isArray(state.teamRegistry.pending)) return;
  state.teamRegistry.pending.splice(index, 1);
  renderTeamRegistryReview();

  const summaryEl = document.getElementById('teamRegistrySummary');
  if (summaryEl) summaryEl.innerHTML = renderTeamRegistrySummary(state.teamRegistry);

  const statusEl = document.getElementById('teamRegistryStatus');
  if (statusEl) {
    statusEl.textContent = JSON.stringify({
      pending_total: state.teamRegistry.pending.length,
      approved_total: state.teamRegistry.approved.length,
      last_action: 'registry_row_resolved',
      last_sync: state.teamRegistry.syncResult,
    }, null, 2);
  }
}

function preserveScroll(fn) {
  const y = window.scrollY;
  return Promise.resolve()
    .then(fn)
    .finally(() => window.scrollTo(0, y));
}

async function approveRegistrySuggestion(index) {
  const payload = registryPayloadAt(index, false);
  if (!payload || !payload.footystats_name) return;

  try {
    addManualOverrideIfNeeded(payload, index);
    await approveTeamRegistryAlias(payload);
    removeRegistryPendingAt(index);
  } catch (err) {
    const statusEl = document.getElementById('teamRegistryStatus');
    if (statusEl) statusEl.textContent = `Erro ao aprovar alias: ${err.message}`;
  }
}

async function approveRegistryEdited(index) {
  const payload = registryPayloadAt(index, true);
  if (!payload || !payload.footystats_name) return;

  try {
    addManualOverrideIfNeeded(payload, index);
    await updateTeamRegistryAlias({...payload, suggested_footystats_name: payload.footystats_name});
    await approveTeamRegistryAlias(payload);
    removeRegistryPendingAt(index);
  } catch (err) {
    const statusEl = document.getElementById('teamRegistryStatus');
    if (statusEl) statusEl.textContent = `Erro ao editar/aprovar alias: ${err.message}`;
  }
}

function addManualOverrideIfNeeded(payload, index) {
  const item = state.teamRegistry.pending?.[index];
  if (item?.manual_override_required !== 'true') return;
  const reason = window.prompt('Score baixo: informe a justificativa de override manual para aprovar.');
  if (!reason) throw new Error('Override manual cancelado.');
  payload.manual_override = true;
  payload.manual_override_reason = reason;
}

async function rejectRegistryAlias(index) {
  const payload = registryPayloadAt(index, true);
  if (!payload) return;

  try {
    await rejectTeamRegistryAlias({...payload, status: 'rejected'});
    removeRegistryPendingAt(index);
  } catch (err) {
    const statusEl = document.getElementById('teamRegistryStatus');
    if (statusEl) statusEl.textContent = `Erro ao rejeitar alias: ${err.message}`;
  }
}

Object.assign(window, {
  loadTeamRegistry,
  renderTeamRegistryLeagueSelect,
  syncSelectedTeamRegistryLeague,
  syncAllTeamRegistryLeagues,
  setRegistrySyncButtons,
  renderTeamRegistryReview,
  registryPayloadAt,
  removeRegistryPendingAt,
  preserveScroll,
  approveRegistrySuggestion,
  approveRegistryEdited,
  addManualOverrideIfNeeded,
  rejectRegistryAlias,
});
