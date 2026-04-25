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

Object.assign(window, {
  renderReplayConfigRows,
  addReplayConfigField,
  loadReplayRuns,
  loadReplaySummaries,
  openSelectedReplaySummary,
  loadReplaySummaryDetail,
  renderReplaySummaryPayload,
  loadReplayPicks,
  submitReplay,
});
