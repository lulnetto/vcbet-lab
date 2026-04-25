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
function registryPendingCount() {
  return (state.teamRegistry?.pending || []).filter(item =>
    String(item.status || 'pending_review') === 'pending_review'
  ).length;
}

function legacyAliasDiagnosticCount() {
  return state.aliasFiles.reduce((sum, item) => (
    sum + Number(item.status_counts?.pending_review || 0)
  ), 0);
}

function legacyAliasBlockedCount() {
  return state.aliasFiles.reduce((sum, item) => (
    sum + Number(item.status_counts?.blocked || 0)
  ), 0);
}

function aliasPendingCount() {
  return registryPendingCount();
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
  const legacyAliases = legacyAliasDiagnosticCount();
  const legacyBlockedAliases = legacyAliasBlockedCount();
  const total = Number(summary.total_entries || 0);
  const open = Number(summary.open_entries || 0);
  const settled = Number(summary.settled_entries || 0);
  const clvCount = Number(state.dashboard?.clv?.count || 0);
  const incompleteReplay = state.replaySummaries.some(item => ['incomplete','blocked','bad'].some(x => String(item.replay_quality_status || item.temporal_contract_status || '').toLowerCase().includes(x)));
  const warningItems = [];
  if (aliases) warningItems.push(`${aliases} alias(es) pendente(s) em Qualidade de Dados.`);
  if (!aliases && (legacyAliases || legacyBlockedAliases)) {
  warningItems.push(`${legacyAliases + legacyBlockedAliases} diagnóstico(s) legado(s) de alias em runs/replays. Registry está sem pendências.`);
  }
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
    ['Aliases no registry', state.loadErrors.teamRegistry ? 'não verificado' : String(aliases)],
    ['Diagnósticos legados', state.loadErrors.aliases ? 'não verificado' : String(legacyAliases + legacyBlockedAliases)],
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

Object.assign(window, {
  renderNextAction,
  registryPendingCount,
  legacyAliasDiagnosticCount,
  legacyAliasBlockedCount,
  aliasPendingCount,
  hasRunForOperationalDate,
  dashboardSummary,
  getNextAction,
  todayStatus,
  renderTodayCockpit,
  refreshTodayCockpit,
});
