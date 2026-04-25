function bindTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.onclick = () => switchTab(btn.dataset.tab);
  });
}

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(x => x.classList.toggle('active', x.dataset.tab === tab));
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  const target = document.getElementById(`tab-${tab}`);
  if (target) target.classList.add('active');
}

function bindOperationalInputs() {
  ['analysisDate','dailyDate','analysisConfig','dailyConfig'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.onchange = renderTodayCockpit;
  });
}

function startAutoRefresh() {
  setInterval(async () => {
    try { await loadJobs(); } catch {}
  }, 5000);
  setInterval(async () => {
    if (!state.selectedJobId) return;
    const selected = state.jobs.find(job => job.id === state.selectedJobId);
    const running = selected && ['queued','running'].includes(selected.status);
    document.getElementById('logsAutoState').textContent = running ? 'auto 2s' : 'parado';
    if (running) {
      try { await reloadSelectedLogs(); } catch {}
    }
  }, 2000);
}

async function loadHealth() {
  const payload = await api('/health');
  document.getElementById('healthText').textContent = `online | root=${payload.project_root}`;
}

async function boot() {
  bindTabs();
  document.getElementById('aliasIncludeBlocked').onchange = () => loadAliasFiles(true);
  await loadHealth();
  await loadConfigs();
  bindOperationalInputs();
  await refreshTodayCockpit();
  startAutoRefresh();
}

boot();
