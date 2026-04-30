# Ciclo 2A – Auditoria Read-Only dos Descartes de Odds e Ignored Market

## 1. Resumo executivo

O funil **não é auditável ponta a ponta hoje**.

A maior perda de informação ocorre **antes do `odds_snapshot.csv`**: o collector descarta ~3.840 linhas por `unsupported_type_id` e ~416 por `unsupported_market_shape` **sem persistir samples**. Esses descartes só aparecem como contadores agregados no `odds_collection_manifest.json`. Não há como, a partir dos artefatos atuais, reconstruir quais mercados/selections específicas foram perdidas em cada evento.

Após o snapshot, o pipeline é **parcialmente auditável**: `blocked_candidates.csv`, `portfolio_rejected.csv`, `raw_candidates.csv` e `quality_report.json` permitem rastrear cada linha até o motivo de rejeição, mas **não há um único artefato que una a linha original (pre-snapshot) ao motivo final de descarte**.

---

## 2. Mapa do funil atual

| Etapa | Arquivo/Função | O que entra | O que sai | Onde descarta | Motivo registrado? | Persistido? |
|---|---|---|---|---|---|---|
| **1. Coleta Betano** | `odds_collector.py:_parse_event_odds` | Todos os `markets[]` e `selections[]` do JSON do evento | Linhas com `normalized_status == "ok"` | `typeId` não em `SUPPORTED_MARKET_TYPE_IDS` (3.840 na run 192056); `odd <= 0` / `None` / unparseable (silencioso); normalizer retorna `unsupported_scope`, `unparseable_selection`, `unsupported_market_shape` (416 na run) | Sim, como contador agregado (`skipped_unsupported_type_id`, etc.) | Apenas no `odds_collection_manifest.json` (agregado por liga/total). **Nenhuma linha descartada é salva.** |
| **2. Fallback de fetch** | `odds_collector.py:extract_all_odds` | Evento com falha na API | Rows do HTML fallback | Erros de fetch (blocked, timeout, JSON inválido) | Sim, `failure_reason` por evento | No manifest, por evento |
| **3. Snapshot odds** | `odds_collector.py:save_to_csv` | Linhas coletadas com `normalized_status == "ok"` | `odds_snapshot.csv` | — | — | Sim |
| **4. Carregamento pipeline** | `pipeline/input_loader.py:carregar_snapshot_odds` | `odds_snapshot.csv` | `df_betano` | Se CSV legado sem colunas, roda `normalize_odds_dataframe` (pode gerar `ignored_market`, `unknown_market`) | Sim, coluna `normalized_status` | Sim, no DataFrame em memória |
| **5. Filtro base** | `pipeline/filtering_stage.py:build_normalization_filter` | `df_betano` | `df_alvo` | `normalized_status != "ok"`; `market_scope != "full_time"`; `market_type` não em `SUPPORTED_MARKETS` | Sim, `base_filter_discard_counts` | Sim, no `quality_report.json` |
| **6. Skip liga sem xG** | `pipeline/filtering_stage.py` | `df_alvo` | `df_alvo` filtrado | Ligas presentes em odds mas ausentes em xG | Sim, `league_skipped_missing_xg_snapshot` | Sim, no `quality_report.json` |
| **7. Resolução de times** | `pipeline/team_resolution.py:resolve_row_teams` | Cada linha de `df_alvo` | Match ou não | `home_match.matched_name` ou `away_match.matched_name` é `None` | Sim, `processing_discard_counts["unresolved_team_match"]` | Sim, no `quality_report.json` e `alias_review_pending.csv` |
| **8. Pricing** | `pricing_engine.py:price_market_selection` | Linha com times resolvidos | `pricing_result` dict | `market_type`/`side`/`line` não suportados pela Poisson | Sim, `processing_discard_counts["pricing_unavailable"]` | Sim, no `quality_report.json` |
| **9. Pick filter** | `decision_policy.py:evaluate_pick_candidate_with_details` | Candidato precificado | Pick aprovado ou rejeitado | `unsupported_market`, `odd_out_of_range`, `edge_below_min`, `ev_outlier_above_max`, `safety_gate_blocked`, `extended_range_requires_premium_signal`, `low_confidence_or_critical_flag` | **Sim, por linha**, via `decision_reject_reason` e `safety_reject_reason` | `blocked_candidates.csv` (payload completo), `pick_filter_approved.csv`, `quality_report.json` |
| **10. Portfolio/Seleção** | `selection/line_selection.py:select_top_picks` | Candidatos aprovados no pick filter | Picks finais | `DUPLICATE_OR_NEAR_DUPLICATE`, `CONTRADICTORY_LINE_WITH_SELECTED`, `MATCH_PICK_CAP_REACHED`, `HIGH_CORRELATION_WITH_SELECTED`, `MEDIUM_CORRELATION_*`, exposure | **Sim, por linha**, via `portfolio_reject_reason` | `portfolio_rejected.csv`, `picks_snapshot.csv` |
| **11. Quality report** | `pipeline/quality_report.py:build_quality_report` | Todos os contadores e DataFrames | `quality_report.json` | — | Agregado apenas | Sim |
| **12. UI / Dashboard** | `service/dashboard.py`, `service/static/js/components.js` | `bets_ledger.csv` | Visualização de picks executados/liquidados | Não exibe descartes do collector, normalizer ou pipeline | Não | Não |

---

## 3. Pontos cegos críticos

1. **Pre-snapshot: sem sample de linhas descartadas pelo collector**
   - `odds_collector.py` filtra `typeId` não suportado (3.840 na run 192056) e shape inválido (416) **antes** de salvar qualquer coisa.
   - Não existe `odds_discarded.csv` ou similar.
   - O `markets_seen_by_name` e `markets_seen_by_type_id` no manifest mostram **o que foi visto**, mas não **o que foi descartado** linha a linha.

2. **Odds inválidas sem contador explícito**
   - No collector, `odd_value is None`, `odd_float <= 0` ou `ValueError` causam `continue` silencioso.
   - O diag não incrementa um contador para esses casos. Só se deduz pela diferença entre `supported_market_rows_seen` e `supported_market_rows_with_valid_odd`.

3. **Não há traceback do mercado original ao motivo final**
   - Uma linha que passa pelo collector mas é rejeitada no pick filter está em `blocked_candidates.csv`, mas para saber se ela quase foi descartada no collector (ex: typeId suportado mas shape estranho), é preciso cruzar manualmente com o manifest.

4. **UI não expõe descartes**
   - O dashboard lê apenas o ledger (picks aprovados). Não há tela que mostre o funil de 1.402 odds → 2 picks com exemplos de cada descarte.

---

## 4. Motivos de descarte já existentes

| Motivo | Etapa | Arquivo/Função | Granularidade | Persistido? | Observação |
|---|---|---|---|---|---|
| `skipped_unsupported_type_id` | Collector | `odds_collector.py` | Agregado por liga/total | `odds_collection_manifest.json` | Maior descarte (3.840 na run 192056). Sem sample. |
| `skipped_unsupported_market_shape` | Collector | `odds_collector.py` | Agregado por liga/total | `odds_collection_manifest.json` | 416 na run 192056 (ex: typeId 2818/104/503). Sem sample. |
| `skipped_unparseable_selection` | Collector | `odds_collector.py` | Agregado por liga/total | `odds_collection_manifest.json` | 0 na run 192056. Sem sample. |
| `skipped_unsupported_scope` | Collector | `odds_collector.py` | Agregado por liga/total | `odds_collection_manifest.json` | 0 na run 192056. Sem sample. |
| Odd inválida (None, <=0, unparseable) | Collector | `odds_collector.py` | **Não contado** | Não | Diferença entre `supported_market_rows_seen` e `supported_market_rows_with_valid_odd`. |
| `normalized_status_not_ok` | Pipeline filtro base | `filtering_stage.py` | Agregado | `quality_report.json` | 0 na run 192056 (todas as 1.402 eram ok). |
| `unsupported_market_type` | Pipeline filtro base | `filtering_stage.py` | Agregado | `quality_report.json` | 0 na run 192056. |
| `missing_xg_league_snapshot` | Pipeline | `pricing_stage.py` | Agregado | `quality_report.json` | 0 na run 192056. |
| `missing_home_or_away_team` | Pipeline | `pricing_stage.py` | Agregado | `quality_report.json` | 0 na run 192056. |
| `unresolved_team_match` | Pipeline | `team_resolution.py` | Agregado + pending rows | `quality_report.json`, `alias_review_pending.csv` | 88 na run 192056. Cada linha gera entrada no alias_pending se `pending_review`/`blocked`. |
| `pricing_unavailable` | Pipeline | `pricing_engine.py` | Agregado | `quality_report.json` | 0 na run 192056 (Poisson cobre todos os mercados suportados). |
| `pick_filter_odd_out_of_range` | Pick filter | `decision_policy.py` | **Por linha** | `blocked_candidates.csv`, `quality_report.json` | 859 na run 192056. Maior descarte pós-pricing. |
| `pick_filter_edge_below_min` | Pick filter | `decision_policy.py` | **Por linha** | `blocked_candidates.csv`, `quality_report.json` | 365 na run 192056. |
| `pick_filter_ev_outlier_above_max` | Pick filter | `decision_policy.py` | **Por linha** | `blocked_candidates.csv`, `quality_report.json` | 18 na run 192056. |
| `pick_filter_safety_gate_blocked` | Pick filter | `decision_policy.py` | **Por linha** | `blocked_candidates.csv`, `quality_report.json` | 51 na run 192056. Flags detalhadas no CSV. |
| `pick_filter_extended_range_requires_premium_signal` | Pick filter | `decision_policy.py` | **Por linha** | `blocked_candidates.csv`, `quality_report.json` | 6 na run 192056. |
| `pick_filter_low_confidence_or_critical_flag` | Pick filter | `decision_policy.py` | **Por linha** | `blocked_candidates.csv`, `quality_report.json` | 11 na run 192056. |
| `DUPLICATE_OR_NEAR_DUPLICATE` | Portfolio | `selection/line_selection.py` | **Por linha** | `portfolio_rejected.csv` | Não ocorreu na run 192056. |
| `HIGH_CORRELATION_WITH_SELECTED` | Portfolio | `selection/line_selection.py` | **Por linha** | `portfolio_rejected.csv` | 1 na run 192056. |
| `ASIAN_TOTAL_LINE_SUPERSEDED` | Portfolio | `selection/asian_ladder.py` | **Por linha** | `portfolio_rejected.csv` | 1 na run 192056. |
| `MATCH_PICK_CAP_REACHED` | Portfolio | `selection/line_selection.py` | **Por linha** | `portfolio_rejected.csv` | Não ocorreu na run 192056. |
| `MEDIUM_CORRELATION_*` | Portfolio | `selection/line_selection.py` | **Por linha** | `portfolio_rejected.csv` | Não ocorreu na run 192056. |
| Exposure/league/family limit | Portfolio | `selection/exposure.py` | **Por linha** | `portfolio_rejected.csv` | Não ocorreu na run 192056. |

---

## 5. Mercados potencialmente não auditáveis hoje

Baseado exclusivamente no código e nos dados da run 192056:

| Mercado/TypeId | Situação | Evidência |
|---|---|---|
| **Escanteios, Cartões, Chutes no gol, Player props** | Descartados no collector por `typeId` não suportado | `markets_seen_by_type_id` no manifest mostra dezenas de typeIds (ex: 1000111, 1000617, 5000+) com contagem alta. Nenhum sample persistido. |
| **Resultado Final (typeId 1)** | Descartado no collector | Visto no manifest (`"1": N`), mas não suportado. Sem sample. |
| **Intervalo/Final, 1º/2º tempo, Empate Anula** | Descartado no collector ou normalizado como `unsupported_scope` | Visto em `markets_seen_by_name`. Sem sample. |
| **Total de gols Alternativas (typeId 104, 503)** | Aceito pelo collector, mas marcado como `unsupported_market_shape` no normalizer (416 na run) | `skipped_unsupported_market_shape` no manifest. Sem sample de qual selection/line foi descartada. |
| **Exact goals / Range (typeId 2818)** | Idem | `normalize_betano_market_contract` retorna `unsupported_market_shape` para 2818, 104, 503. |
| **Mercados com seleções compostas** | Descartados silenciosamente no `normalize_market_entry` (legacy path) se `COMPOSITE_SELECTION_PATTERN` bater | Não aparece no snapshot porque o collector não usa esse path. Potencial cego se alguém carregar CSV legado. |

---

## 6. Patch recomendado para Ciclo 2B

Objetivo: tornar o funil auditável **sem alterar lógica de negócio**.

### 6.1 Novos artefatos

1. **`odds_discarded_pre_snapshot.csv`** (por run)
   - Uma linha para cada mercado/selection descartado no collector **antes** do snapshot.
   - Colunas: `run_id`, `event_url`, `league`, `match_name`, `market_raw`, `selection_raw`, `betano_market_type_id`, `betano_market_name`, `discard_reason`, `discard_stage`, `odd_raw`, `collected_at`.

2. **`odds_discarded_aggregator.json`** (merge no manifest)
   - Manter a estrutura atual do manifest, mas adicionar `top_discarded_samples` (ex: 20 primeiras linhas por `discard_reason`) para inspeção rápida.

3. **`pipeline_funnel_detail.csv`** (por run)
   - Juntar `raw_candidates.csv` + `blocked_candidates.csv` + `portfolio_rejected.csv` em um único arquivo com a coluna `funnel_stage` (`priced`, `pick_filter_rejected`, `portfolio_rejected`, `final_pick`).
   - **Alternativa mais simples:** garantir que `blocked_candidates.csv` e `portfolio_rejected.csv` já tenham todas as colunas do `odds_snapshot.csv` (incluindo `betano_market_type_id`, `market_raw`, `selection_raw`).

### 6.2 Campos por linha

- No collector: `discard_reason` (ex: `unsupported_type_id:4016`, `invalid_odd`, `unsupported_market_shape:range_exact_goals`).
- No `blocked_candidates.csv`: já tem `decision_reject_reason` e `safety_reject_reason`. Falta expor `typeId`, `market_raw`, `selection_raw` — que já estão no `raw_candidates.csv` mas **não** são propagados para `blocked_candidates.csv` (verificar se estão lá).

### 6.3 Onde instrumentar

| Função | Alteração |
|---|---|
| `odds_collector.py:_parse_event_odds` | Ao invés de `continue` silencioso, chamar `_record_discard(market, sel, reason)` que append em uma lista local e salva no CSV no final da run. |
| `odds_collector.py:extract_all_odds` | Salvar `odds_discarded_pre_snapshot.csv` junto com `odds_snapshot.csv`. |
| `market_normalizer.py:normalize_betano_market_contract` | Garantir que `unsupported_reason` retornado seja incluído no diag do collector (já é, mas verificar se `unknown_selection`/`parse_error` também são contados). |
| `pipeline/output_writer.py:write_candidate_artifacts` | Garantir que `blocked_candidates.csv` e `portfolio_rejected.csv` herdem todas as colunas de identidade do `odds_snapshot.csv` (`betano_market_type_id`, `market_raw`, `selection_raw`, `event_url`). |
| `pipeline/quality_report.py:build_quality_report` | Incluir `top_discarded_samples` no JSON. |

### 6.4 Testes mínimos

- `test_odds_collector.py`: mock de evento com typeId não suportado → assert que `odds_discarded_pre_snapshot.csv` é criado e contém a linha.
- `test_pipeline_ev.py`: rodar pipeline com odds_snapshot conhecido → assert que `blocked_candidates.csv` contém `betano_market_type_id` e `market_raw`.
- `test_data_health.py`: validar que `unsupported_market_rate` continua computando corretamente após adição do novo artefato.

---

## 7. Riscos de quebrar funcionamento

1. **CSV muito grande**: se o collector passar a salvar ~4.000 linhas descartadas por run, o `odds_discarded_pre_snapshot.csv` pode ter 10MB+. Risco baixo se usarmos `writeheader` padrão.
2. **Memória no collector**: manter uma lista de descartes em memória durante a coleta aumenta o footprint, mas é proporcional ao número de mercados (típico: <10k por run). Risco baixo.
3. **Quebra de schema no `blocked_candidates.csv`**: adicionar colunas do snapshot (ex: `betano_market_type_id`) pode quebrar consumidores que esperam schema fixo. No entanto, `output_writer.py` já usa `EXPORT_COLS` extensível. Risco baixo se adicionarmos ao `pick_features.py`/`build_candidate_row`.
4. **Pipeline `input_loader` legacy**: se alguém carregar CSV sem `normalized_status`, o `normalize_odds_dataframe` ainda pode gerar `ignored_market`. O patch não deve alterar esse comportamento, apenas passar a logar.
5. **Nenhum risco em EV, stake, pricing, portfolio, settlement, replay, filtros de pick ou normalização** — o patch proposto é puramente de telemetria/auditoria.

---

## 8. Comandos rodados

```bash
# 1. Busca por termos de descarte no codebase
grep -R "ignored_market\|unsupported_market\|unsupported_reason\|unsupported_scope\|unknown_market\|unknown_selection\|unparseable_selection\|skip\|skipped\|discard\|discarded\|filtered\|blocked\|safety_gate\|pick_filter\|normalized_status" vcbet scripts tests -n

# 2. Listagem de runs com quality report
for f in $(find data/runs -name "quality_report.json" | sort); do
  rows=$(python3 -c "import json; d=json.load(open('$f')); print(d.get('inputs',{}).get('odds_rows_total',0))")
  echo "$rows $f"
done | sort -rn | head -10

# 3. Identificação da run alvo (1402 odds, 1314 precificadas, 2 picks)
# Resultado: data/runs/2026-05-01/run_20260429_192056/quality_report.json

# 4. Leitura do quality_report da run alvo
cat data/runs/2026-05-01/run_20260429_192056/quality_report.json | python3 -m json.tool

# 5. Leitura do odds_collection_manifest da run alvo (totais)
cat data/runs/2026-05-01/run_20260429_192056/odds_collection_manifest.json | python3 -m json.tool | grep -A 20 '"totals"'

# 6. Extração de typeIds vistos vs descartados por liga
python3 -c "
import json
with open('data/runs/2026-05-01/run_20260429_192056/odds_collection_manifest.json') as f:
    d = json.load(f)
for league, diag in d.get('leagues',{}).items():
    if diag.get('events_success',0) > 0:
        seen = diag.get('markets_seen_by_type_id',{})
        skipped = diag.get('skipped_unsupported_type_id',0)
        ok = diag.get('normalized_ok_rows',0)
        non_ok = diag.get('normalized_non_ok_rows',0)
        print(f'{league}: ok={ok} non_ok={non_ok} skipped_type_id={skipped} seen_type_ids={sorted(seen.keys())}')
"

# 7. Análise do odds_snapshot.csv da run alvo
python3 -c "
import pandas as pd
df = pd.read_csv('data/runs/2026-05-01/run_20260429_192056/odds_snapshot.csv', sep=';')
print('Total rows:', len(df))
print('normalized_status counts:')
print(df['normalized_status'].value_counts())
print('market_type counts:')
print(df['market_type'].value_counts())
print('betano_market_type_id counts:')
print(df['betano_market_type_id'].value_counts())
"

# 8. Amostra de blocked_candidates.csv
head -5 data/runs/2026-05-01/run_20260429_192056/blocked_candidates.csv
wc -l data/runs/2026-05-01/run_20260429_192056/blocked_candidates.csv

# 9. Amostra de raw_candidates.csv
head -5 data/runs/2026-05-01/run_20260429_192056/raw_candidates.csv
wc -l data/runs/2026-05-01/run_20260429_192056/raw_candidates.csv

# 10. Leitura dos arquivos-fonte principais
# vcbet/collectors/odds_collector.py
# vcbet/core/market_normalizer.py
# vcbet/core/pipeline/filtering_stage.py
# vcbet/core/pipeline/input_loader.py
# vcbet/core/pipeline/pricing_stage.py
# vcbet/core/pipeline/team_resolution.py
# vcbet/core/pipeline/quality_report.py
# vcbet/core/decision_policy.py
# vcbet/core/risk_policy.py
# vcbet/core/pipeline_ev.py
# vcbet/core/pricing_engine.py
# vcbet/core/team_matcher.py
# vcbet/core/strategy_config.py
# vcbet/core/line_selector.py
# vcbet/core/data_health.py
# vcbet/core/pipeline/output_writer.py
# vcbet/service/dashboard.py
# vcbet/service/static/js/components.js
```

---

*Relatório gerado em 2026-04-29. Nenhum arquivo foi modificado.*
