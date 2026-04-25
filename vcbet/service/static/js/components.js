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

function statusClass(value) {
  const text = String(value || '').toLowerCase();
  if (['done','completed','success','ok','settled','finished'].some(x => text.includes(x))) return 'ok';
  if (['queued','running','pending','open','atenção','pendente','rodando','parcial'].some(x => text.includes(x))) return 'warn';
  if (['fail','error','cancel','blocked','bad','erro'].some(x => text.includes(x))) return 'bad';
  return '';
}

function statusPill(value) {
  return `<span class="pill ${statusClass(value)}">${escapeHtml(value || '-')}</span>`;
}

function rowDetails(row, label = 'Detalhes') {
  return `<details class="table-detail"><summary>${escapeHtml(label)}</summary><pre>${escapeHtml(JSON.stringify(row, null, 2))}</pre></details>`;
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
