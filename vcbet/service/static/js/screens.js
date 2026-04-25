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
  return document.getElementById('analysisConfig')?.value || document.getElementById('dailyConfig')?.value || '';
}

function operationalDate() {
  return document.getElementById('analysisDate')?.value || document.getElementById('dailyDate')?.value || new Date().toISOString().slice(0, 10);
}

function aliasPendingCount() {
  return state.aliasFiles.reduce((sum, item) => sum + Number(item.status_counts?.pending_review || 0) + Number(item.status_counts?.blocked || 0), 0);
}

function hasRunForOperationalDate() {
  const date = operationalDate();
  return state.replayRuns.some(item => item.target_date === date || String(item.run_id || '').includes(date.replaceAll('-', '')));
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
  if (!hasPicks) return { text:'Rodar análise do dia. Ainda não há run/picks verificados para o contexto atual.', button:'Rodar análise', handler:() => document.getElementById('analysisDate')?.focus() };
  if (open) return { text:`Atualizar resultados / settlement. Há ${open} pick(s) abertas no filtro atual.`, button:'Atualizar resultados', handler:() => document.getElementById('resultsGrace')?.focus() };
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

  document.getElementById('todayDate').textContent = operationalDate() || 'não selecionada';
  document.getElementById('todayConfig').textContent = selectedConfigName() || 'não verificada';
  document.getElementById('todayStatus').innerHTML = todayStatus();
  document.getElementById('todayRefresh').textContent = state.lastRefreshAt ? formatLocalDateTime(state.lastRefreshAt) : 'não carregado';
  document.getElementById('pipelineMeta').textContent = Object.keys(state.loadErrors).length ? 'estado parcial' : 'dados carregados';

  document.getElementById('todayPipeline').innerHTML = [
    pipelineStep('Análise do dia', running ? 'rodando' : (total || hasRunForOperationalDate() ? 'ok' : 'pendente'), total ? `${total} pick(s) no filtro atual da carteira.` : 'Sem picks verificadas no contexto atual.', 'Rodar análise', "document.getElementById('analysisDate')?.focus()"),
    pipelineStep('Closing odds', running ? 'rodando' : (clvCount ? 'ok' : (total ? 'atenção' : 'indisponível')), clvCount ? `${clvCount} entrada(s) com closing odds.` : (total ? 'Closing odds não verificada para as entradas carregadas.' : 'Depende de picks/ledger carregados.'), 'Atualizar', "document.getElementById('closingWindow')?.focus()"),
    pipelineStep('Resultados', running ? 'rodando' : (open ? 'atenção' : (settled ? 'ok' : 'pendente')), open ? `${open} pick(s) abertas podem precisar de resultado.` : (settled ? 'Entradas liquidadas encontradas.' : 'Sem resultado verificado.'), 'Atualizar resultados', "document.getElementById('resultsGrace')?.focus()"),
    pipelineStep('Settlement', running ? 'rodando' : (open ? 'atenção' : (settled ? 'ok' : 'pendente')), open ? 'Há entradas abertas no filtro atual.' : (settled ? `${settled} entrada(s) liquidadas.` : 'Settlement não verificado.'), 'Liquidar ledger', "document.getElementById('settlementLedger')?.focus()"),
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
  const el = document.getElementById(id);
  el.innerHTML = '';
  state.configs.forEach(cfg => {
    const opt = document.createElement('option');
    opt.value = cfg.name;
    opt.textContent = `${cfg.label} (${cfg.name})`;
    if (cfg.name === preferred) opt.selected = true;
    el.appendChild(opt);
  });
}

async function loadConfigs() {
  state.configs = await api('/configs');
  ['analysisConfig','dailyConfig'].forEach(id => fillConfigSelect(id));
  renderReplayConfigRows(['legacy_v2']);
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
    ledger_file: document.getElementById('settlementLedger').value,
    results_file: document.getElementById('settlementResults').value,
    overrides_file: document.getElementById('settlementOverrides').value || null,
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
    const payload = await api('/runs?limit=300');
    state.replayRuns = payload.items || [];
    delete state.loadErrors.runs;
    const select = document.getElementById('replaySourceRunSelect');
    select.innerHTML = '<option value="">Selecione uma run</option>' + state.replayRuns.map(item =>
      `<option value="${escapeHtml(item.path)}">${escapeHtml(item.target_date)} | ${escapeHtml(item.run_id)} | picks=${escapeHtml(item.picks_rows ?? '-')}</option>`
    ).join('');
    select.onchange = () => { document.getElementById('replaySourceRun').value = select.value; };
  } catch (err) {
    state.loadErrors.runs = err.message;
  }
  renderTodayCockpit();
}

async function loadReplaySummaries() {
  try {
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
    ], 'Ainda não há dados de replay. Rode um replay a partir de uma run histórica para comparar configs.');
  } catch (err) {
    state.loadErrors.replay = err.message;
    renderTable('tableReplaySummaries', [], [
      {key:'target_date', label:'Data'}, {key:'source_run_id', label:'Run'}, {key:'quality_html', label:'Qualidade', html:true}
    ], 'Replay não verificado nesta carga.');
  }
  renderTodayCockpit();
}

async function loadReplaySummaryDetail(index) {
  const item = state.replaySummaries[index];
  if (!item) return;
  const payload = await api(`/replays/summary?${qs({summary_file: item.summary_file})}`);
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
      action: `<button class="ghost small" onclick="loadReplayPicks('${escapeHtml(item.summary_file)}','${escapeHtml(r.config_name)}')">ver picks</button>`
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

async function loadAliasFiles(forceReload = false) {
  try {
    const includeBlocked = document.getElementById('aliasIncludeBlocked').checked;
    const payload = await api(`/aliases/files?${qs({include_blocked: includeBlocked})}`);
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
  const payload = await api(`/aliases/review?${qs({pending_file: pendingFile, alias_file: document.getElementById('aliasFile').value, include_blocked: document.getElementById('aliasIncludeBlocked').checked})}`);
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
    pick: `<input type="checkbox" class="alias-check" data-row-id="${escapeHtml(item.row_id)}" checked>`,
    target_edit: `<input class="alias-target" data-row-id="${escapeHtml(item.row_id)}" value="${escapeHtml(item.suggestion || '')}">`
  }));
  renderTable('tableAliasReview', rows, [
    {key:'pick', label:'', html:true}, {key:'league', label:'Liga'}, {key:'match_name', label:'Jogo'}, {key:'side', label:'Lado'}, {key:'source_name', label:'Nome detectado'},
    {key:'target_edit', label:'Nome correto', html:true}, {key:'score', label:'Score'}, {key:'match_status', label:'Status'}
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
  return `<div class="job ${failed ? 'job-failed' : statusClass(job.status)}">
    <div class="inline"><strong>${escapeHtml(job.title)}</strong>${statusPill(job.status)}<span class="muted">${escapeHtml(job.id)}</span></div>
    <div class="job-context"><strong>${escapeHtml(jobActionContext(job))}</strong><span>${escapeHtml(job.job_type || '-')}</span></div>
    ${requestBits ? `<div class="muted">${escapeHtml(requestBits)}</div>` : ''}
    <div class="inline" style="margin-top:8px;">
      <button class="ghost small" onclick="viewLogs('${escapeHtml(job.id)}')">logs</button>
      ${cancelButton}
    </div></div>`;
}

async function loadJobs() {
  try {
    const payload = await api('/jobs?limit=40');
    state.jobs = payload.items || [];
    delete state.loadErrors.jobs;
    document.getElementById('jobsList').innerHTML = state.jobs.map(formatJob).join('') || '<div class="state-box"><strong>Nenhum job recente.</strong>Quando você rodar uma análise, daily run, replay ou coleta, o andamento aparecerá aqui com acesso aos logs.</div>';
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
    loadAliasFiles(true),
    loadJobs(),
  ]);
  state.lastRefreshAt = new Date().toISOString();
  renderTodayCockpit();
}
