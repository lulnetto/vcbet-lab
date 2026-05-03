function configPresetItem(name) {
  return (state.configPresets.items || []).find(item => item.name === name);
}

function rangesToText(ranges) {
  return (ranges || []).map(item => `${item.min}-${item.max}`).join(', ');
}

function parseRangeText(value) {
  const text = String(value || '').trim();
  if (!text) return [];
  return text.split(',').map(part => {
    const match = part.trim().match(/^([0-9]+(?:[.,][0-9]+)?)\s*-\s*([0-9]+(?:[.,][0-9]+)?)$/);
    if (!match) throw new Error(`Faixa inválida: ${part.trim()}`);
    return { min: Number(match[1].replace(',', '.')), max: Number(match[2].replace(',', '.')) };
  });
}

function textLines(value) {
  return String(value || '').split('\n').map(x => x.trim()).filter(Boolean);
}

function numberOrNull(id) {
  const el = document.getElementById(id);
  if (!el || String(el.value).trim() === '') return null;
  return Number(String(el.value).replace(',', '.'));
}

function setConfigPresetMessage(text, kind = '') {
  const el = document.getElementById('configPresetMessage');
  if (!el) return;
  el.className = kind || 'muted';
  el.textContent = text || '';
}

function renderConfigPresetIssues(summary) {
  const root = document.getElementById('configPresetIssues');
  if (!root) return;
  const issues = summary?.issues || [
    ...(summary?.errors || []),
    ...(summary?.warnings || []),
  ];
  if (!issues.length) {
    root.innerHTML = '<div class="config-issue ok">Config válida.</div>';
    return;
  }
  root.innerHTML = issues.map(issue => (
    `<div class="config-issue ${escapeHtml(issue.severity || 'warning')}"><strong>${escapeHtml(issue.severity || '')}</strong> ${escapeHtml(issue.path || '')}: ${escapeHtml(issue.message || '')}</div>`
  )).join('');
}

function renderConfigPresetList() {
  const rows = (state.configPresets.items || []).map(item => ({
    ...item,
    markets_text: (item.enabled_markets || []).join(', '),
    protected_html: item.protected ? statusPill('protegida') : statusPill('editável'),
    actions_html: `<div class="inline">
      <button class="ghost small" onclick="openConfigPreset('${escapeHtml(item.name)}')">Editar</button>
      <button class="ghost small" onclick="cloneConfigPresetPrompt('${escapeHtml(item.name)}')">Clonar</button>
      <button class="danger small" ${item.protected ? 'disabled' : ''} onclick="deleteConfigPresetPrompt('${escapeHtml(item.name)}')">Deletar</button>
    </div>`,
  }));
  renderTable('tableConfigPresets', rows, [
    {key:'name', label:'Nome'},
    {key:'label', label:'Label'},
    {key:'pricing_variant', label:'Pricing'},
    {key:'markets_text', label:'Mercados habilitados'},
    {key:'updated_at', label:'Última modificação', format: value => formatLocalDateTime(value)},
    {key:'protected_html', label:'Status', html:true},
    {key:'actions_html', label:'Ações', html:true},
  ], 'Nenhum preset encontrado em configs/*.json.');
}

function populateConfigPresetCreateSource() {
  const el = document.getElementById('configPresetCreateSource');
  if (!el) return;
  const current = el.value || state.configPresets.selectedName || state.selectedConfig || 'gd_experimental_v1';
  el.innerHTML = '';
  (state.configPresets.items || []).forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.name;
    opt.textContent = item.label || item.name;
    el.appendChild(opt);
  });
  if ([...el.options].some(opt => opt.value === current)) el.value = current;
}

async function loadConfigPresets(force = false) {
  if (state.configPresets.loading && !force) return;
  state.configPresets.loading = true;
  try {
    state.configPresets.items = await fetchConfigPresets();
    renderConfigPresetList();
    populateConfigPresetCreateSource();
    if (!state.configPresets.selectedName && state.configPresets.items.length) {
      state.configPresets.selectedName = state.configPresets.items.find(item => item.name === state.selectedConfig)?.name || state.configPresets.items[0].name;
    }
    if (state.configPresets.selectedName && (!state.configPresets.detail || force)) {
      await openConfigPreset(state.configPresets.selectedName);
    }
  } catch (err) {
    setConfigPresetMessage(`Erro ao carregar configs: ${err.message}`, 'bad');
  } finally {
    state.configPresets.loading = false;
  }
}

async function openConfigPreset(name) {
  try {
    const detail = await fetchConfigPreset(name);
    state.configPresets.selectedName = name;
    state.configPresets.detail = detail;
    renderConfigPresetEditor(detail);
    setConfigPresetMessage(`Editando ${name}.`, 'muted');
  } catch (err) {
    setConfigPresetMessage(`Erro ao abrir ${name}: ${err.message}`, 'bad');
  }
}

function renderPricingOptions(options, current) {
  return (options || []).map(value => `<option value="${escapeHtml(value)}" ${value === current ? 'selected' : ''}>${escapeHtml(value)}</option>`).join('');
}

function marketRowHtml(market, cfg, enabled) {
  return `<tr>
    <td><input type="checkbox" class="cfg-market-enabled" data-market="${escapeHtml(market)}" ${enabled ? 'checked' : ''}></td>
    <td><strong>${escapeHtml(market)}</strong></td>
    ${['odd_min','standard_max','extended_max','edge_min','edge_strong','edge_premium_extended'].map(field => (
      `<td><input type="number" step="0.001" class="cfg-market-input" data-market="${escapeHtml(market)}" data-field="${field}" value="${escapeHtml(cfg?.[field] ?? '')}"></td>`
    )).join('')}
    <td><input type="checkbox" class="cfg-market-primary" data-market="${escapeHtml(market)}" ${cfg?.is_primary_market ? 'checked' : ''}></td>
    <td><input type="text" class="cfg-market-ranges" data-market="${escapeHtml(market)}" value="${escapeHtml(rangesToText(cfg?.allowed_odd_ranges || []))}" placeholder="1.50-2.00, 2.50-3.00"></td>
  </tr>`;
}

function renderConfigPresetEditor(detail) {
  const root = document.getElementById('configPresetEditor');
  if (!root || !detail) return;
  const raw = detail.raw || {};
  const resolved = detail.resolved || {};
  const metadata = resolved.metadata || {};
  const markets = detail.schema_options?.available_markets || [];
  const pricingOptions = detail.schema_options?.available_pricing_variants || [];
  const enabledMarkets = Array.isArray(raw.enabled_markets) ? raw.enabled_markets : Object.keys(resolved.markets || {});
  const leagueFilter = resolved.league_filter || {};
  const xg = resolved.xg_residual_adjustment || {};
  const portfolio = resolved.rules?.portfolio || {};
  const correlation = portfolio.correlation_selection || {};

  root.className = '';
  root.innerHTML = `
    <div class="row">
      <div><label>Nome técnico</label><input id="cfgMetaName" value="${escapeHtml(detail.name)}" disabled></div>
      <div><label>Label</label><input id="cfgMetaLabel" value="${escapeHtml(metadata.label || '')}"></div>
      <div><label>Pricing variant</label><select id="cfgPricingVariant">${renderPricingOptions(pricingOptions, resolved.pricing_variant)}</select></div>
    </div>
    <div style="margin-top:10px;"><label>Description</label><textarea id="cfgMetaDescription">${escapeHtml(metadata.description || '')}</textarea></div>

    <details class="advanced" open>
      <summary>Mercados</summary>
      <div style="margin-top:10px;"><label>Allowed odd ranges global</label><input id="cfgGlobalOddRanges" value="${escapeHtml(rangesToText(raw.allowed_odd_ranges || []))}" placeholder="1.50-2.00, 2.50-3.00"></div>
      <div class="table-wrap" style="margin-top:10px;">
        <table class="config-market-table">
          <thead><tr>
            <th>ON</th><th>market_type</th><th>odd_min</th><th>standard_max</th><th>extended_max</th><th>edge_min</th><th>edge_strong</th><th>edge_premium_extended</th><th>primary</th><th>allowed_odd_ranges</th>
          </tr></thead>
          <tbody>${markets.map(market => marketRowHtml(market, resolved.markets?.[market] || {}, enabledMarkets.includes(market))).join('')}</tbody>
        </table>
      </div>
    </details>

    <details class="advanced" open>
      <summary>Ligas</summary>
      <div class="row" style="margin-top:10px;">
        <div><label>Modo</label><select id="cfgLeagueMode">
          ${['disabled','allowlist','blocklist'].map(mode => `<option value="${mode}" ${mode === (leagueFilter.mode || 'disabled') ? 'selected' : ''}>${mode}</option>`).join('')}
        </select></div>
        <div><label>Allowed leagues</label><textarea id="cfgAllowedLeagues" placeholder="uma liga por linha">${escapeHtml((leagueFilter.allowed_leagues || []).join('\n'))}</textarea></div>
        <div><label>Blocked leagues</label><textarea id="cfgBlockedLeagues" placeholder="uma liga por linha">${escapeHtml((leagueFilter.blocked_leagues || []).join('\n'))}</textarea></div>
      </div>
    </details>

    <details class="advanced" open>
      <summary>Residual xG</summary>
      <div class="inline" style="margin-top:10px;"><label><input type="checkbox" id="cfgXgEnabled" ${xg.enabled ? 'checked' : ''}> enabled</label></div>
      <div class="row" style="margin-top:10px;">
        <div><label>weight</label><input id="cfgXgWeight" type="number" step="0.001" value="${escapeHtml(xg.weight ?? '')}"></div>
        <div><label>max residual</label><input id="cfgXgMaxResidual" type="number" step="0.001" value="${escapeHtml(xg.max_residual_abs ?? '')}"></div>
        <div><label>max lambda adjustment pct</label><input id="cfgXgMaxLambdaPct" type="number" step="0.001" value="${escapeHtml(xg.max_lambda_adjustment_pct ?? '')}"></div>
        <div><label>min games</label><input id="cfgXgMinGames" type="number" step="1" value="${escapeHtml(xg.min_games ?? '')}"></div>
      </div>
      <div style="margin-top:10px;"><label>markets</label><textarea id="cfgXgMarkets">${escapeHtml((xg.markets || []).join('\n'))}</textarea></div>
    </details>

    <details class="advanced" open>
      <summary>Portfolio básico</summary>
      <div class="row" style="margin-top:10px;">
        <div><label>max picks per match</label><input id="cfgPortfolioMaxMatch" type="number" step="1" value="${escapeHtml(portfolio.max_picks_per_match ?? '')}"></div>
        <div><label>EV override global</label><input id="cfgPortfolioEvOverride" type="number" step="0.1" value="${escapeHtml(correlation.ev_gap_override_pp ?? '')}"></div>
      </div>
      <div class="inline" style="margin-top:10px;"><label><input type="checkbox" id="cfgCorrelationEnabled" ${correlation.enabled !== false ? 'checked' : ''}> correlation selection enabled</label></div>
    </details>

    <details class="advanced" open>
      <summary>JSON avançado</summary>
      <textarea id="cfgRawJson" class="config-json-editor">${escapeHtml(JSON.stringify(raw, null, 2))}</textarea>
      <div class="inline" style="margin-top:10px;">
        <button class="ghost small" onclick="formatCurrentConfigJson()">Formatar JSON</button>
        <button class="ghost small" onclick="validateCurrentConfigPreset()">Validar</button>
        <button class="green small" onclick="saveCurrentConfigPreset()">Salvar</button>
      </div>
    </details>
    <div id="configPresetIssues" class="config-issues"></div>
  `;
  renderConfigPresetIssues(detail.validation || {issues: []});
}

function readCurrentConfigPresetPayload() {
  const detail = state.configPresets.detail;
  if (!detail) throw new Error('Nenhuma config selecionada.');
  const rawText = document.getElementById('cfgRawJson')?.value || '{}';
  const payload = JSON.parse(rawText);
  payload.metadata = payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {};
  payload.metadata.name = detail.name;
  payload.metadata.label = document.getElementById('cfgMetaLabel')?.value || detail.name;
  payload.metadata.description = document.getElementById('cfgMetaDescription')?.value || '';
  payload.pricing_variant = document.getElementById('cfgPricingVariant')?.value || 'xg_only';

  const enabled = [...document.querySelectorAll('.cfg-market-enabled')]
    .filter(input => input.checked)
    .map(input => input.dataset.market);
  payload.enabled_markets = enabled;

  const globalRanges = parseRangeText(document.getElementById('cfgGlobalOddRanges')?.value || '');
  if (globalRanges.length) payload.allowed_odd_ranges = globalRanges;
  else delete payload.allowed_odd_ranges;

  payload.markets = payload.markets && typeof payload.markets === 'object' ? payload.markets : {};
  [...document.querySelectorAll('.cfg-market-enabled')].forEach(input => {
    const market = input.dataset.market;
    const cfg = payload.markets[market] && typeof payload.markets[market] === 'object' ? payload.markets[market] : {};
    document.querySelectorAll(`.cfg-market-input[data-market="${CSS.escape(market)}"]`).forEach(fieldInput => {
      const value = String(fieldInput.value || '').trim();
      cfg[fieldInput.dataset.field] = value === '' ? null : Number(value.replace(',', '.'));
    });
    cfg.is_primary_market = Boolean(document.querySelector(`.cfg-market-primary[data-market="${CSS.escape(market)}"]`)?.checked);
    const ranges = parseRangeText(document.querySelector(`.cfg-market-ranges[data-market="${CSS.escape(market)}"]`)?.value || '');
    if (ranges.length) cfg.allowed_odd_ranges = ranges;
    else delete cfg.allowed_odd_ranges;
    payload.markets[market] = cfg;
  });

  const leagueMode = document.getElementById('cfgLeagueMode')?.value || 'disabled';
  payload.league_filter = {
    enabled: leagueMode !== 'disabled',
    mode: leagueMode,
    allowed_leagues: textLines(document.getElementById('cfgAllowedLeagues')?.value),
    blocked_leagues: textLines(document.getElementById('cfgBlockedLeagues')?.value),
  };

  payload.xg_residual_adjustment = payload.xg_residual_adjustment && typeof payload.xg_residual_adjustment === 'object' ? payload.xg_residual_adjustment : {};
  payload.xg_residual_adjustment.enabled = Boolean(document.getElementById('cfgXgEnabled')?.checked);
  [
    ['cfgXgWeight', 'weight'],
    ['cfgXgMaxResidual', 'max_residual_abs'],
    ['cfgXgMaxLambdaPct', 'max_lambda_adjustment_pct'],
    ['cfgXgMinGames', 'min_games'],
  ].forEach(([id, key]) => {
    const value = numberOrNull(id);
    if (value === null) delete payload.xg_residual_adjustment[key];
    else payload.xg_residual_adjustment[key] = key === 'min_games' ? Math.trunc(value) : value;
  });
  payload.xg_residual_adjustment.markets = textLines(document.getElementById('cfgXgMarkets')?.value);

  payload.rules = payload.rules && typeof payload.rules === 'object' ? payload.rules : {};
  payload.rules.portfolio = payload.rules.portfolio && typeof payload.rules.portfolio === 'object' ? payload.rules.portfolio : {};
  payload.rules.portfolio.max_picks_per_match = numberOrNull('cfgPortfolioMaxMatch');
  payload.rules.portfolio.correlation_selection = payload.rules.portfolio.correlation_selection && typeof payload.rules.portfolio.correlation_selection === 'object'
    ? payload.rules.portfolio.correlation_selection
    : {};
  payload.rules.portfolio.correlation_selection.enabled = Boolean(document.getElementById('cfgCorrelationEnabled')?.checked);
  const evOverride = numberOrNull('cfgPortfolioEvOverride');
  if (evOverride === null) delete payload.rules.portfolio.correlation_selection.ev_gap_override_pp;
  else payload.rules.portfolio.correlation_selection.ev_gap_override_pp = evOverride;

  return payload;
}

function formatCurrentConfigJson() {
  try {
    const el = document.getElementById('cfgRawJson');
    if (!el) return;
    el.value = JSON.stringify(JSON.parse(el.value || '{}'), null, 2);
    setConfigPresetMessage('JSON formatado.', 'ok');
  } catch (err) {
    setConfigPresetMessage(`JSON inválido: ${err.message}`, 'bad');
  }
}

async function validateCurrentConfigPreset() {
  try {
    const detail = state.configPresets.detail;
    const payload = readCurrentConfigPresetPayload();
    const summary = await validateConfigPreset(detail.name, payload);
    renderConfigPresetIssues(summary);
    setConfigPresetMessage(summary.valid ? 'Config válida.' : 'Corrija os erros antes de salvar.', summary.valid ? 'ok' : 'bad');
    return summary;
  } catch (err) {
    setConfigPresetMessage(`Erro de validação: ${err.message}`, 'bad');
    return { valid: false, issues: [{severity:'error', path:'editor', message:err.message}] };
  }
}

async function saveCurrentConfigPreset() {
  const detail = state.configPresets.detail;
  if (!detail) return;
  const summary = await validateCurrentConfigPreset();
  if (!summary.valid) return;
  try {
    const payload = readCurrentConfigPresetPayload();
    const saved = await saveConfigPreset(detail.name, payload);
    state.configPresets.detail = saved;
    renderConfigPresetEditor(saved);
    setConfigPresetMessage(`Config salva. Backup: ${saved.backup_path || 'criado'}.`, 'ok');
    await loadConfigPresets(true);
    await loadEntities();
  } catch (err) {
    setConfigPresetMessage(`Erro ao salvar: ${err.message}`, 'bad');
  }
}

function suggestedConfigCopyName(name) {
  const base = `${name}_copy`;
  const existing = new Set((state.configPresets.items || []).map(item => item.name));
  if (!existing.has(base)) return base;
  let idx = 2;
  while (existing.has(`${base}_${idx}`)) idx += 1;
  return `${base}_${idx}`;
}

async function cloneConfigPresetPrompt(name) {
  const nextName = prompt('Nome do novo preset:', suggestedConfigCopyName(name));
  if (!nextName) return;
  const source = configPresetItem(name);
  const label = prompt('Label:', `${source?.label || name} Copy`) || nextName;
  try {
    const cloned = await cloneConfigPreset(name, { name: nextName, label, description: source?.description || '' });
    setConfigPresetMessage(`Preset clonado: ${cloned.name}.`, 'ok');
    await loadConfigPresets(true);
    await loadEntities();
    await openConfigPreset(cloned.name);
  } catch (err) {
    setConfigPresetMessage(`Erro ao clonar: ${err.message}`, 'bad');
  }
}

async function deleteConfigPresetPrompt(name) {
  const item = configPresetItem(name);
  if (item?.protected) {
    setConfigPresetMessage('Config protegida não pode ser deletada.', 'bad');
    return;
  }
  if (!confirm(`Deletar o preset ${name}?`)) return;
  try {
    await deleteConfigPreset(name);
    if (state.configPresets.selectedName === name) {
      state.configPresets.selectedName = '';
      state.configPresets.detail = null;
      document.getElementById('configPresetEditor').innerHTML = '<div class="state-box"><strong>Nenhuma config selecionada.</strong>Use a lista para abrir outro preset.</div>';
    }
    setConfigPresetMessage(`Preset deletado: ${name}.`, 'ok');
    await loadConfigPresets(true);
    await loadEntities();
  } catch (err) {
    setConfigPresetMessage(`Erro ao deletar: ${err.message}`, 'bad');
  }
}

async function createConfigPresetFromForm() {
  const sourceName = document.getElementById('configPresetCreateSource')?.value || state.configPresets.selectedName;
  const name = document.getElementById('configPresetCreateName')?.value.trim();
  const label = document.getElementById('configPresetCreateLabel')?.value.trim();
  const description = document.getElementById('configPresetCreateDescription')?.value || '';
  if (!name) {
    setConfigPresetMessage('Informe um nome técnico para criar o preset.', 'bad');
    return;
  }
  try {
    const created = await createConfigPreset({ source_name: sourceName, name, label, description });
    setConfigPresetMessage(`Preset criado: ${created.name}.`, 'ok');
    document.getElementById('configPresetCreateName').value = '';
    await loadConfigPresets(true);
    await loadEntities();
    await openConfigPreset(created.name);
  } catch (err) {
    setConfigPresetMessage(`Erro ao criar preset: ${err.message}`, 'bad');
  }
}

Object.assign(window, {
  loadConfigPresets,
  openConfigPreset,
  validateCurrentConfigPreset,
  saveCurrentConfigPreset,
  formatCurrentConfigJson,
  cloneConfigPresetPrompt,
  deleteConfigPresetPrompt,
  createConfigPresetFromForm,
});
