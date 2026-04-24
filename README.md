# VCBet

VCBet é um sistema de análise operacional de apostas esportivas focado em geração de picks, replay/calibração de configs, coleta de resultados, settlement e operação via API/UI.

O projeto nasceu como **UBET** e passou por uma refatoração estrutural para **VCBet**, preservando o comportamento operacional já funcional e reorganizando o código em um pacote Python mais limpo.

---

## 1. Objetivo do projeto

O VCBet existe para:

- coletar odds do dia
- atualizar base de xG
- precificar mercados
- selecionar picks com filtros de qualidade e correlação
- registrar as entradas em ledger
- coletar resultados reais pós-jogo
- liquidar as entradas
- rodar replays históricos para comparar configs
- operar tudo isso via CLI e via serviço HTTP com UI web

---

## 2. Estado atual do projeto

### Checkpoint funcional atual

O projeto atualmente consegue:

- rodar análise por CLI
- rodar análise por API/UI
- coletar closing odds
- coletar resultados
- liquidar apostas
- fazer replay histórico
- exibir dashboard operacional
- listar jobs e logs
- escolher config na UI/API
- revisar aliases pendentes via UI
- comparar múltiplas configs no replay
- visualizar picks por config no replay

### Mudança estrutural recente

A refatoração mais recente fez:

- rename de **UBET** para **VCBet**
- endurecimento dos imports para `vcbet.*`
- reorganização por domínio funcional
- criação de wrappers temporários e posterior migração gradual
- correção de chamadas de scripts antigos para execução via módulo

---

## 3. Estrutura do projeto

Estrutura lógica atual esperada:

```text
VCBet/
  vcbet/
    __init__.py
    paths.py
    core/
    collectors/
    settlement/
    replay/
    service/
      static/
  configs/
  data/
    history/
    results/
    runs/
    replays/
    service/
  scripts/
  legacy/
  alias_times.json
  ligas.json
  run_project.sh
  run_service.py
  run_service.sh
  requirements.txt
  requirements_service.txt
```

### Responsabilidade por pasta

#### `vcbet/core/`
Camada principal de decisão.

Contém coisas como:

- pipeline principal
- pricing
- normalização de mercado
- filtros de pick
- correlação/portfolio
- matcher de times
- ledger manager
- config strategy

#### `vcbet/collectors/`
Coletores e snapshots.

Contém:

- odds collector
- xG collector
- closing odds collector
- results collector

#### `vcbet/settlement/`
Pós-jogo.

Contém:

- settlement engine
- relatórios do ledger

#### `vcbet/replay/`
Replay e calibração.

Contém:

- replay pipeline
- geração de comparação entre configs
- outputs de replay por run/config

#### `vcbet/service/`
Serviço HTTP + UI.

Contém:

- API
- schemas
- commands
- dashboard
- runner de jobs
- store de jobs
- frontend estático em `static/index.html`

#### `configs/`
Configs versionadas de estratégia.

Presets importantes:

- `champion_strict`
- `intermediate_balanced`
- `legacy_recovered`
- `legacy_v2`

#### `data/`
Dados operacionais e outputs do sistema.

Subpastas importantes:

- `data/history/` → ledger histórico
- `data/results/` → resultados coletados
- `data/runs/` → runs operacionais diárias
- `data/replays/` → replays históricos
- `data/service/` → jobs/logs do serviço

#### `legacy/`
Histórico operacional, docs antigas e artefatos que não devem mais participar do core.

---

## 4. Fluxos principais

## 4.1 Fluxo de análise

A análise diária, em alto nível, faz:

1. coleta odds do dia
2. detecta ligas presentes
3. atualiza snapshot de xG das ligas ativas
4. normaliza mercados e linhas
5. faz match de times
6. precifica candidatos
7. filtra picks
8. aplica regras de portfolio/correlação
9. exporta `picks_snapshot.csv`
10. atualiza o ledger histórico sem duplicar entradas idênticas
11. salva `quality_report.json`

### Entrypoint principal

Hoje o caminho recomendado é:

```bash
python3 -m vcbet.core.pipeline_ev
```

ou via script operacional:

```bash
bash run_project.sh --mode full ...
```

---

## 4.2 Fluxo de pós-jogo

Etapas:

1. closing odds collector
2. results collector
3. settlement engine

### Status importantes no ledger

- `open`
- `settled`
- `postponed`
- `voided`

### Regras importantes

- matching de resultado não deve depender só de `match_name`
- deve considerar pelo menos:
  - liga
  - home_team
  - away_team
  - datetime

---

## 4.3 Fluxo de replay

O replay existe para comparar configs usando uma run histórica como referência.

Ele permite:

- selecionar uma run histórica
- comparar 2 ou mais configs
- ver métricas de overlap/precision/recall/jaccard
- ver picks por config
- opcionalmente checar resultado real das picks do replay

### Métricas importantes do comparison

- `overlap`
- `precision`
- `recall`
- `jaccard`
- `extra_in_candidate`
- `missing_from_candidate`
- `asian_total_line_drift`

---

## 5. Configs e calibração

### Conclusões importantes já levantadas

#### Melhor preset atual para uso prático
Hoje a melhor base para produção é **`legacy_v2`**.

Motivos:

- melhor overlap com a run boa antiga
- melhor precision
- melhor recall
- menor drift de linha em relação às alternativas testadas

#### Presets

##### `legacy_v2`
Melhor equilíbrio atual.

##### `intermediate_balanced`
Challenger razoável, mas mais sujeito a picks extras ruins.

##### `champion_strict`
Mais conservador, porém reproduziu mal a run antiga boa em alguns testes.

##### `legacy_recovered`
Mais permissivo, mas com pior qualidade em vários cenários e ruído maior.

---

## 6. Descobertas importantes de negócio/modelo

### 6.1 Mercado historicamente mais lucrativo no ledger de teste
No `test_ledger`, o melhor mercado foi:

- `asian_total`
- com destaque para `unders`

BTTS foi mais fraco nesse ledger específico.

### 6.2 Problema real da calibração
O problema não era apenas threshold. O replay mostrou problema claro de:

- **drift de linha em asian_total**

Exemplo típico:

- run antiga boa escolhia `under 3.0` + `under 3.75`
- configs novas escolhiam `under 3.25`

Mesmo jogo. Mesma direção. Linha errada.

### 6.3 Problema estrutural ainda em aberto
A seleção de linha/portfolio ainda pode escolher entradas muito correlacionadas ou mesmo contraditórias em sentido econômico.

Exemplo real visto no replay:

- `Real Oviedo +0.5`
- `Real Oviedo -0.25`

Isso indica necessidade de um módulo de **line selection** mais forte.

---

## 7. Sistema de aliases

### Problema
Existem aliases pendentes em `alias_review_pending.csv` que podem impedir o match correto de times, reduzindo cobertura e qualidade da análise.

### Situação atual
Foi adicionada uma aba **Aliases** na UI para:

- listar pendências reais
- aceitar aliases selecionados
- aceitar todos visíveis
- editar target antes de salvar
- persistir no `alias_times.json`

### Regra desejada
- a UI só deve mostrar arquivos com pendência real
- se o CSV de review ficar vazio após aprovação, ele deve ser removido
- `blocked` não significa necessariamente rejeitado, e sim baixa confiança do matcher

---

## 8. Dashboard e UI

### Abas atuais da UI

- Dashboard
- Operação
- Replay
- Aliases
- Jobs

### Melhorias já aplicadas

- janela de log maior em Jobs
- visualização de picks por config no Replay
- multi-config no Replay
- revisão de aliases via UI
- auto refresh parcial de jobs/logs
- tabela operacional maior
- dashboard priorizando data/hora do jogo em vez de apenas “criado em”
- botão de atualizar resultados na operação

### Melhorias ainda desejadas

- UX mais robusta para estados vazios/erros
- auto refresh mais polido
- indicadores de contagem regressiva para kickoff
- status visual melhor para picks abertas/encerradas

---

## 9. Bugs importantes já encontrados e corrigidos

### Sofascore 403
`requests` cru tomava 403.

Solução:

- usar sessão de browser/Playwright

### Matching de nomes de times
Problemas com alias tipo:

- `Levante` vs `Levante UD`
- `Sevilha FC` vs `Sevilla`

Solução:

- normalização + aliases + revisão manual

### Dashboard e delimitador CSV
O `bets_ledger.csv` usa `;`.

Houve leitura errada por `,` e isso foi corrigido com autodetecção.

### Pandas Categorical no dashboard
Bug com `fillna('NA')` em `Categorical` já corrigido.

### Fallback silencioso de config
Config inválida podia cair em default silenciosamente.

Hoje deve falhar explicitamente.

### Execução por caminhos antigos
Houve vários bugs porque o service ainda chamava scripts antigos no root.

Isso foi sendo corrigido para:

```bash
python3 -m vcbet....
```

---

## 10. Regras de ledger e comportamento esperado

### Regra importante
**O ledger histórico não deve reescrever a história silenciosamente.**

### Cenário
Se uma nova execução gerar, para o mesmo jogo/mercado, uma linha diferente da execução anterior, isso não deve sobrescrever retroativamente a pick anterior do ledger oficial.

### Modelo mental correto
Separar:

#### `run snapshot`
Resultado bruto daquela execução.

#### `official picks` / carteira oficial
O que foi realmente aceito/publicado operacionalmente.

#### `bets_ledger`
Histórico imutável do que foi oficialmente levado adiante.

### Recomendação de comportamento
- não sobrescrever passado no ledger
- não duplicar picks idênticas
- picks diferentes da mesma run/config devem viver no snapshot
- promoção para o ledger oficial deve ser explícita

Esse ponto ainda merece endurecimento maior no projeto.

---

## 11. Arquivos e dados importantes

### Arquivos operacionais importantes

- `run_project.sh`
- `run_service.py`
- `alias_times.json`
- `ligas.json`
- `configs/*.json`
- `data/history/bets_ledger.csv`
- `data/results/results_auto.csv`

### Outputs importantes por run

Em `data/runs/<data>/<run_id>/`:

- `odds_snapshot.csv`
- `xg_snapshot.csv`
- `picks_snapshot.csv`
- `quality_report.json`
- possivelmente `alias_review_pending.csv`

### Outputs importantes por replay

Em `data/replays/<data>/<replay_run>/`:

- `picks_snapshot.csv`
- `replay_ledger.csv`
- `quality_report.json`
- `pick_filter_approved.csv`
- `portfolio_rejected.csv`
- `alias_review_pending.csv`
- `comparison_summary.json`

---

## 12. Comandos operacionais recomendados

### Subir o serviço

```bash
python3 run_service.py
```

### Rodar análise por script operacional

```bash
bash run_project.sh --mode full --date 2026-04-24 --alias-file alias_times.json --ledger-file data/history/bets_ledger.csv --output-dir data/runs --python-bin python3 --config-name legacy_v2
```

### Rodar pipeline por módulo

```bash
python3 -m vcbet.core.pipeline_ev
```

### Deduplicar ledger

```bash
PYTHONPATH=. python3 scripts/dedupe_ledger.py --ledger-file data/history/bets_ledger.csv
```

### Aprovar aliases de um CSV

```bash
python3 scripts/approve_alias_review.py --pending-file data/runs/.../alias_review_pending.csv --alias-file alias_times.json
```

---

## 13. Estado atual da arquitetura

### Decisão arquitetural adotada
Não foi feita uma reescrita web-first completa.

A arquitetura escolhida foi:

- preservar o core via CLI
- expor API por cima
- deixar a UI consumir a API
- migrar aos poucos sem quebra operacional

### Por que isso importa
Isso significa que qualquer refatoração futura deve continuar sendo:

- incremental
- reversível
- compatível com o core já funcional

Nada de reescrever tudo por estética.

---

## 14. Próximos passos recomendados

Prioridade alta:

1. endurecer regra entre snapshot da run e ledger oficial
2. melhorar `line_selector` para evitar picks redundantes/correlacionadas
3. melhorar UX do alias review e estados vazios
4. ampliar testes de smoke/regressão
5. criar CLI única `vcbet.cli`

### Próximo passo técnico mais valioso
Criar um módulo tipo:

```text
vcbet/core/line_selector.py
```

Objetivo:

- escolher uma única melhor linha por jogo/mercado/direção
- evitar linhas dominadas ou excessivamente correlacionadas
- reduzir drift estrutural
- registrar motivo de rejeição com clareza

---

## 15. Cuidados para qualquer próximo chat ou refatoração

Quem continuar este projeto deve respeitar estas regras:

- não reescrever tudo do zero
- não quebrar fluxos já funcionais
- sempre auditar antes de mover/apagar
- manter compatibilidade operacional
- usar `python -m vcbet...` em vez de scripts antigos no root
- tratar alias pendente como problema operacional sério
- não permitir sobrescrita silenciosa do ledger histórico
- separar decisões de replay/snapshot da carteira oficial do dia

---

## 16. Resumo executivo

Se alguém pegar o projeto do zero, precisa saber só isso:

- VCBet é a continuação refatorada do UBET
- o sistema já está funcional end-to-end
- a melhor config atual para uso prático é `legacy_v2`
- o maior problema técnico restante é seleção de linha/portfolio
- alias pendente impacta cobertura e precisa de revisão visível
- a UI existe para operar o sistema, não só para visualizar dados
- o ledger não deve ser tratado como snapshot descartável

