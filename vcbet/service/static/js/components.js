function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatLocalDateTime(value) {
  if (!value || value === 'NaT') return '';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return new Intl.DateTimeFormat('pt-BR', {
    year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit',
  }).format(dt);
}

function formatPtDate(value) {
  if (!value) return '';
  const text = String(value).slice(0, 10);
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value);
}

function todayIsoDate() {
  return typeof initialLocalDate === 'function' ? initialLocalDate() : new Date().toISOString().slice(0, 10);
}

function statusClass(value) {
  const text = String(value || '').toLowerCase();
  if (['done','completed','success','ok','settled','finished'].some(x => text.includes(x))) return 'ok';
  if (['queued','running','pending','open','atenção','pendente','rodando','parcial'].some(x => text.includes(x))) return 'warn';
  if (['fail','error','cancel','blocked','bad','erro'].some(x => text.includes(x))) return 'bad';
  return '';
}

function entityEmptyMessage(kind) {
  if (kind === 'runs' || kind === 'replays') {
    return 'Catálogo não encontrado. Rode scripts/build_run_catalog.py e scripts/build_replay_catalog.py ou gere uma nova execução.';
  }
  return 'Nenhum item encontrado.';
}

function renderDatePicker(id, value = state.selectedDate || todayIsoDate()) {
  const el = document.getElementById(id);
  if (!el) return;
  el.type = 'date';
  if (!el.value) el.value = value;
  el.onchange = () => {
    state.selectedDate = el.value || todayIsoDate();
    renderTodayCockpit();
  };
}

function renderEntitySelect(id, items, options = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  const {
    valueKey = 'id',
    labelKey = 'label',
    emptyLabel = 'nenhum item encontrado',
    placeholder = 'Selecione',
    keepEmpty = false,
    selected = '',
    onChange = null,
  } = options;
  const current = el.value || selected;
  el.innerHTML = keepEmpty ? `<option value="">${escapeHtml(placeholder)}</option>` : '';
  if (!items || !items.length) {
    el.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
    el.disabled = true;
    if (onChange) onChange('');
    return;
  }
  el.disabled = false;
  items.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item[valueKey] ?? '';
    opt.textContent = item[labelKey] ?? item[valueKey] ?? '';
    Object.entries(item).forEach(([key, value]) => {
      if (value !== undefined && value !== null && typeof value !== 'object') opt.dataset[key] = value;
    });
    el.appendChild(opt);
  });
  if ([...el.options].some(o => o.value === current)) el.value = current;
  else if (selected && [...el.options].some(o => o.value === selected)) el.value = selected;
  if (onChange) {
    el.onchange = () => onChange(el.value, items.find(item => String(item[valueKey] ?? '') === el.value));
    onChange(el.value, items.find(item => String(item[valueKey] ?? '') === el.value));
  }
}

function renderLedgerSelect(id, inputId) {
  renderEntitySelect(id, state.entities.ledgers, {
    valueKey: 'id',
    labelKey: 'label',
    selected: state.selectedLedger || 'official',
    emptyLabel: entityEmptyMessage('ledgers'),
    onChange: (value, item) => {
      state.selectedLedger = value || state.selectedLedger || 'official';
      const input = document.getElementById(inputId);
      if (input && item?.path) input.value = item.path;
    },
  });
}

function renderRunSelect(id, inputId) {
  renderEntitySelect(id, state.entities.runs, {
    valueKey: 'run_dir',
    labelKey: 'label',
    selected: state.selectedRun,
    keepEmpty: true,
    placeholder: 'Selecione uma run',
    emptyLabel: state.entities.catalogMessages.runs || 'Nenhuma run encontrada.',
    onChange: (value) => {
      state.selectedRun = value || '';
      const input = document.getElementById(inputId);
      if (input) input.value = value || '';
    },
  });
}

function renderReplaySelect(id) {
  renderEntitySelect(id, state.entities.replays, {
    valueKey: 'summary_file',
    labelKey: 'label',
    selected: state.selectedReplayHistory || state.selectedReplay,
    keepEmpty: true,
    placeholder: 'Selecione um replay',
    emptyLabel: state.entities.catalogMessages.replays || 'Nenhum replay encontrado.',
    onChange: (value) => {
      state.selectedReplayHistory = value || '';
      state.selectedReplay = value || '';
    },
  });
}

function renderConfigSelect(id, preferred = state.selectedConfig || 'legacy_v2') {
  renderEntitySelect(id, state.entities.configs, {
    valueKey: 'id',
    labelKey: 'label',
    selected: preferred,
    emptyLabel: entityEmptyMessage('configs'),
    onChange: (value) => {
      if (value) state.selectedConfig = value;
      renderTodayCockpit();
    },
  });
}

function renderManualPathToggle(summaryText = 'Avançado') {
  return `<summary>${escapeHtml(summaryText)}</summary>`;
}

function statusPill(value) {
  return `<span class="pill ${statusClass(value)}">${escapeHtml(value || '-')}</span>`;
}

function rowDetails(row, label = 'Detalhes') {
  return `<details class="table-detail advanced"><summary>${escapeHtml(label)}</summary><pre>${escapeHtml(JSON.stringify(row, null, 2))}</pre></details>`;
}

function displayValue(value) {
  if (value === undefined || value === null || value === '') return 'não disponível';
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'não disponível';
  if (typeof value === 'object') return JSON.stringify(value);
  return value;
}

function firstAvailable(row, keys) {
  for (const key of keys) {
    if (row && row[key] !== undefined && row[key] !== null && row[key] !== '') return row[key];
  }
  return null;
}

function pickWarnings(row) {
  const warnings = [];
  const knownChecks = [
    ['alias', ['alias_status', 'aliases_pending', 'alias_pending', 'blocked_aliases']],
    ['fallback replay', ['replay_fallback_used', 'fallback_used']],
    ['trace incompleto', ['trace_complete', 'trace_status']],
    ['odds snapshot', ['odds_snapshot_status', 'odds_snapshot_file', 'closing_odds_status']],
    ['contrato temporal', ['temporal_contract_status']],
  ];
  knownChecks.forEach(([label, keys]) => {
    const value = firstAvailable(row, keys);
    const text = String(value ?? '').toLowerCase();
    if (value === true || (label === 'trace incompleto' && value === false) || ['missing','weak','unavailable','incomplete','pending','blocked','bad','fallback'].some(x => text.includes(x))) {
      warnings.push(`${label}: ${displayValue(value)}`);
    }
  });
  Object.entries(row || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '' || value === false) return;
    const keyText = key.toLowerCase();
    if (!/(warning|flag|limitation|error)/.test(keyText)) return;
    const text = displayValue(value);
    if (text !== 'não disponível') warnings.push(`${key}: ${text}`);
  });
  return [...new Set(warnings)].slice(0, 6);
}

function warningList(items, emptyText = '') {
  if (!items || !items.length) return emptyText ? `<div class="state-box subtle">${escapeHtml(emptyText)}</div>` : '';
  return `<div class="warning-list">${items.map(item => `<div class="warning-item">${escapeHtml(item)}</div>`).join('')}</div>`;
}

function pickDetailButton(source, index) {
  return `<button class="ghost small" onclick="openPickDetail('${escapeHtml(source)}', ${Number(index)})">inspecionar</button>`;
}

function ensurePickDrawer() {
  let root = document.getElementById('pickDetailDrawer');
  if (root) return root;
  root = document.createElement('div');
  root.id = 'pickDetailDrawer';
  root.className = 'drawer-backdrop';
  root.innerHTML = '<aside class="drawer-panel" role="dialog" aria-modal="true"></aside>';
  root.onclick = event => {
    if (event.target === root) closePickDetail();
  };
  document.body.appendChild(root);
  return root;
}

function detailRow(label, value) {
  return `<div class="detail-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(displayValue(value))}</strong></div>`;
}

function openPickDetail(source, index) {
  const collections = {
    dashboard: state.dashboardEntries || [],
    replay: state.replayPicks || [],
  };
  const row = collections[source]?.[index];
  if (!row) return;
  const root = ensurePickDrawer();
  const panel = root.querySelector('.drawer-panel');
  const warnings = pickWarnings(row);
  const technicalKeys = [
    'run_id', 'source_run_id', 'source_file', 'summary_file', 'config_name', 'created_at',
    'candidate_stage', 'pick_safety_status', 'final_bet_status', 'final_settlement_status',
    'trace_status', 'temporal_contract_status', 'replay_quality_status', 'replay_source_strength',
  ];
  panel.innerHTML = `
    <div class="drawer-head">
      <div>
        <div class="muted">Inspeção de pick</div>
        <h2>${escapeHtml(displayValue(firstAvailable(row, ['match_name', 'fixture', 'event_name'])))}</h2>
      </div>
      <button class="ghost small" onclick="closePickDetail()">fechar</button>
    </div>
    ${warnings.length ? warningList(warnings) : ''}
    <div class="detail-grid">
      ${detailRow('Liga', firstAvailable(row, ['league', 'competition']))}
      ${detailRow('Mercado', firstAvailable(row, ['market_type', 'market']))}
      ${detailRow('Seleção', firstAvailable(row, ['selection_raw', 'selection', 'side']))}
      ${detailRow('Linha', firstAvailable(row, ['line', 'handicap']))}
      ${detailRow('Odd entrada', firstAvailable(row, ['odd_entrada', 'odds', 'price']))}
      ${detailRow('Odd justa/modelo', firstAvailable(row, ['fair_odds', 'model_odds', 'odd_fair', 'fair_price']))}
      ${detailRow('EV / edge', firstAvailable(row, ['ev_percent', 'edge_percent', 'model_edge', 'ev']))}
      ${detailRow('Confiança', firstAvailable(row, ['confidence_score', 'confidence']))}
      ${detailRow('Status', firstAvailable(row, ['final_settlement_status', 'final_bet_status', 'pick_safety_status', 'candidate_stage']))}
      ${detailRow('Config', firstAvailable(row, ['config_name', 'config']))}
      ${detailRow('Run/fonte', firstAvailable(row, ['run_id', 'source_run_id', 'source_file', 'summary_file']))}
    </div>
    <details class="advanced" open>
      <summary>Metadados técnicos</summary>
      <div class="detail-grid compact">
        ${technicalKeys.map(key => detailRow(key, row[key])).join('')}
      </div>
    </details>
    <details class="advanced">
      <summary>JSON bruto</summary>
      <pre>${escapeHtml(JSON.stringify(row, null, 2))}</pre>
    </details>`;
  root.classList.add('open');
}

function closePickDetail() {
  const root = document.getElementById('pickDetailDrawer');
  if (root) root.classList.remove('open');
}

function jobActionContext(job) {
  const type = String(job?.job_type || job?.title || '').toLowerCase();
  const req = job?.request || {};
  if (type.includes('replay')) return 'Replay Lab';
  if (type.includes('closing')) return 'Atualizar closing odds';
  if (type.includes('results_settlement') || (type.includes('result') && type.includes('settlement'))) return 'Resultados + settlement';
  if (type.includes('result')) return 'Atualizar resultados';
  if (type.includes('settlement')) return 'Liquidar ledger';
  if (type.includes('daily')) return 'Ciclo diário completo';
  if (type.includes('analysis')) return 'Análise do dia';
  if (req.config_name || req.target_date) return 'Rotina operacional';
  return 'Ação não identificada';
}

function fillSelect(id, values, keepEmpty = false, emptyLabel = 'Todos') {
  const el = document.getElementById(id);
  if (!el) return;
  const current = el.value;
  el.innerHTML = keepEmpty ? `<option value="">${emptyLabel}</option>` : '';
  values.forEach(v => {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    el.appendChild(opt);
  });
  if ([...el.options].some(o => o.value === current)) el.value = current;
}

function renderTable(id, rows, cols, emptyMessage = 'Sem dados para os filtros atuais.') {
  const el = document.getElementById(id);
  const normalizedCols = cols.map(c => typeof c === 'string' ? ({key:c, label:c, html:false}) : ({html:false, ...c}));
  if (!rows || !rows.length) {
    el.innerHTML = `<tr><td class="state-box"><strong>Nada para mostrar.</strong>${escapeHtml(emptyMessage)}</td></tr>`;
    return;
  }
  const head = `<tr>${normalizedCols.map(c => `<th>${escapeHtml(c.label)}</th>`).join('')}</tr>`;
  const body = rows.map(row => `<tr>${normalizedCols.map(c => {
    const raw = row[c.key] ?? '';
    const value = c.format ? c.format(raw, row) : raw;
    return `<td>${c.html ? (value || '') : escapeHtml(value)}</td>`;
  }).join('')}</tr>`).join('');
  el.innerHTML = `<thead>${head}</thead><tbody>${body}</tbody>`;
}

function parseAmbiguousOptions(value) {
  return String(value || '').split('|').map(item => {
    const text = item.trim();
    if (!text) return null;
    const parts = text.split(':');
    const score = parts.length > 1 ? parts.pop().trim() : '';
    return { name: parts.join(':').trim(), score };
  }).filter(Boolean);
}

function renderAmbiguousOptions(value, index = null) {
  const options = parseAmbiguousOptions(value);
  if (!options.length) return '<span class="muted">sem opções</span>';

  const list = options.slice(0, 5).map(item => (
    `<span class="candidate-chip">${escapeHtml(item.name)}${item.score ? ` <strong>${escapeHtml(item.score)}</strong>` : ''}</span>`
  )).join('');

  if (index === null) return `<div class="candidate-list">${list}</div>`;

  const select = `<select class="registry-candidate-select" data-registry-index="${Number(index)}">
    ${options.map((item, optionIndex) => (
      `<option value="${escapeHtml(item.name)}" ${optionIndex === 0 ? 'selected' : ''}>
        ${escapeHtml(item.name)}${item.score ? ` (${escapeHtml(item.score)})` : ''}
      </option>`
    )).join('')}
  </select>`;

  return `<div class="candidate-list">${list}</div>${select}`;
}

function renderTeamRegistrySummary(registry) {
  const pending = registry?.pending || [];
  const approved = registry?.approved || [];
  const leagues = [...new Set([...pending, ...approved].map(item => item.league || 'sem_liga'))].sort();
  const leagueRows = leagues.map(league => `<div class="summary-row"><span>${escapeHtml(league)}</span><strong>${Number(registry.pendingByLeague?.[league] || 0)} pend. / ${Number(registry.approvedByLeague?.[league] || 0)} aprov.</strong></div>`).join('');
  return `
    <div class="kpis">
      <div class="kpi"><div class="label">Pendentes no registry</div><div class="value">${pending.length}</div></div>
      <div class="kpi"><div class="label">Aliases aprovados</div><div class="value">${approved.length}</div></div>
    </div>
    <div class="registry-league-summary">${leagueRows || '<div class="muted">Sem ligas para resumir.</div>'}</div>`;
}

function renderRegistryReviewActions(item, index) {
  const blocked = item.approval_blocked === 'true';
  const low = item.manual_override_required === 'true';
  return `<div class="inline registry-actions">
    <button class="green small" ${blocked ? 'disabled' : ''} onclick="approveRegistrySuggestion(${Number(index)})">${low ? 'Aprovar com justificativa' : 'Aprovar sugestão'}</button>
    <button class="amber small" ${blocked ? 'disabled' : ''} onclick="approveRegistryEdited(${Number(index)})">Editar e aprovar</button>
    <button class="danger small" onclick="rejectRegistryAlias(${Number(index)})">Rejeitar / ignorar</button>
  </div>`;
}

function renderTeamRegistryPendingTable(items) {
  const rows = (items || []).map((item, index) => ({
    ...item,
    suggested_edit: `<input class="registry-footy-input" data-registry-index="${index}" value="${escapeHtml(item.suggested_footystats_name || '')}">`,
    options_html: renderAmbiguousOptions(item.ambiguous_options, index),
    status_html: statusPill(item.status || 'pending_review'),
    score_html: statusPill(item.top_score || '-'),
    warnings_html: String(item.validation_warnings || '').split('|').filter(Boolean).map(w => `<span class="pill bad">${escapeHtml(w)}</span>`).join(' ') || '<span class="muted">sem alertas</span>',
    betano_html: `<strong>${escapeHtml(item.betano_name || '')}</strong><div class="muted">id=${escapeHtml(item.betano_team_id || '-')}</div><div class="muted">${escapeHtml(item.betano_url || '')}</div>`,
    actions_html: renderRegistryReviewActions(item, index),
  }));
  renderTable('tableTeamRegistryPending', rows, [
    {key:'league', label:'Liga'},
    {key:'betano_html', label:'Betano', html:true},
    {key:'suggested_edit', label:'xG', html:true},
    {key:'score_html', label:'Score', html:true},
    {key:'review_reason', label:'Motivo'},
    {key:'options_html', label:'Opções ambíguas', html:true},
    {key:'warnings_html', label:'Alertas', html:true},
    {key:'source', label:'Fonte'},
    {key:'status_html', label:'Status', html:true},
    {key:'actions_html', label:'Ações', html:true},
  ], 'Nenhum alias pendente no registry global.');
}

function stepStatus(value) {
  const cls = { ok:'ok', 'atenção':'warn', pendente:'warn', rodando:'warn', indisponível:'' }[value] || '';
  return `<span class="pill ${cls}">${escapeHtml(value)}</span>`;
}

function pipelineStep(name, status, text, actionLabel, action) {
  return `<div class="step-card">
    <div class="section-title"><h3>${escapeHtml(name)}</h3>${stepStatus(status)}</div>
    <p>${escapeHtml(text)}</p>
    ${actionLabel ? `<button class="ghost small" onclick="${escapeHtml(action)}">${escapeHtml(actionLabel)}</button>` : ''}
  </div>`;
}

function renderKpis(summary, clv) {
  const items = [
    ['Entradas', summary.total_entries], ['Abertas', summary.open_entries], ['Liquidadas', summary.settled_entries],
    ['Executadas', summary.executed_entries], ['Unid. modelo', summary.model_units], ['ROI modelo %', summary.model_roi_percent],
    ['Unid. real', summary.real_units], ['ROI real %', summary.real_roi_percent], ['Hit rate %', summary.hit_rate_percent],
    ['Weighted HR %', summary.weighted_hit_rate_percent], ['Wins', summary.wins], ['Losses', summary.losses],
    ['Half wins', summary.half_wins], ['Half losses', summary.half_losses], ['CLV médio', clv.avg_delta], ['CLV + %', clv.positive_rate_percent]
  ];
  document.getElementById('kpiGrid').innerHTML = items.map(([label, value]) => `<div class="kpi"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value ?? 0)}</div></div>`).join('');
}
