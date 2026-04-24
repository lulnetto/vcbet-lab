# VCBet

Projeto refatorado de UBET para VCBet.

## Entrypoints compatíveis

- `./run_project.sh`
- `python run_service.py`
- `python pipeline_ev.py`
- `python odds_collector.py` antigo `2odds_c.py`
- `python footystats_xg_collector.py` antigo `fs_xg.py`

Wrappers temporários mantêm os nomes antigos funcionando durante a transição.

# Refatoração de ligas centralizadas

## Arquivos
- `ligas.json`: fonte única de configuração das ligas
- `config_ligas.py`: funções utilitárias para carregar ligas por fonte
- `2odds_c.py`: scraper da Betano usando `ligas.json`
- `fs_xg_v2.py`: scraper do FootyStats usando `ligas.json`
- `pipeline_ev.py`: pipeline com validação opcional das ligas presentes no CSV

## Como usar
1. Coloque esses arquivos na mesma pasta do projeto.
2. Ajuste `ligas.json` para adicionar, remover ou desativar ligas.
3. Rode normalmente:
   - `python3 fs_xg_v2.py --debug`
   - `python3 2odds_c.py --d 2026-04-22`
   - `python3 pipeline_ev.py --debug`

## Observações
- Para desativar uma liga sem apagar sua configuração, troque `"ativo": true` para `false`.
- Se uma liga existir apenas no FootyStats ou apenas na Betano, deixe o outro campo como `null`.
- O nome em `nome` é a chave de ligação entre os arquivos gerados.
