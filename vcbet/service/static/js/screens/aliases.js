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

Object.assign(window, {
  loadAliasFiles,
  loadAliasReview,
  renderAliasReviewTable,
  collectAliasApprovals,
  approveSelectedAliases,
  approveAllVisibleAliases,
});
