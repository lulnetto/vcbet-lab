async function submitAnalysis() {
  await submitJob('/jobs/analysis', {
    mode: document.getElementById('analysisMode').value,
    date: document.getElementById('analysisDate').value || null,
    ledger_file: document.getElementById('analysisLedger').value,
    config_name: document.getElementById('analysisConfig').value,
    xg_source: document.getElementById('analysisXgSource').value,
    debug: document.getElementById('analysisDebug').checked,
    dry_run: document.getElementById('analysisDryRun').checked,
  });
}

async function submitDailyRun() {
  await submitJob('/jobs/daily-run', {
    date: document.getElementById('dailyDate').value || null,
    ledger_file: document.getElementById('dailyLedger').value,
    results_file: document.getElementById('dailyResults').value,
    config_name: document.getElementById('dailyConfig').value,
    xg_source: document.getElementById('dailyXgSource').value,
    debug: document.getElementById('dailyDebug').checked,
    skip_results_collection: document.getElementById('skipResults').checked,
    skip_settlement: document.getElementById('skipSettlement').checked,
    skip_closing_odds: true,
    refresh_catalogs: document.getElementById('dailyRefreshCatalogs').checked,
  });
}

async function submitClosingOdds() {
  await submitJob('/jobs/closing-odds', {
    ledger_file: document.getElementById('closingLedger').value,
    window_minutes: Number(document.getElementById('closingWindow').value || 20),
    allow_past_minutes: Number(document.getElementById('closingPast').value || 10),
    all_pending: document.getElementById('closingAllPending').checked,
  });
}

async function submitResultsCollection() {
  await submitJob('/jobs/results-collection', {
    ledger_file: document.getElementById('resultsLedger').value,
    output_file: document.getElementById('resultsFile').value,
    grace_minutes: Number(document.getElementById('resultsGrace').value || 110),
    max_pages: Number(document.getElementById('resultsMaxPages').value || 6),
    all_pending: document.getElementById('resultsAllPending').checked,
    debug: document.getElementById('resultsDebug').checked,
    source: document.getElementById('resultsSource').value || null,
  });
}

async function submitSettlement() {
  await submitJob('/jobs/settlement', {
    ledger_file: document.getElementById('resultsLedger').value,
    results_file: document.getElementById('resultsFile').value,
    overrides_file: document.getElementById('settlementOverrides').value || null,
  });
}

async function submitResultsSettlement() {
  await submitJob('/jobs/results-settlement-cycle', {
    ledger_file: document.getElementById('resultsLedger').value,
    results_file: document.getElementById('resultsFile').value,
    overrides_file: document.getElementById('settlementOverrides').value || null,
    all_pending: document.getElementById('resultsAllPending').checked,
    results_grace_minutes: Number(document.getElementById('resultsGrace').value || 110),
    results_max_pages: Number(document.getElementById('resultsMaxPages').value || 6),
    results_debug: document.getElementById('resultsDebug').checked,
    results_source: document.getElementById('resultsSource').value || null,
  });
}
function formatJob(job) {
  const req = job.request || {};
  const config = req.config_name ? ` | config=${req.config_name}` : '';
  const replayCfg = req.configs ? ` | configs=${req.configs.join(',')}` : '';
  const canCancel = ['queued','running'].includes(job.status);
  const canDelete = !canCancel;
  const cancelButton = canCancel ? `<button class="danger small" onclick="cancelJob('${escapeHtml(job.id)}')">cancelar</button>` : '';
  const deleteButton = canDelete ? `<button class="danger small" onclick="deleteJob('${escapeHtml(job.id)}')">deletar</button>` : '';
  const failed = ['failed','error'].includes(String(job.status || '').toLowerCase());
  const requestBits = [
    req.target_date ? `data=${req.target_date}` : '',
    req.source_run_dir ? `run=${req.source_run_dir}` : '',
    config.trim(),
    replayCfg.trim(),
  ].filter(Boolean).join(' | ');
  const phases = (job.phases || []).map(phase => `${phase.name}:${phase.status}`).join(' | ');
  return `<div class="job ${failed ? 'job-failed' : statusClass(job.status)}">
    <div class="inline"><strong>${escapeHtml(job.title)}</strong>${statusPill(job.status)}<span class="muted">${escapeHtml(job.id)}</span></div>
    <div class="job-context"><strong>${escapeHtml(jobActionContext(job))}</strong><span>${escapeHtml(job.job_type || '-')}</span></div>
    ${requestBits ? `<div class="muted">${escapeHtml(requestBits)}</div>` : ''}
    ${phases ? `<div class="muted">fases: ${escapeHtml(phases)}</div>` : ''}
    <div class="inline" style="margin-top:8px;">
      <button class="ghost small" onclick="viewLogs('${escapeHtml(job.id)}')">logs</button>
      ${cancelButton}
      ${deleteButton}
    </div></div>`;
}

function renderJobsPage() {
  const root = document.getElementById('jobsList');
  if (!root) return;
  const total = state.jobs.length;
  const totalPages = Math.max(1, Math.ceil(total / state.jobsPageSize));
  state.jobsPage = Math.min(Math.max(1, state.jobsPage), totalPages);
  const start = (state.jobsPage - 1) * state.jobsPageSize;
  const visible = state.jobs.slice(start, start + state.jobsPageSize);
  const info = document.getElementById('jobsPageInfo');
  if (info) info.textContent = `Página ${state.jobsPage}/${totalPages} · ${total} job(s)`;
  root.innerHTML = visible.map(formatJob).join('') || '<div class="state-box"><strong>Nenhum job recente.</strong>Quando você rodar uma análise, daily run, replay ou coleta, o andamento aparecerá aqui com acesso aos logs.</div>';
}

function nextJobsPage() {
  const totalPages = Math.max(1, Math.ceil(state.jobs.length / state.jobsPageSize));
  if (state.jobsPage < totalPages) {
    state.jobsPage += 1;
    renderJobsPage();
  }
}

function previousJobsPage() {
  if (state.jobsPage > 1) {
    state.jobsPage -= 1;
    renderJobsPage();
  }
}

async function loadJobs() {
  try {
    const payload = await api('/jobs?limit=100');
    state.jobs = payload.items || [];
    delete state.loadErrors.jobs;
    renderJobsPage();
  } catch (err) {
    state.jobs = [];
    state.loadErrors.jobs = err.message;
    document.getElementById('jobsList').innerHTML = '<div class="state-box"><strong>Monitor não verificado.</strong>Não foi possível carregar jobs nesta atualização.</div>';
  }
  renderTodayCockpit();
}

async function viewLogs(jobId) {
  state.selectedJobId = jobId;
  const res = await fetch(`/jobs/${jobId}/logs?lines=1400`);
  const text = await res.text();
  const el = document.getElementById('jobLogs');
  el.textContent = text || 'Sem logs.';
  el.scrollTop = el.scrollHeight;
}

async function reloadSelectedLogs() {
  if (!state.selectedJobId) return;
  await viewLogs(state.selectedJobId);
}

async function cancelJob(jobId) {
  await api(`/jobs/${jobId}/cancel`, { method:'POST' });
  await loadJobs();
}

async function deleteJob(jobId) {
  if (!confirm('Deletar este job permanentemente?')) return;
  await api(`/jobs/${jobId}`, { method:'DELETE' });
  await loadJobs();
}

async function cleanupFailedJobs() {
  if (!confirm('Remover todos os jobs com erro finalizados?')) return;
  await api('/jobs/cleanup-failed', { method:'POST' });
  await loadJobs();
}

Object.assign(window, {
  submitAnalysis,
  submitDailyRun,
  submitClosingOdds,
  submitResultsCollection,
  submitSettlement,
  submitResultsSettlement,
  formatJob,
  renderJobsPage,
  nextJobsPage,
  previousJobsPage,
  loadJobs,
  viewLogs,
  reloadSelectedLogs,
  cancelJob,
  deleteJob,
  cleanupFailedJobs,
});
