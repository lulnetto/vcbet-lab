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

Object.assign(window, {
  resetWalletToday,
  showWalletHistory,
  dashboardParams,
  loadDashboard,
  loadEntries,
});
