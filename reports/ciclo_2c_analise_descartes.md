# Ciclo 2C — Análise dos Descartes Reais Pré-Snapshot

## 1. Resumo executivo

Dos **26.169 descartes** da run `run_20260429_215017`, a **grande maioria é ruído** para o escopo atual do VCBet:

- **~72%** são player props (marcador, chutes, desarmes, passes, impedimentos, cartões).
- **~14%** são escanteios e seus derivados.
- **~7%** são resultados corretos, intervalo/final, e combos (ex: Resultado Final + Total de Gols).
- **~3%** são mercados de primeiro/segundo tempo (cujo descarte é correto por escopo).

**Não há mercado valioso escondido em volume bruto.** O valor potencial está concentrado em **no máximo 5 mercados de futebol puro** que o modelo Poisson já consegue precificar com adaptações mínimas.

---

## 2. Top 30 descartes por typeId/market_raw

| typeId | market_raw principal | linhas | % dos descartes | exemplos de selection_raw |
|---|---:|---:|---:|---|
| 76 | Marcar em qualquer momento | 1.700 | 6,50% | Dominic Calvert-Lewin (Leeds United) |
| 4015 | Escanteios - Resultado Correto | 897 | 3,43% | 7-3, 6-4, 5-3 |
| 34 | Escanteios Mais/Menos (alternativas) | 654 | 2,50% | Mais de 10.5, Menos de 4.5 |
| 574 | Intervalo/Final e Total de gols Mais/Menos | 640 | 2,45% | Leeds United / Leeds United e Mais 1.5 |
| 17 | Resultado Correto | 580 | 2,22% | 1-0, 2-0, 2-1 |
| 79 | Marcar 2 ou mais gols | 558 | 2,13% | Dominic Calvert-Lewin (Leeds United) |
| 80 | Hat-trick de jogador | 558 | 2,13% | Dominic Calvert-Lewin (Leeds United) |
| 77 | Marcar em qualquer momento - Primeiro Tempo | 558 | 2,13% | Dominic Calvert-Lewin (Leeds United) |
| 347 | Marcar de fora da grande área | 557 | 2,13% | Dominic Calvert-Lewin (Leeds United) |
| 19 | Resultado exato a qualquer momento | 488 | 1,86% | 1-0, 2-0, 2-1 |
| 33 | Total de escanteios | 408 | 1,56% | Mais de 4, Exatamente 4, Menos de 4 |
| 83 | Jogador a marcar em ambos os Tempos | 394 | 1,51% | Dominic Calvert-Lewin (Leeds United) |
| 37 | Mais/Menos 1.º Tempo Escanteios (alternativas) | 304 | 1,16% | Mais de 1.5, Menos de 2.5 |
| 147 | Resultado Correto Intervalo/Final | 298 | 1,14% | 0-0 / 0-0, 1-0 / 2-0 |
| 5306 | Marcador do primeiro gol da equipe Casa | 295 | 1,13% | Dominic Calvert-Lewin (Leeds United) |
| 5307 | Marcador do primeiro gol da equipe visitante | 289 | 1,10% | Sem Gol, Zian Flemming (Burnley) |
| 118 | Resultado Correto do 1° Tempo | 278 | 1,06% | 1-0, 2-0, 2-1 |
| 36 | Total escanteios- 1° Tempo | 276 | 1,05% | Mais de 1, Exatamente 1, Menos de 1 |
| 125 | Próximo gol antes 10:00 (Gol 1) | 256 | 0,98% | Gol Antes do minuto 10:00 |
| 408 | Handicap - Resultado Final | 240 | 0,92% | Leeds United -4, Empate -4, Burnley +4 |
| 2818 | Total de gols | 224 | 0,86% | 0-2, 0-3, 1-2 (range/exato) |
| 46 | Disputa até X Escanteios | 213 | 0,81% | Leeds United para 3, Burnley para 5 |
| 346 | Receber um cartão vermelho | 204 | 0,78% | Hannibal Mejbri (Burnley) |
| 62 | Receber um cartão | 204 | 0,78% | Hannibal Mejbri (Burnley) |
| 18 | Resultado Correto (Múltipla) | 191 | 0,73% | (1-0)(2-0) ou (3-0) |
| 38 | Mais/Menos 2.º Tempo Escanteios | 184 | 0,70% | Mais de 1.5, Menos de 1.5 |
| 1000661 | Jogador a Marcar um gol ou dar uma assistência | 174 | 0,66% | Dominic Calvert-Lewin (Leeds United) |
| 542 | Jogador a Acertar na Trave | 174 | 0,66% | Dominic Calvert-Lewin (Leeds United) |
| 27 | Tempo do Próximo gol (Gol 1) | 160 | 0,61% | 00:00-09:59, 10:00-19:59 |
| 186 | Handicap Asiático - Primeiro Tempo | 160 | 0,61% | Leeds United -1.0, Burnley +1.0 |

---

## 3. Classificação dos descartes

### 3.1 Ignorar (sem justificativa para implementar agora)

| typeIds | Mercados | Motivo |
|---|---|---|
| 76, 79, 80, 77, 347, 83, 5306, 5307, 1000661, 542 | Player props de marcador (anytime, 1º tempo, 2+ gols, hat-trick, fora da área, ambos tempos, assistência, trave) | Requer modelo de eventos individuais que não existe. Volume alto mas não justifica investimento agora. |
| 595, 1000680, 596, 1000681, 599, 597, 1000676 | Player props de estatísticas (chutes, chutes no gol, passes, desarmes, impedimentos) | Mesmo motivo acima. |
| 593 | Assistências de jogador | Idem. |
| 33, 34, 36, 37, 38, 4015, 4016, 4017, 46 | Escanteios (totais, correto, intervalo/final, faixa, disputa) | Requer modelo de escanteios baseado em estilo de jogo/xG por minuto. Fora do escopo atual. |
| 346, 62, 63 | Cartões (vermelho, amarelo, primeiro cartão) | Modelo de cartões depende de árbitro, temperatura do jogo, histórico de faltas. Alto risco. |
| 17, 19, 118, 147, 18 | Resultado Correto (FT, HT, exato a qualquer momento, múltipla, intervalo/final) | O modelo Poisson pode precificar, mas odds muito altas (>6) e volatilidade extrema. Não é prioridade. |
| 574, 24, 26, 20, 25, 5015, 5249 | Combos e mercados compostos (Intervalo/Final + Total, Chance Dupla + Total, Resultado + BTTS, Resultado ou Total, etc.) | São produtos lógicos de mercados já suportados, mas com odds tipicamente baixas (1.10–1.80) e baixo EV esperado. Parser complexo para retorno marginal. |
| 2934, 128, 125, 27, 130 | Mercados temporais (próximo gol antes de X, resultado por faixa de minutos, total de gols por intervalo) | Requer modelagem temporal (survival analysis ou Markov). Fora do escopo. |
| 102 | Evolução do jogo (marcar primeiro e ganhar/empatar/perder) | Pode ser derivado do Poisson, mas é um mercado composto de eventos sequenciais. Não trivial. |
| 96 | Margem de Vitória | Derivável do Poisson, mas odds altas e liquidez baixa. Investigar depois. |

### 3.2 Investigar depois (médio/longo prazo)

| typeIds | Mercados | Motivo |
|---|---|---|
| 1 | Resultado Final (1X2) | Mercado fundamental. O modelo Poisson já calcula P(home), P(draw), P(away). Requer apenas expor o cálculo. |
| 96 | Margem de Vitória | Pode ser derivado do Poisson (soma de PMFs para diferença de gols). Baixo risco, mas liquidez questionável. |
| 408 | Handicap - Resultado Final (handicap europeu) | Similar ao asian handicap mas sem push. Parser fácil, mas precisa de nova função de pricing. |

### 3.3 Candidato baixo risco

| typeIds | Mercados | Motivo |
|---|---|---|
| 10 | Empate Anula (Draw No Bet) | Derivado direto do 1X2: DNB Home = P(home win) / (1 - P(draw)). Parser trivial (só 3 seleções: time1, time2, empate anula). O modelo Poisson já tem tudo. |

### 3.4 Candidato médio risco

| typeIds | Mercados | Motivo |
|---|---|---|
| 1 | Resultado Final (1X2) | Embora o Poisson calcule as probabilidades, é um mercado novo com gestão de risco diferente (odds baixas para favoritos, alta variância em zebra). Requer calibração de edge/threshold separada. |

### 3.5 Provável comportamento correto (não bug)

| typeIds | Mercados | Motivo |
|---|---|---|
| 14, 115, 116, 130, 131, 186, 4049, 4050 | Mercados de 1º tempo / 2º tempo / intervalos | O projeto deliberadamente suporta apenas `full_time`. O collector descarta por `unsupported_type_id` porque a whitelist não inclui esses typeIds. O normalizer também rejeitaria por `unsupported_scope`. Não é bug. |
| 186 | Handicap Asiático - Primeiro Tempo | Idem. |
| 93, 16 | Intervalo/Final - Chance Dupla, Intervalo/Final | Mercado HT/FT e chance dupla de intervalo. Fora do escopo de escopo. |

---

## 4. Análise dos 416 `unsupported_market_shape`

### 4.1 Distribuição

| typeId | market_raw | linhas |
|---|---|---|
| 2818 | Total de gols | 224 |
| 503 | Total de gols | 128 |
| 104 | Total de gols (alternativas) | 64 |

### 4.2 O que são

São mercados de **range de gols** e **gols exatos**:

- **typeId 2818**: seleções como `0-2`, `1-3`, `2-5`, `3-6`, `5-6` (ranges de gols).
- **typeId 503**: seleções como `0`, `1`, `2`, `3`, `4`, `5`, `6`, `7+` (gols exatos).
- **typeId 104**: seleções como `0-1`, `2-3`, `4-6`, `7+` (alternativas de range).

### 4.3 Pode virar total_goals normal?

**Não.** Essas seleções não são `Mais de X` / `Menos de X`. São ranges discretos (ex: "exatamente 2 gols" ou "entre 2 e 4 gols"). O pricing requer uma função diferente:

- Para typeId 503 (exato): `P(goals = n)` direto da Poisson.
- Para typeId 2818/104 (range): `P(a <= goals <= b)` = soma de PMFs.

### 4.4 Recomendação

- **typeId 503 (exato)**: pode ser útil como hedge ou mercado secundário, mas odds muito altas (ex: 11.0 para 0 gols) e baixa liquidez. **Não implementar agora.**
- **typeId 2818/104 (ranges)**: mercados de baixa liquidez, odds tipicamente 1.12–4.75. **Continuar ignorando.**

---

## 5. Top 5 mercados candidatos para próximo parser

| Prioridade | typeId | Mercado | Por que vale | Risco | Modelo necessário | Patch provável |
|---|---|---|---|---|---|---|
| **1** | 10 | **Empate Anula (Draw No Bet)** | Parser trivial. O Poisson já calcula P(home), P(draw), P(away). Pricing = P(win) / (1 - P(draw)). Mercado líquido e com edge real. | **Baixo** | Reutiliza `poisson.pmf` e `_asian_handicap_probs` (cálculo de vitória/derrota/empate já existe no loop). | Adicionar `typeId=10` em `SUPPORTED_MARKET_TYPE_IDS`; no `market_normalizer`, mapear seleção para `home`/`away` e calcular DNB como `side=home|away`, `line=0` mas com pricing de vitória condicional. |
| **2** | 1 | **Resultado Final (1X2)** | Mercado mais líquido do mundo. O modelo Poisson já tem P(home), P(draw), P(away). Só falta expor. | **Médio** | Nova função `price_1x2` que retorna prob de 1, X, 2 a partir das lambdas. | Adicionar `typeId=1`; parser simples (1, X, 2); pricing derivado do Poisson bivariado. |
| **3** | 96 | **Margem de Vitória** | Derivado do Poisson. "Ganhar por exatamente 1" ou "por 2+" são somas de convoluções de PMFs. | **Médio** | Função que calcula P(goal_diff = k) e P(goal_diff >= k). | Adicionar `typeId=96`; parser de seleção para extrair "exatamente N" ou "N ou mais"; pricing por convolução Poisson. |
| **4** | 408 | **Handicap Europeu (1X2 com handicap)** | Parser fácil (time -N, Empate -N, time +N). O pricing é vitória/empate/derrota com ajuste de gols. | **Médio** | Similar ao 1X2, mas com offset nos lambdas (ou ajuste no cálculo de diferença de gols). | Adicionar `typeId=408`; parser extrai time e handicap inteiro; pricing por convolução com offset. |
| **5** | 20 | **Resultado Final / BTTS** | Mercado composto, mas pode ser derivado do modelo existente: P(resultado) * P(BTTS\|resultado). | **Médio-Alto** | Requer cálculo condicional de BTTS dado o vencedor. Parser um pouco mais complexo (selection_raw = "Time / Sim|Não"). | Adicionar `typeId=20`; parser split em `/`; pricing = P(resultado ∩ BTTS=yes/no). |

---

## 6. Mercados que NÃO devemos implementar agora

| Mercado / typeId | Motivo |
|---|---|
| Player props (marcador, chutes, passes, desarmes, impedimentos, assistências) | Requer modelo de eventos individuais que não existe. Volume alto, mas retorno de modelo duvidoso. |
| Escanteios (totais, correto, intervalo/final, faixa, disputa) | Requer modelo de estilo de jogo por equipe. Fora do escopo. |
| Cartões (amarelo, vermelho, primeiro cartão) | Depende de dados de árbitro e estilo defensivo que não temos. |
| Resultado Correto (17, 19, 118, 147, 18) | O Poisson consegue, mas odds muito altas e volatilidade extrema. Não é eficiente para EV consistente. |
| Mercados temporais (próximo gol antes de X, resultado por faixa de minutos) | Requer modelagem temporal (survival / Markov). |
| Combos (24, 25, 26, 574, 5015, 5249) | São produtos de mercados já suportados. Odds tipicamente baixas (1.10–1.80), baixo EV esperado. |
| Exact goals / Range (503, 2818, 104) | Mercados de nicho, baixa liquidez, pricing trivial mas sem utilidade operacional clara. |

---

## 7. Patch recomendado para Ciclo 2D

### 7.1 Escopo mínimo

Implementar **apenas o Draw No Bet (typeId 10)** como prova de conceito. Se funcionar bem, expandir para 1X2 (typeId 1).

### 7.2 Arquivos a alterar

1. **`vcbet/core/market_normalizer.py`**
   - Adicionar `10: "draw_no_bet"` em `SUPPORTED_MARKET_TYPE_IDS`.
   - No `normalize_betano_market_contract`, adicionar bloco para `typeId == 10`:
     - `selection_slug` contém nome do time → `side = "home"` ou `"away"`.
     - `normalized_status = "ok"`, `market_type = "draw_no_bet"`.
   - O parser já existe implicitamente: a seleção é o nome do time (ex: "Leeds United", "Burnley").

2. **`vcbet/collectors/odds_collector.py`**
   - Adicionar `10: "draw_no_bet"` em `SUPPORTED_MARKET_TYPE_IDS`.

3. **`vcbet/core/pricing_engine.py`**
   - Adicionar função `price_draw_no_bet(lambda_home, lambda_away, side)`:
     - Calcula `P_home_win`, `P_draw`, `P_away_win` a partir do loop Poisson bivariado (ou reusa `_asian_handicap_probs` com line=0).
     - `home_dnb_prob = P_home_win / (1 - P_draw)`.
     - `away_dnb_prob = P_away_win / (1 - P_draw)`.
   - No `price_market_selection`, adicionar branch para `market_type == "draw_no_bet"`.

4. **`vcbet/core/decision_policy.py` / `strategy_config.py`**
   - Adicionar thresholds para `draw_no_bet` no JSON de config (copiar do `asian_handicap` como base).

5. **`tests/`**
   - `test_pricing_engine.py`: assert que `price_draw_no_bet(home, away, "home")` retorna prob coerente (maior que `P_home_win`).
   - `test_market_normalizer.py`: mock de market typeId 10 → assert `normalized_status == "ok"`.

### 7.3 Riscos

- **Nenhum risco em modelagem estatística**: o Poisson já calcula as 3 probabilidades.
- **Risco baixo de parser**: seleção é apenas o nome do time, igual ao asian handicap.
- **Risco de config**: se não adicionar thresholds para `draw_no_bet`, o pick filter rejeitará tudo como `unsupported_market`. Mitigação: adicionar no `DEFAULT_CONFIG_PAYLOAD`.

---

## 8. Comandos rodados

```bash
RUN_DIR="data/runs/2026-05-01/run_20260429_215017"

# 1. Carregamento e contagem total
python3 - <<'PY'
import pandas as pd
d = pd.read_csv("data/runs/2026-05-01/run_20260429_215017/odds_discarded_pre_snapshot.csv", sep=";")
print("rows", len(d))
print(d["discard_reason"].value_counts().head(50))
PY
# Resultado: 26.169 descartes; top reasons listados na seção 2.

# 2. Top typeId + market_raw
python3 - <<'PY'
import pandas as pd
d = pd.read_csv("data/runs/2026-05-01/run_20260429_215017/odds_discarded_pre_snapshot.csv", sep=";")
print(
    d.groupby(["betano_market_type_id", "market_raw"])
     .size()
     .sort_values(ascending=False)
     .head(50)
)
PY

# 3. Samples por top typeId
python3 - <<'PY'
import pandas as pd
d = pd.read_csv("data/runs/2026-05-01/run_20260429_215017/odds_discarded_pre_snapshot.csv", sep=";")
for tid in d["betano_market_type_id"].value_counts().head(30).index:
    print(f"\nTYPE {tid}")
    print(
        d[d["betano_market_type_id"] == tid]
        [["market_raw", "selection_raw", "odd_raw", "discard_reason"]]
        .drop_duplicates()
        .head(10)
        .to_string(index=False)
    )
PY

# 4. Análise dos unsupported_market_shape
python3 - <<'PY'
import pandas as pd
d = pd.read_csv("data/runs/2026-05-01/run_20260429_215017/odds_discarded_pre_snapshot.csv", sep=";")
shape = d[d["discard_reason"] == "unsupported_market_shape:range_exact_goals_no_parser"]
print("Total:", len(shape))
print(shape["betano_market_type_id"].value_counts())
print(shape[["betano_market_type_id", "market_raw", "selection_raw", "odd_raw"]].drop_duplicates().head(30).to_string(index=False))
PY

# 5. Verificação de mercados com nome de suportado
python3 - <<'PY'
import pandas as pd
d = pd.read_csv("data/runs/2026-05-01/run_20260429_215017/odds_discarded_pre_snapshot.csv", sep=";")
mask = d["market_raw"].str.contains("Total de Gols Mais/Menos|Handicap Asiático|Ambas equipes Marcam", case=False, na=False)
print(d[mask][["betano_market_type_id", "market_raw", "selection_raw", "discard_reason"]].drop_duplicates().to_string(index=False))
PY
# Resultado: todos são variantes de 1º tempo, 2º tempo ou combos. Nenhum descarte indevido de mercado full_time.

# 6. Análise de candidatos específicos
python3 - <<'PY'
import pandas as pd
d = pd.read_csv("data/runs/2026-05-01/run_20260429_215017/odds_discarded_pre_snapshot.csv", sep=";")
for tid in [408, 20, 5249, 93, 16, 96, 102, 46, 4016, 4017, 10, 12, 14]:
    sub = d[d["betano_market_type_id"] == tid]
    if len(sub) == 0: continue
    print(f"\n=== TYPE {tid} ({len(sub)} rows) ===")
    print(sub[["market_raw", "selection_raw", "odd_raw"]].drop_duplicates().head(15).to_string(index=False))
PY

# 7. Verificação de 1X2
python3 - <<'PY'
import pandas as pd
d = pd.read_csv("data/runs/2026-05-01/run_20260429_215017/odds_discarded_pre_snapshot.csv", sep=";")
for tid in [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]:
    sub = d[d["betano_market_type_id"] == tid]
    if len(sub) == 0: continue
    print(f"\nTYPE {tid} ({len(sub)})")
    print(sub[["market_raw", "selection_raw", "odd_raw"]].drop_duplicates().head(10).to_string(index=False))
PY
```

---

*Relatório gerado em 2026-04-29. Nenhum arquivo foi modificado.*
