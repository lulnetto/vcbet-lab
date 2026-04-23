# Checkpoint estável sugerido antes da refatoração

## Objetivo
Congelar um estado operacional confiável antes de reorganizar pastas, remover arquivos e renomear módulos.

## Checklist do checkpoint
- Serviço sobe com `python3 run_service.py`
- UI responde em `/`
- Dashboard responde sem 500
- `GET /configs` lista `legacy_v2`
- Jobs via API funcionam:
  - analysis
  - daily-run
  - results-collection
  - settlement
  - replay-run
- `legacy_v2` disponível na UI e executável
- Replay histórico de 22/04 fecha com métricas coerentes
- Etapa 7 continua estável:
  - results_collector
  - settlement_engine
  - overrides

## Próxima fase de refatoração
1. Congelar árvore atual em tag/checkpoint
2. Mapear arquivos órfãos e duplicados
3. Separar em pastas:
   - `ubet/core`
   - `ubet/domain`
   - `ubet/services`
   - `ubet/web`
   - `scripts/`
   - `configs/`
   - `data/`
4. Transformar scripts principais em entrypoints finos
5. Centralizar schemas e config loading
6. Padronizar nomes de arquivos e módulos
7. Remover legado morto só depois de smoke tests

## Regra importante
Não mexer em nomes e caminhos ao mesmo tempo que muda regra de negócio.
Primeiro congelar comportamento, depois limpar estrutura.
