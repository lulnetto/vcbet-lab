function renderNextAction() {
  const action = getNextAction();
  const el = document.getElementById('nextActionText');
  if (el) el.textContent = action.text;
  const btn = document.getElementById('nextActionButton');
  if (btn) {
    btn.textContent = action.button;
    btn.onclick = action.handler;
  }
}

function selectedConfigName() {
  return document.getElementById('analysisConfig')?.value || document.getElementById('dailyConfig')?.value || state.selectedConfig || '';
}

function operationalDate() {
  return document.getElementById('analysisDate')?.value || document.getElementById('dailyDate')?.value || state.selectedDate || todayIsoDate();
}

function aliasPendingCount() {
  const runDiagnostics = state.aliasFiles.reduce((sum, item) => sum + Number(item.status_counts?.pending_review || 0) + Number(item.status_counts?.blocked || 0), 0);
  return runDiagnostics + Number(state.teamRegistry?.pending?.length || 0);
}

function hasRunForOperationalDate() {
  const date = operationalDate();
  return (state.entities.runs || state.replayRuns).some(item => item.target_date === date || String(item.run_id || '').includes(date.replaceAll('-', '')));
}

function dashboardSummary() {
  return state.dashboard?.summary || {};
}

function getNextAction() {
  const running = state.jobs.some(job => ['queued','running'].includes(job.status));
  const aliases = aliasPendingCount();
  const summary = dashboardSummary();
  const hasPicks = Number(summary.total_entries || 0) > 0 || hasRunForOperationalDate();
  const open = Number(summary.open_entries || 0);
  if (running) return { text:'Acompanhar job em execução. Aguarde a rotina terminar antes de disparar outra etapa.', button:'Abrir Monitor', handler:() => switchTab('jobs') };
  if (aliases) return { text:`Revisar pendências de Qualidade de Dados: ${aliases} alias(es) aguardando decisão.`, button:'Revisar qualidade', handler:() => switchTab('aliases') };
  if (!hasPicks) return { text:'Gerar/Atualizar análise do dia. Ainda não há run/picks verificados para o contexto atual.', button:'Gerar análise', handler:() => document.getElementById('analysisDate')?.focus() };
  if (open) return { text:`Atualizar resultados e liquidar. Há ${open} pick(s) abertas no filtro atual.`, button:'Resultados + settlement', handler:() => document.getElementById('resultsGrace')?.focus() };
  return { text:'Revisar Carteira. Dados carregados e nenhuma pendência bloqueante foi detectada.', button:'Ir para Carteira', handler:() => switchTab('dashboard') };
}

function todayStatus() {
  if (state.jobs.some(job => ['queued','running'].includes(job.status))) return statusPill('rodando');
  if (aliasPendingCount()) return statusPill('atenção');
  if (state.loadErrors.dashboard || state.loadErrors.jobs || state.loadErrors.aliases) return statusPill('parcial');
  if (Number(dashboardSummary().total_entries || 0) > 0 || hasRunForOperationalDate()) return statusPill('ok');
  return statusPill('pendente');
}

function renderTodayCockpit() {
  const summary = dashboardSummary();
  const running = state.jobs.some(job => ['queued','running'].includes(job.status));
  const failedJobs = state.jobs.filter(job => ['failed','error'].includes(job.status)).length;
  const aliases = aliasPendingCount();
  const total = Number(summary.total_entries || 0);
  const open = Number(summary.open_entries || 0);
  const settled = Number(summary.settled_entries || 0);
  const clvCount = Number(state.dashboard?.clv?.count || 0);
  const incompleteReplay = state.replaySummaries.some(item => ['incomplete','blocked','bad'].some(x => String(item.replay_quality_status || item.temporal_contract_status || '').toLowerCase().includes(x)));
  const warningItems = [];
  if (aliases) warningItems.push(`${aliases} alias(es) pendente(s) em Qualidade de Dados.`);
  if (failedJobs) warningItems.push(`${failedJobs} job(s) com erro no Monitor.`);
  if (state.loadErrors.dashboard) warningItems.push('Carteira não verificada nesta carga.');
  if (state.loadErrors.replay) warningItems.push('Replay Lab não verificado nesta carga.');
  if (incompleteReplay) warningItems.push('Há replay com qualidade ou contrato temporal fraco/incompleto.');
  if (!total && !state.loadErrors.dashboard) warningItems.push('Nenhuma pick disponível no filtro atual.');

  document.getElementById('todayDate').textContent = formatPtDate(operationalDate()) || 'não selecionada';
  document.getElementById('todayConfig').textContent = selectedConfigName() || 'não verificada';
  document.getElementById('todayStatus').innerHTML = todayStatus();
  document.getElementById('todayRefresh').textContent = state.lastRefreshAt ? formatLocalDateTime(state.lastRefreshAt) : 'não carregado';
  document.getElementById('pipelineMeta').textContent = Object.keys(state.loadErrors).length ? 'estado parcial' : 'dados carregados';

  document.getElementById('todayPipeline').innerHTML = [
    pipelineStep('Análise do dia', running ? 'rodando' : (total || hasRunForOperationalDate() ? 'ok' : 'pendente'), total ? `${total} pick(s) no filtro atual da carteira.` : 'Sem picks verificadas no contexto atual.', 'Gerar/Atualizar', "document.getElementById('analysisDate')?.focus()"),
    pipelineStep('Closing odds', running ? 'rodando' : (clvCount ? 'ok' : (total ? 'atenção' : 'indisponível')), clvCount ? `${clvCount} entrada(s) com closing odds.` : (total ? 'Watcher/tick manual via Manutenção quando houver event_url.' : 'Depende de picks/ledger carregados.'), '', ''),
    pipelineStep('Resultados + settlement', running ? 'rodando' : (open ? 'atenção' : (settled ? 'ok' : 'pendente')), open ? `${open} pick(s) aberta(s) podem precisar de resultado e liquidação.` : (settled ? `${settled} entrada(s) liquidadas.` : 'Sem resultado/settlement verificado.'), 'Atualizar e liquidar', "document.getElementById('resultsGrace')?.focus()"),
    pipelineStep('Revisão', aliases || failedJobs ? 'atenção' : (total ? 'ok' : 'pendente'), aliases || failedJobs ? 'Existem pendências antes da revisão final.' : (total ? 'Carteira pronta para revisão operacional.' : 'Aguardando análise do dia.'), 'Carteira', "switchTab('dashboard')")
  ].join('');

  const pendingRows = [
    ['Aliases pendentes', state.loadErrors.aliases ? 'não verificado' : String(aliases)],
    ['Jobs com erro', state.loadErrors.jobs ? 'não verificado' : String(failedJobs)],
    ['Picks abertas', state.loadErrors.dashboard ? 'não verificado' : String(open)],
    ['Resultados pendentes', state.loadErrors.dashboard ? 'não verificado' : (open ? String(open) : '0')],
    ['Replay/diagnóstico', state.loadErrors.replay ? 'não verificado' : (incompleteReplay ? 'atenção' : (state.replaySummaries.length ? 'ok' : 'não verificado'))],
  ];
  const warningsEl = document.getElementById('todayWarnings');
  if (warningsEl) warningsEl.innerHTML = warningList(warningItems);
  document.getElementById('todayPending').innerHTML = pendingRows.map(([label, value]) => `<div class="summary-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('');

  const flags = (state.dashboard?.breakdowns?.by_flag || []).slice(0, 3).map(row => `${row.bucket}: ${row.picks}`).join(', ') || 'sem flags no filtro';
  document.getElementById('todayWallet').innerHTML = [
    ['Total de picks', state.loadErrors.dashboard ? 'não verificado' : String(total)],
    ['Abertas', state.loadErrors.dashboard ? 'não verificado' : String(open)],
    ['Liquidadas', state.loadErrors.dashboard ? 'não verificado' : String(settled)],
    ['Alertas/flags', state.loadErrors.dashboard ? 'não verificado' : flags],
  ].map(([label, value]) => `<div class="summary-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('');

  const relevantJobs = state.jobs.slice(0, 4);
  document.getElementById('todayJobs').innerHTML = state.loadErrors.jobs
    ? '<div class="state-box"><strong>Jobs não verificados.</strong>O restante do cockpit continua disponível.</div>'
    : (relevantJobs.map(job => `<div class="compact-job ${statusClass(job.status)}"><div class="inline"><strong>${escapeHtml(job.title)}</strong>${statusPill(job.status)}</div><div class="muted">${escapeHtml(jobActionContext(job))} | ${escapeHtml(job.job_type)} | ${escapeHtml(job.id)}</div></div>`).join('') || '<div class="state-box"><strong>Nenhum job recente.</strong>Abra o Monitor para acompanhar novas execuções.</div>');
  renderNextAction();
}

function fillConfigSelect(id, preferred = 'legacy_v2') {
  renderConfigSelect(id, preferred);
}

async function loadConfigs() {
  await loadEntities();
}

async function loadEntities() {
  const [configs, ledgers, runs, replays] = await Promise.all([
    fetchConfigs(),
    fetchLedgers(),
    fetchRuns(),
    fetchReplays(),
  ]);
  state.entities.configs = configs.items || [];
  state.entities.ledgers = ledgers.items || [];
  state.entities.runs = runs.items || [];
  state.entities.replays = replays.items || [];
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
  ['analysisDate','dailyDate'].forEach(id => renderDatePicker(id));
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
}

function resetWalletToday(reload = true, force = true) {
  const date = operationalDate();
  const from = document.getElementById('dashDateFrom');
  const to = document.getElementById('dashDateTo');
  if (from && (force || !from.value)) from.value = date;
  if (to && (force || !to.value)) to.value = date;
  if (reload) loadDashboard();
}

function showWalletHistory() {
  const from = document.getElementById('dashDateFrom');
  const to = document.getElementById('dashDateTo');
  if (from) from.value = '';
  if (to) to.value = '';
  loadDashboard();
}

function dashboardParams() {
  return {
    ledger_file: document.getElementById('dashLedger').value,
    run_id: document.getElementById('dashRun').value,
    league: document.getElementById('dashLeague').value,
    market_type: document.getElementById('dashMarket').value,
    date_from: document.getElementById('dashDateFrom').value,
    date_to: document.getElementById('dashDateTo').value,
    only_executed: document.getElementById('dashExecuted').checked,
    only_settled: document.getElementById('dashSettled').checked,
  };
}

async function loadDashboard() {
  try {
    const payload = await api(`/dashboard/summary?${qs(dashboardParams())}`);
    state.dashboard = payload;
    delete state.loadErrors.dashboard;
    renderKpis(payload.summary, payload.clv);
    renderTable('tableMarket', payload.breakdowns.by_market, [
      {key:'bucket', label:'Mercado'}, {key:'picks', label:'Picks'}, {key:'units_model', label:'Unid'}, {key:'roi_model_percent', label:'ROI %'}
    ]);
    renderTable('tableOdd', payload.breakdowns.by_odd_bucket, [
      {key:'bucket', label:'Faixa'}, {key:'picks', label:'Picks'}, {key:'units_model', label:'Unid'}, {key:'roi_model_percent', label:'ROI %'}
    ]);
    renderTable('tableStake', payload.breakdowns.by_stake_bucket, [
      {key:'bucket', label:'Faixa'}, {key:'picks', label:'Picks'}, {key:'units_model', label:'Unid'}, {key:'roi_model_percent', label:'ROI %'}
    ]);
    renderTable('tableFlag', payload.breakdowns.by_flag, [
      {key:'bucket', label:'Flag'}, {key:'picks', label:'Picks'}, {key:'units_model', label:'Unid'}, {key:'roi_model_percent', label:'ROI %'}
    ]);

    const filters = payload.filters || {};
    fillSelect('dashRun', filters.available_runs || [], true);
    fillSelect('dashLeague', filters.available_leagues || [], true);
    fillSelect('dashMarket', filters.available_markets || [], true);
    await loadEntries();
  } catch (err) {
    state.dashboard = null;
    state.loadErrors.dashboard = err.message;
    document.getElementById('actionResult').textContent = `Erro dashboard: ${err.message}`;
    renderTodayCockpit();
  }
}

async function loadEntries() {
  try {
    const payload = await api(`/dashboard/entries?${qs({...dashboardParams(), limit: 300})}`);
    state.dashboardEntries = payload.items || [];
    delete state.loadErrors.entries;
    const rows = (payload.items || []).map((row, idx) => ({
      ...row,
      warning_html: warningList(pickWarnings(row), 'sem aviso'),
      status_html: statusPill(row.final_settlement_status || row.pick_safety_status || row.candidate_stage),
      inspect: pickDetailButton('dashboard', idx),
      details: rowDetails(row, 'Avançado')
    }));
    renderTable('tableEntries', rows, [
      {key:'match_datetime', label:'Jogo em', format:v => formatLocalDateTime(v)},
      {key:'league', label:'Liga'}, {key:'match_name', label:'Jogo'}, {key:'market_type', label:'Mercado'},
      {key:'selection_raw', label:'Seleção'}, {key:'line', label:'Linha'}, {key:'odd_entrada', label:'Odd'},
      {key:'ev_percent', label:'EV %'}, {key:'confidence_score', label:'Conf.'}, {key:'stake_units', label:'Stake'},
      {key:'status_html', label:'Status', html:true}, {key:'warning_html', label:'Avisos', html:true}, {key:'inspect', label:'', html:true}, {key:'details', label:'', html:true},
    ], 'Sem picks ou entradas para os filtros atuais. Ajuste filtros, selecione outra run ou rode uma análise em Hoje.');
    renderTodayCockpit();
  } catch (err) {
    state.loadErrors.entries = err.message;
    document.getElementById('actionResult').textContent = `Erro entries: ${err.message}`;
    renderTodayCockpit();
  }
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

async function submitAnalysis() {
  await submitJob('/jobs/analysis', {
    mode: document.getElementById('analysisMode').value,
    date: document.getElementById('analysisDate').value || null,
    ledger_file: document.getElementById('analysisLedger').value,
    config_name: document.getElementById('analysisConfig').value,
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

function renderReplayConfigRows(selected = []) {
  const root = document.getElementById('replayConfigRows');
  root.innerHTML = '';
  const initial = selected.length ? selected : ['legacy_v2'];
  initial.forEach(name => addReplayConfigField(name));
}

function addReplayConfigField(selected = '') {
  const root = document.getElementById('replayConfigRows');
  const max = state.configs.length || 1;
  if (root.children.length >= max) return;
  const div = document.createElement('div');
  div.className = 'config-row';
  const select = document.createElement('select');
  select.className = 'replay-config-select';
  state.configs.forEach(cfg => {
    const opt = document.createElement('option');
    opt.value = cfg.name;
    opt.textContent = `${cfg.label} (${cfg.name})`;
    if (cfg.name === selected) opt.selected = true;
    select.appendChild(opt);
  });
  const remove = document.createElement('button');
  remove.className = 'ghost';
  remove.textContent = 'remover';
  remove.onclick = () => div.remove();
  div.appendChild(select);
  div.appendChild(remove);
  root.appendChild(div);
}

async function loadReplayRuns() {
  try {
    const payload = await fetchRuns();
    state.entities.runs = payload.items || [];
    state.entities.catalogMessages.runs = payload.message || '';
    state.replayRuns = state.entities.runs;
    delete state.loadErrors.runs;
    renderRunSelect('replaySourceRunSelect', 'replaySourceRun');
  } catch (err) {
    state.loadErrors.runs = err.message;
  }
  renderTodayCockpit();
}

async function loadReplaySummaries() {
  try {
    const entities = await fetchReplays();
    state.entities.replays = entities.items || [];
    state.entities.catalogMessages.replays = entities.message || '';
    renderReplaySelect('replaySummarySelect');
    const payload = await api('/replays/summaries?limit=80');
    state.replaySummaries = payload.items || [];
    delete state.loadErrors.replay;
    renderTable('tableReplaySummaries', state.replaySummaries.map((item, idx) => ({
      ...item,
      quality_html: statusPill(item.replay_quality_status),
      temporal_html: statusPill(item.temporal_contract_status),
      configs_text: (item.configs || []).join(', '),
      limitations_text: (item.replay_limitations || []).join(', '),
      action: `<button class="ghost small" onclick="loadReplaySummaryDetail(${idx})">abrir</button>`
    })), [
      {key:'target_date', label:'Data'}, {key:'source_run_id', label:'Run'}, {key:'quality_html', label:'Qualidade', html:true}, {key:'temporal_html', label:'Temporal', html:true}, {key:'configs_text', label:'Configs'}, {key:'results_count', label:'Picks'}, {key:'action', label:'', html:true}
    ], state.entities.catalogMessages.replays || 'Ainda não há dados de replay. Rode um replay a partir de uma run histórica para comparar configs.');
  } catch (err) {
    state.loadErrors.replay = err.message;
    renderTable('tableReplaySummaries', [], [
      {key:'target_date', label:'Data'}, {key:'source_run_id', label:'Run'}, {key:'quality_html', label:'Qualidade', html:true}
    ], 'Replay não verificado nesta carga.');
  }
  renderTodayCockpit();
}

async function openSelectedReplaySummary() {
  const selected = document.getElementById('replaySummarySelect')?.value;
  if (!selected) return;
  state.selectedReplayHistory = selected;
  state.selectedReplay = selected;
  const index = state.replaySummaries.findIndex(item => item.summary_file === selected);
  if (index >= 0) {
    await loadReplaySummaryDetail(index);
    return;
  }
  const item = state.entities.replays.find(replay => replay.summary_file === selected);
  if (!item?.summary_file) return;
  const payload = await api(`/replays/summary?${qs({summary_file: item.summary_file})}`);
  renderReplaySummaryPayload(payload, item.summary_file);
}

async function loadReplaySummaryDetail(index) {
  const item = state.replaySummaries[index];
  if (!item) return;
  const payload = await api(`/replays/summary?${qs({summary_file: item.summary_file})}`);
  state.selectedReplay = item.summary_file || '';
  renderReplaySummaryPayload(payload, item.summary_file);
}

function renderReplaySummaryPayload(payload, summaryFile) {
  state.replaySummaryPayload = payload;
  const rows = (payload.results || []).map((r, idx) => {
    const st = (r.settlement && r.settlement.settlement_summary) || {};
    const sc = r.scorecard || {};
    return {
      config_name: r.config_name,
      role: sc.role || '',
      primary_candidate_status: sc.primary_candidate_status || '',
      picks_total: r.picks_total,
      precision: sc.precision_percent ?? r.comparison?.precision,
      recall: sc.recall_percent ?? r.comparison?.recall,
      jaccard: sc.jaccard_percent ?? r.comparison?.jaccard,
      drift: sc.asian_total_shifted_lines ?? r.asian_total_line_drift?.shifted_line_matches_total ?? 0,
      settled: sc.model_result_summary?.settled ?? st.settled ?? 0,
      units: sc.model_result_summary?.model_units ?? st.model_units ?? 0,
      roi: sc.model_result_summary?.model_roi_percent ?? st.model_roi_percent ?? 0,
      status_html: statusPill(sc.primary_candidate_status || r.replay_quality_status || ''),
      action: `<button class="ghost small" onclick="loadReplayPicks('${escapeHtml(summaryFile)}','${escapeHtml(r.config_name)}')">ver picks</button>`
    };
  });
  const ctx = payload.comparison_context || {};
  const replayContract = payload.replay_input_contract || {};
  const recMethod = ctx.recommendation_method || payload.recommended_configs?.method || 'manual_policy';
  const replayWarnings = [];
  const quality = payload.replay_quality_status || replayContract.replay_quality_status || '';
  const temporal = payload.temporal_contract_status || replayContract.temporal_contract_status || '';
  const strength = payload.replay_source_strength || replayContract.replay_source_strength || '';
  if (['incomplete','blocked','bad','weak'].some(x => String(quality).toLowerCase().includes(x))) replayWarnings.push(`Qualidade do replay: ${quality}`);
  if (['weak','unavailable','missing','incomplete','bad'].some(x => String(temporal).toLowerCase().includes(x))) replayWarnings.push(`Contrato temporal: ${temporal}`);
  if (['fallback','weak','missing','unavailable'].some(x => String(strength).toLowerCase().includes(x))) replayWarnings.push(`Força da fonte: ${strength}`);
  (payload.replay_limitations || replayContract.replay_limitations || []).forEach(item => replayWarnings.push(`Limitação: ${item}`));
  const selectedConfigs = (payload.results || []).map(r => r.config_name).filter(Boolean);
  const pickCounts = (payload.results || []).map(r => `${r.config_name || '-'}: ${displayValue(r.picks_total)} picks`);
  document.getElementById('replayWarnings').innerHTML = warningList(replayWarnings, 'Nenhum aviso explícito de força/qualidade no payload.');
  document.getElementById('replayComparisonBrief').innerHTML = `
    <div class="comparison-brief">
      ${detailRow('Configs selecionadas', selectedConfigs.join(', '))}
      ${detailRow('Diferença visível', pickCounts.join(' | '))}
      ${detailRow('Método de recomendação', recMethod)}
    </div>`;
  document.getElementById('replaySummaryKpis').innerHTML = `
    <div class="kpi"><div class="label">Source run</div><div class="value">${escapeHtml(payload.source_run_id || '-')}</div></div>
    <div class="kpi"><div class="label">Data</div><div class="value">${escapeHtml(payload.target_date || '-')}</div></div>
    <div class="kpi"><div class="label">Qualidade replay</div><div class="value">${escapeHtml(payload.replay_quality_status || replayContract.replay_quality_status || '-')}</div></div>
    <div class="kpi"><div class="label">Fonte replay</div><div class="value">${escapeHtml(payload.replay_source_strength || replayContract.replay_source_strength || '-')}</div></div>
    <div class="kpi"><div class="label">Temporal</div><div class="value">${escapeHtml(payload.temporal_contract_status || replayContract.temporal_contract_status || '-')}</div></div>
    <div class="kpi"><div class="label">Recomendação</div><div class="value">${escapeHtml(recMethod)}</div></div>
    <div class="kpi"><div class="label">Baseline política</div><div class="value">${escapeHtml(ctx.default_baseline_config || '-')}</div></div>
    <div class="kpi"><div class="label">Referência política</div><div class="value">${escapeHtml(ctx.conservative_reference_config || '-')}</div></div>`;
  renderTable('tableReplayResults', rows, [
    {key:'config_name', label:'Config'}, {key:'role', label:'Papel'}, {key:'status_html', label:'Status', html:true}, {key:'picks_total', label:'Picks'}, {key:'precision', label:'Precisao replay %'},
    {key:'recall', label:'Recall %'}, {key:'jaccard', label:'Jaccard %'}, {key:'drift', label:'Drift'},
    {key:'settled', label:'Settled'}, {key:'units', label:'Unid'}, {key:'roi', label:'ROI %'}, {key:'action', label:'', html:true}
  ], 'Abra um summary no histórico para visualizar a comparação de configs.');
}

async function loadReplayPicks(summaryFile, configName) {
  const payload = await api(`/replays/picks?${qs({summary_file: summaryFile, config_name: configName, limit: 400})}`);
  state.replayPicks = payload.items || [];
  document.getElementById('replayPicksMeta').textContent = `${configName} | ${payload.total} picks | fonte=${payload.source_file || '-'}`;
  const rows = (payload.items || []).map((row, idx) => ({
    ...row,
    warning_html: warningList(pickWarnings(row), 'sem aviso'),
    status_html: statusPill(row.final_bet_status || row.pick_safety_status || row.temporal_contract_status),
    inspect: pickDetailButton('replay', idx),
    details: rowDetails(row, 'Avançado')
  }));
  renderTable('tableReplayPicks', rows, [
    {key:'league', label:'Liga'}, {key:'match_name', label:'Jogo'}, {key:'market_type', label:'Mercado'},
    {key:'selection_raw', label:'Seleção'}, {key:'line', label:'Linha'}, {key:'odd_entrada', label:'Odd'},
    {key:'ev_percent', label:'EV %'}, {key:'confidence_score', label:'Conf.'}, {key:'stake_units', label:'Stake'},
    {key:'status_html', label:'Status', html:true}, {key:'warning_html', label:'Avisos', html:true}, {key:'inspect', label:'', html:true}, {key:'details', label:'', html:true}
  ], 'Este replay não retornou picks para a config selecionada. Confira a run origem ou escolha outra config.');
}

async function submitReplay() {
  const configs = [...document.querySelectorAll('.replay-config-select')].map(el => el.value).filter((v, i, arr) => v && arr.indexOf(v) === i);
  await submitJob('/jobs/replay-run', {
    source_run_dir: document.getElementById('replaySourceRun').value || document.getElementById('replaySourceRunSelect').value,
    configs,
    evaluate_results: document.getElementById('replayEvaluateResults').checked,
    results_source: document.getElementById('replayResultsSource').value || null,
  });
}

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
      failed: failed.map(item => ({league: item.league, coverage_status: item.coverage_status, error: item.error || ''})),
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

async function approveRegistrySuggestion(index) {
  const payload = registryPayloadAt(index, false);
  if (!payload || !payload.footystats_name) return;
  addManualOverrideIfNeeded(payload, index);
  await approveTeamRegistryAlias(payload);
  await loadTeamRegistry(true);
}

async function approveRegistryEdited(index) {
  const payload = registryPayloadAt(index, true);
  if (!payload || !payload.footystats_name) return;
  addManualOverrideIfNeeded(payload, index);
  await updateTeamRegistryAlias({...payload, suggested_footystats_name: payload.footystats_name});
  await approveTeamRegistryAlias(payload);
  await loadTeamRegistry(true);
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
  await rejectTeamRegistryAlias({...payload, status: 'rejected'});
  await loadTeamRegistry(true);
}

async function loadAliasFiles(forceReload = false) {
  try {
    const includeBlocked = document.getElementById('aliasIncludeBlocked').checked;
    const scope = document.getElementById('aliasDiagnosticScope')?.value || state.aliasDiagnostics.scope || 'runs_recent';
    const includeResolved = Boolean(document.getElementById('aliasIncludeResolved')?.checked);
    state.aliasDiagnostics.scope = scope;
    state.aliasDiagnostics.includeResolved = includeResolved;
    const payload = await api(`/aliases/files?${qs({include_blocked: includeBlocked, scope, include_resolved: includeResolved})}`);
    state.aliasFiles = payload.items || [];
    delete state.loadErrors.aliases;
    const select = document.getElementById('aliasPendingFile');
    const current = forceReload ? '' : select.value;
    select.innerHTML = '';
    if (!state.aliasFiles.length) {
      select.innerHTML = '<option value="">Sem aliases pendentes</option>';
      document.getElementById('aliasSummary').textContent = 'Nenhuma pendência de qualidade encontrada.';
      renderAliasReviewTable([]);
      renderTodayCockpit();
      return;
    }
    state.aliasFiles.forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.pending_file;
      opt.textContent = `${item.pending_file} | pend=${item.status_counts.pending_review} | blocked=${item.status_counts.blocked}`;
      select.appendChild(opt);
    });
    if ([...select.options].some(o => o.value === current)) select.value = current;
    select.onchange = () => loadAliasReview();
    await loadAliasReview();
  } catch (err) {
    state.aliasFiles = [];
    state.loadErrors.aliases = err.message;
    document.getElementById('aliasSummary').textContent = `Aliases não verificados: ${err.message}`;
  }
  renderTodayCockpit();
}

async function loadAliasReview() {
  const pendingFile = document.getElementById('aliasPendingFile').value;
  if (!pendingFile) {
    document.getElementById('aliasSummary').textContent = 'Nenhuma pendência de qualidade encontrada.';
    renderAliasReviewTable([]);
    return;
  }
  const payload = await api(`/aliases/review?${qs({pending_file: pendingFile, alias_file: document.getElementById('aliasFile').value, include_blocked: document.getElementById('aliasIncludeBlocked').checked, include_resolved: state.aliasDiagnostics.includeResolved})}`);
  state.aliasReview = payload;
  document.getElementById('aliasSummary').textContent = JSON.stringify({ pending_file: payload.pending_file, alias_file: payload.alias_file, total: payload.total, status_counts: payload.status_counts }, null, 2);
  renderAliasReviewTable(payload.items || []);
}

function renderAliasReviewTable(items) {
  document.getElementById('aliasVisibleCount').textContent = `${items.length} aliases visíveis`;
  if (!items.length) {
    document.getElementById('aliasEmptyState').style.display = 'block';
    document.getElementById('aliasEmptyState').innerHTML = '<strong>Nenhuma pendência de qualidade agora.</strong>Não há aliases para revisar com os filtros atuais. Siga para Hoje para rodar a análise ou atualize a lista após novas coletas.';
    document.getElementById('aliasTableWrap').style.display = 'none';
    document.getElementById('tableAliasReview').innerHTML = '';
    return;
  }
  document.getElementById('aliasEmptyState').style.display = 'none';
  document.getElementById('aliasTableWrap').style.display = 'block';
  const rows = items.map(item => ({
    ...item,
    diagnostic_status_html: statusPill(item.diagnostic_status || item.registry_status || item.match_status),
    action_html: item.league ? `<button class="ghost small" onclick="syncSelectedTeamRegistryLeague(${JSON.stringify(item.league)})">Sincronizar liga</button>` : '<span class="muted">sem liga</span>',
  }));
  renderTable('tableAliasReview', rows, [
    {key:'league', label:'Liga'}, {key:'match_name', label:'Jogo'}, {key:'side', label:'Lado'}, {key:'source_name', label:'Nome detectado'},
    {key:'suggestion', label:'Sugestão diagnóstica'}, {key:'score', label:'Score'}, {key:'diagnostic_status_html', label:'Status', html:true}, {key:'action_html', label:'Ação registry', html:true}
  ], 'Nenhum alias ficou visível com os filtros atuais.');
}

function collectAliasApprovals(allVisible = false) {
  const items = state.aliasReview?.items || [];
  const checked = new Set([...document.querySelectorAll('.alias-check')].filter(el => allVisible || el.checked).map(el => el.dataset.rowId));
  const targetMap = new Map([...document.querySelectorAll('.alias-target')].map(el => [el.dataset.rowId, el.value]));
  return items.filter(item => checked.has(item.row_id)).map(item => ({
    row_id: item.row_id,
    source_name: item.source_name,
    target_name: targetMap.get(item.row_id) || item.suggestion || '',
  })).filter(item => item.source_name && item.target_name);
}

async function approveSelectedAliases() {
  const approvals = collectAliasApprovals(false);
  if (!approvals.length) return;
  await api('/aliases/approve', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ pending_file: state.aliasReview.pending_file, alias_file: document.getElementById('aliasFile').value, approvals, include_blocked: document.getElementById('aliasIncludeBlocked').checked })
  });
  await loadAliasFiles(true);
}

async function approveAllVisibleAliases() {
  const approvals = collectAliasApprovals(true);
  if (!approvals.length) return;
  await api('/aliases/approve', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ pending_file: state.aliasReview.pending_file, alias_file: document.getElementById('aliasFile').value, approvals, include_blocked: document.getElementById('aliasIncludeBlocked').checked })
  });
  await loadAliasFiles(true);
}

function formatJob(job) {
  const req = job.request || {};
  const config = req.config_name ? ` | config=${req.config_name}` : '';
  const replayCfg = req.configs ? ` | configs=${req.configs.join(',')}` : '';
  const canCancel = ['queued','running'].includes(job.status);
  const cancelButton = canCancel ? `<button class="danger small" onclick="cancelJob('${escapeHtml(job.id)}')">cancelar</button>` : '';
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

async function refreshTodayCockpit() {
  await Promise.allSettled([
    loadDashboard(),
    loadReplayRuns(),
    loadReplaySummaries(),
    loadTeamRegistry(true),
    loadAliasFiles(true),
    loadJobs(),
  ]);
  state.lastRefreshAt = new Date().toISOString();
  renderTodayCockpit();
}
