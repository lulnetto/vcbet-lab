function selectedConfigName() {
  return document.getElementById('analysisConfig')?.value || document.getElementById('dailyConfig')?.value || state.selectedConfig || '';
}

function operationalDate() {
  return document.getElementById('analysisDate')?.value || document.getElementById('dailyDate')?.value || state.selectedDate || todayIsoDate();
}
function fillConfigSelect(id, preferred = 'legacy_v2') {
  renderConfigSelect(id, preferred);
}

async function loadConfigs() {
  await loadEntities();
}

async function loadEntities() {
  const [configs, ledgers, runs, replays, bindings] = await Promise.all([
    fetchConfigs(),
    fetchLedgers(),
    fetchRuns(),
    fetchReplays(),
    fetchProfileLedgerBindings().catch(() => ({items: state.profileLedgerBindings || {}})),
  ]);
  state.entities.configs = configs.items || [];
  state.entities.ledgers = ledgers.items || [];
  state.entities.runs = runs.items || [];
  state.entities.replays = replays.items || [];
  state.profileLedgerBindings = bindings.items || state.profileLedgerBindings || {};
  state.entities.catalogMessages = {
    runs: runs.message || '',
    replays: replays.message || '',
  };
  state.configs = state.entities.configs.map(cfg => ({...cfg, name: cfg.name || cfg.id}));
  if (!state.selectedConfig) {
    const defaultConfig = state.configs.find(cfg => cfg.is_default) || state.configs[0];
    state.selectedConfig = defaultConfig?.name || defaultConfig?.id || 'legacy_v2';
  }
  setupEntitySelectors();
  renderReplayConfigRows(['legacy_v2']);
}

function setupEntitySelectors() {
  ['analysisDate','dailyDate','batchRunDate'].forEach(id => renderDatePicker(id));
  ['dashDateFrom','dashDateTo'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.type = 'date';
  });
  resetWalletToday(false);
  ['analysisConfig','dailyConfig'].forEach(id => fillConfigSelect(id, state.selectedConfig));
  [
    ['dashLedgerSelect', 'dashLedger'],
    ['analysisLedgerSelect', 'analysisLedger'],
    ['dailyLedgerSelect', 'dailyLedger'],
    ['closingLedgerSelect', 'closingLedger'],
    ['resultsLedgerSelect', 'resultsLedger'],
  ].forEach(([selectId, inputId]) => renderLedgerSelect(selectId, inputId));
  renderRunSelect('replaySourceRunSelect', 'replaySourceRun');
  renderReplaySelect('replaySummarySelect');
  if (typeof renderBatchProfileRows === 'function') renderBatchProfileRows();
}
async function submitJob(path, payload) {
  try {
    const res = await api(path, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    document.getElementById('actionResult').textContent = JSON.stringify(res, null, 2);
    await loadJobs();
  } catch (err) {
    document.getElementById('actionResult').textContent = `Erro: ${err.message}`;
  }
}

Object.assign(window, {
  selectedConfigName,
  operationalDate,
  fillConfigSelect,
  loadConfigs,
  loadEntities,
  setupEntitySelectors,
  submitJob,
});
