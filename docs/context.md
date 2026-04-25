# VCBet Context Exclusion Policy

## Objective

This file defines what should not be included in LLM/audit context by default. The goal is to keep audits focused on source, configuration, tests, and docs while avoiding runtime state, generated outputs, caches, historical artifacts, and large debug files.

## Exclusion Rules

- `.git/**`
- `.codex`
- `.codex/**`
- `data/**`
- `dev_asset/**`
- `**/__pycache__/**`
- `*.pyc`
- `.venv/**`
- `venv/**`
- `*.log`
- `*.tmp`
- `*.bak`
- `.pytest_cache/**`
- `.mypy_cache/**`
- `.ruff_cache/**`
- `*.pyo`
- `*.pyd`
- `legacy/history_snapshots/**` for architecture audits unless the task is specifically about legacy ledger snapshots.

## Excluded Tree

Compact inventory of excluded paths. Sizes/counts are approximate filesystem metadata only; large files were not dumped.

| Path | Approx size | Approx files | Why excluded | Include by exception? |
| --- | ---: | ---: | --- | --- |
| `.git` | 865.5 KB | 462 | Git metadata. Never useful for architecture audit payloads. | No, except rare history/forensics tasks. |
| `.codex` | 0 B | 1 | Local Codex metadata placeholder/file. Not source behavior. | No, except context tooling review. |
| `data/history` | 80.7 KB | 4 | Operational ledger/history state. | Only for ledger/settlement audit with tiny samples. |
| `data/runs` | 21.5 MB | 93 | Generated per-run odds/xG/pick artifacts. | Only for debugging one specific run. |
| `data/replays` | 18.4 MB | 216 | Generated replay/comparison outputs. | Only for debugging one specific replay/comparison. |
| `data/results` | 3.6 KB | 3 | Collected result CSVs and debug result artifacts. | Only for results/settlement bugs. |
| `data/service` | 0 B | 2 | Service job metadata and logs. | Only for service execution bugs. |
| `data/team_registry` | 18.0 KB | 3 | Runtime team registry queues, snapshots, debug artifacts. | Only for alias sync/review bugs. |
| `data/_archive` | 7.9 MB | 193 | Archived/generated historical artifacts. | No by default; include one artifact only by request. |
| `dev_asset` | 0 B | 0 | Local debug/scraping assets. | No by default. |
| `legacy/history_snapshots` | 19.9 KB | 7 | Tracked legacy ledger snapshots, not active source. | Only for legacy ledger migration/recovery. |
| `scripts/__pycache__` | 35.8 KB | 4 | Python bytecode cache recreated by test/runtime commands. | No. |
| `tests/__pycache__` | 85.0 KB | 15 | Python bytecode cache recreated by test/runtime commands. | No. |
| `vcbet/__pycache__` | 1.3 KB | 2 | Python bytecode cache recreated by test/runtime commands. | No. |
| `vcbet/collectors/__pycache__` | 33.6 KB | 3 | Python bytecode cache recreated by test/runtime commands. | No. |
| `vcbet/core/__pycache__` | 119.2 KB | 18 | Python bytecode cache recreated by test/runtime commands. | No. |
| `vcbet/replay/__pycache__` | 24.4 KB | 2 | Python bytecode cache recreated by test/runtime commands. | No. |
| `vcbet/service/__pycache__` | 87.0 KB | 10 | Python bytecode cache recreated by test/runtime commands. | No. |
| `vcbet/settlement/__pycache__` | 16.5 KB | 3 | Python bytecode cache recreated by test/runtime commands. | No. |

## Representative Samples of Excluded Content

Samples below are intentionally tiny and metadata-oriented. They are examples of shape, not audit evidence.

### `data/history/`

- `data/history/bets_ledger.csv`: 60.3 KB, CSV/history state.
```csv
bet_id;ledger_schema_version;ledger_schema_status;ledger_schema_missing_columns;run_id;config_name;config_fingerprint;config_source_path;config_snapshot_file;source_run_id;source_snapshot_ref;odds_source_run_id;xg_source_run_id;odds_snapshot_file;xg_snapshot_file;odds_snapshot_hash;xg_snapshot_hash;odds_snapshot_time;xg_asof;temporal_contract_version;temporal_contract_status;signal_version;pipeline_version;decision_timestamp;created_at;settled_at;league;match_datetime;home_team;away_team;match_name;market_raw;event_url;market_type;market_scope;target_team_role;target_team_name;side;line;selection_raw;odd_entrada;odd_justa;prob_model;ev_percent;pricing_signal_type;confidence_score;confidence_score_type;confidence_score_scale;stake_units;entry_reason;risk_flags;pick_safety_status;candidate_stage;safety_gate_reason;decision_policy_status;decision_reject_reason;selection_policy_status;selection_reject_reason;portfolio_risk_status;portfolio_risk_reason;portfolio_exposure_scope;portfolio_exposure_after;ledger_portfolio_gate_status;ledger_portfolio_gate_reason;ledger_portfolio_related_bet_id;ledger_portfolio_gate_details;market_family;bet_executed;executed_at;odd_executada;stake_units_executada;execution_note;auto_home_goals;auto_away_goals;auto_bet_status;auto_settlement_status;auto_odd_fechamento;manual_home_goals;manual_away_goals;manual_bet_status;manual_settlement_status;manual_odd_fechamento;final_home_goals;final_away_goals;final_bet_status;final_settlement_status;final_odd_fechamento;closing_odd;closing_bookmaker;closing_snapshot_time;closing_source;closing_update_status;closing_update_error;settlement_source;settlement_confidence;settlement_note;override_reason;override_updated_at;result_units_model;result_units_real
443cbdec04a4;phase11_csv_v1;compatible_missing_optional;closing_bookmaker|closing_odd|closing_snapshot_time|closing_source|closing_update_error|closing_update_status|confidence_score_scale|confidence_score_type|ledger_portfolio_gate_details|ledger_portfolio_gate_reason|ledger_portfolio_gate_status|ledger_portfolio_related_bet_id|pricing_signal_type;run_20260423_004727;;;;;;;;;;;;;;;;;;;;2026-04-23 00:48:30;2026-04-23 17:26:28;La Liga;2026-04-23 15:00;Rayo Vallecano;Espanyol;Rayo Vallecano - Espanyol;Total de Gols Mais/Menos;https://www.betano.bet.br/odds/rayo-vallecano-espanyol/82821106/;total_goals;full_time;geral;geral;over;2.5;Mais de 2.5;2.15;1.75;0.571186;22.8;;5;;;1.0;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|LIGA_ESTAVEL;SEM_FLAG;;;;;;;;;;;;;;;;;no;;;;;1.0;0.0;settled;pending;;;;;;;1.0;0.0;settled;loss;;;;;;;;sofascore_browser;high;"placar final coletado automaticamente via Sofascore | matched_via=team_score=180;home=70;away=70;dt=40 | source_event_id=14083330";;;-1.0;
024fdba5a0a7;phase11_csv_v1;compatible_missing_optional;closing_bookmaker|closing_odd|closing_snapshot_time|closing_source|closing_update_error|closing_update_status|confidence_score_scale|confidence_score_type|ledger_portfolio_gate_details|ledger_portfolio_gate_reason|ledger_portfolio_gate_status|ledger_portfolio_related_bet_id|pricing_signal_type;run_20260423_004727;;;;;;;;;;;;;;;;;;;;2026-04-23 00:48:30;2026-04-23 16:11:41;La Liga;2026-04-23 14:00;Levante;Sevilha FC;Levante - Sevilha FC;Total de Gols Mais/Menos;https://www.betano.bet.br/odds/levante-sevilha-fc/80074591/;total_goals;full_time;geral;geral;over;2.5;Mais de 2.5;2.15;1.82;0.54823;17.87;;5;;;1.0;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|LIGA_ESTAVEL;SEM_FLAG;;;;;;;;;;;;;;;;;no;;;;;2.0;0.0;settled;pending;;;;;;;2.0;0.0;settled;loss;;;;;;;;sofascore_browser;high;"placar final coletado automaticamente via Sofascore | matched_via=team_score=180;home=70;away=70;dt=40 | source_event_id=14083265";;;-1.0;
```
- `data/history/ch_bets_ledger.csv`: 9.0 KB, CSV/history state.
```csv
bet_id;run_id;config_name;config_fingerprint;config_source_path;config_snapshot_file;source_run_id;source_snapshot_ref;odds_source_run_id;xg_source_run_id;odds_snapshot_file;xg_snapshot_file;odds_snapshot_hash;xg_snapshot_hash;odds_snapshot_time;xg_asof;temporal_contract_version;temporal_contract_status;signal_version;pipeline_version;decision_timestamp;created_at;settled_at;league;match_datetime;home_team;away_team;match_name;market_raw;event_url;market_type;market_scope;target_team_role;target_team_name;side;line;selection_raw;odd_entrada;odd_justa;prob_model;ev_percent;confidence_score;stake_units;entry_reason;risk_flags;pick_safety_status;candidate_stage;safety_gate_reason;decision_policy_status;decision_reject_reason;selection_policy_status;selection_reject_reason;portfolio_risk_status;portfolio_risk_reason;portfolio_exposure_scope;portfolio_exposure_after;market_family;bet_executed;executed_at;odd_executada;stake_units_executada;execution_note;auto_home_goals;auto_away_goals;auto_bet_status;auto_settlement_status;auto_odd_fechamento;manual_home_goals;manual_away_goals;manual_bet_status;manual_settlement_status;manual_odd_fechamento;final_home_goals;final_away_goals;final_bet_status;final_settlement_status;final_odd_fechamento;settlement_source;settlement_confidence;settlement_note;override_reason;override_updated_at;result_units_model;result_units_real
95ea84407b79;run_20260424_141824;champion_strict;4612cb65e0fa;;/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/strategy_config_snapshot.json;run_20260424_141824;odds:/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/odds_snapshot.csv|xg:/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/xg_snapshot.csv;run_20260424_141824;run_20260424_141824;/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/odds_snapshot.csv;/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/xg_snapshot.csv;6941b96a180864e81c61f9f8bd4357c1;93eb211002dc09e609207fd6aa611471;2026-04-24 14:19:21;2026-04-24 14:19:26;temporal_contract_v1;complete;ev_pipeline_v1;pipeline_ev_phase3_provenance;2026-04-24 14:19:54;2026-04-24 14:19:54;2026-04-24 18:19:35;Bundesliga;2026-04-24 15:30;RB Leipzig;1. FC Union Berlin;RB Leipzig - 1. FC Union Berlin;Handicap Asiático (Resultado atual 0 - 0);https://www.betano.bet.br/odds/rb-leipzig-1-fc-union-berlin/83205460/;asian_handicap;full_time;away;1. FC Union Berlin;away;0.75;1. FC Union Berlin +0.75;2.52;1.74;0.576004;40.18;5;1.0;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|MATCH_CONFIAVEL;SEM_FLAG;safe;official_accepted_pick;;eligible;;selected;;accepted;;league:Bundesliga=1.00u|market_family:handicap=1.50u;1.5;handicap;no;;;;;3.0;1.0;settled;pending;;;;;;;3.0;1.0;settled;loss;;sofascore_browser;high;"placar final coletado automaticamente via Sofascore | matched_via=team_score=180;home=70;away=70;dt=40 | source_event_id=14065257.0";;;-1.0;
c3eaff065a3b;run_20260424_141824;champion_strict;4612cb65e0fa;;/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/strategy_config_snapshot.json;run_20260424_141824;odds:/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/odds_snapshot.csv|xg:/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/xg_snapshot.csv;run_20260424_141824;run_20260424_141824;/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/odds_snapshot.csv;/mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260424_141824/xg_snapshot.csv;6941b96a180864e81c61f9f8bd4357c1;93eb211002dc09e609207fd6aa611471;2026-04-24 14:19:21;2026-04-24 14:19:26;temporal_contract_v1;complete;ev_pipeline_v1;pipeline_ev_phase3_provenance;2026-04-24 14:19:54;2026-04-24 14:19:54;2026-04-24 18:26:25;Serie B;2026-04-24 16:00;US Avellino;AS Bari;US Avellino - AS Bari;Asiático (Mais/Menos) Total de gols;https://www.betano.bet.br/odds/us-avellino-as-bari/83377843/;asian_total;full_time;geral;geral;over;2.75;Mais de 2.75;2.37;2.03;0.492708;14.9;4;0.5;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|MATCH_CONFIAVEL;LIGA_VOLATIL;safe;official_accepted_pick;;eligible;;selected;;accepted;;league:Serie B=0.50u|market_family:goals_total=0.50u;0.5;goals_total;no;;;;;2.0;0.0;settled;pending;;;;;;;2.0;0.0;settled;loss;;sofascore_browser;high;"placar final coletado automaticamente via Sofascore | matched_via=team_score=140;home=50;away=50;dt=40 | source_event_id=14317598";;;-0.5;
```
- `data/history/bets_ledger.csv.bak`: 8.7 KB, CSV/history state.
```csv
bet_id;run_id;created_at;settled_at;league;match_datetime;home_team;away_team;match_name;market_raw;event_url;market_type;market_scope;target_team_role;target_team_name;side;line;selection_raw;odd_entrada;odd_justa;prob_model;ev_percent;confidence_score;stake_units;entry_reason;risk_flags;bet_executed;executed_at;odd_executada;stake_units_executada;execution_note;auto_home_goals;auto_away_goals;auto_bet_status;auto_settlement_status;auto_odd_fechamento;manual_home_goals;manual_away_goals;manual_bet_status;manual_settlement_status;manual_odd_fechamento;final_home_goals;final_away_goals;final_bet_status;final_settlement_status;final_odd_fechamento;settlement_source;settlement_confidence;settlement_note;override_reason;override_updated_at;result_units_model;result_units_real
443cbdec04a4;run_20260423_004727;2026-04-23 00:48:30;2026-04-23 17:26:28;La Liga;2026-04-23 15:00;Rayo Vallecano;Espanyol;Rayo Vallecano - Espanyol;Total de Gols Mais/Menos;https://www.betano.bet.br/odds/rayo-vallecano-espanyol/82821106/;total_goals;full_time;geral;geral;over;2.5;Mais de 2.5;2.15;1.75;0.571186;22.8;5;1.0;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|LIGA_ESTAVEL;SEM_FLAG;no;;;;;1.0;0.0;settled;pending;;;;;;;1.0;0.0;settled;loss;;sofascore_browser;high;"placar final coletado automaticamente via Sofascore | matched_via=team_score=180;home=70;away=70;dt=40 | source_event_id=14083330";;;-1.0;
024fdba5a0a7;run_20260423_004727;2026-04-23 00:48:30;2026-04-23 16:11:41;La Liga;2026-04-23 14:00;Levante;Sevilha FC;Levante - Sevilha FC;Total de Gols Mais/Menos;https://www.betano.bet.br/odds/levante-sevilha-fc/80074591/;total_goals;full_time;geral;geral;over;2.5;Mais de 2.5;2.15;1.82;0.54823;17.87;5;1.0;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|LIGA_ESTAVEL;SEM_FLAG;no;;;;;2.0;0.0;settled;pending;;;;;;;2.0;0.0;settled;loss;;sofascore_browser;high;"placar final coletado automaticamente via Sofascore | matched_via=team_score=180;home=70;away=70;dt=40 | source_event_id=14083265";;;-1.0;
```
### `data/results/`

- `data/results/results_auto.csv`: 2.6 KB, CSV result/override state.
```csv
league;match_name;home_team;away_team;home_goals;away_goals;bet_status;settlement_source;settlement_confidence;settlement_note;source_url;matched_via;status_raw;source_event_id;match_datetime
Serie A;Parma Calcio 1913 - AC Pisa 1909;Parma;Pisa;1;0;settled;sofascore_browser;high;placar final coletado automaticamente via Sofascore;https://www.sofascore.com/api/v1/unique-tournament/23/season/76457/events/last/0;"team_score=140;home=50;away=50;dt=40";finished|Ended;13980107;2026-04-25 13:00:00
Serie B;FC Sudtirol - Mantova FC;Südtirol;Mantova;0;3;settled;sofascore_browser;high;placar final coletado automaticamente via Sofascore;https://www.sofascore.com/api/v1/unique-tournament/53/season/79502/events/last/0;"team_score=180;home=70;away=70;dt=40";finished|Ended;14317625;2026-04-25 13:00:00
```
- `data/results/results_overrides.csv`: 214 B, CSV result/override state.
```csv
bet_id;match_name;manual_home_goals;manual_away_goals;manual_bet_status;manual_settlement_status;manual_odd_fechamento;odd_executada;stake_units_executada;bet_executed;executed_at;execution_note;override_reason
```
- `data/results/ch_results_auto.csv`: 817 B, CSV result/override state.
```csv
league;match_name;home_team;away_team;home_goals;away_goals;bet_status;settlement_source;settlement_confidence;settlement_note;source_url;matched_via;status_raw;source_event_id;match_datetime
Serie B;US Avellino - AS Bari;US Avellino 1912;Bari;2;0;settled;sofascore_browser;high;placar final coletado automaticamente via Sofascore;https://www.sofascore.com/api/v1/unique-tournament/53/season/79502/events/last/0;"team_score=140;home=50;away=50;dt=40";finished|Ended;14317598;2026-04-24 19:00:00
Ligue 2;Stade Lavallois MFC - Rodez AF;Stade Lavallois;Rodez AF;0;0;settled;sofascore_browser;high;placar final coletado automaticamente via Sofascore;https://www.sofascore.com/api/v1/unique-tournament/182/season/77357/events/last/0;"team_score=160;home=50;away=70;dt=40";finished|Ended;14064777;2026-04-24 18:00:00
```
### `data/runs/`

- `data/runs/catalog.jsonl`: 9.9 KB, JSON/JSONL generated run metadata; top-level keys only: alias_pending_rows, catalog_version, config_fingerprint, config_name, created_at, ledger_file, manifest_file, manifest_schema_quality, picks_file, picks_rows, pipeline_version, quality_report_file, run_dir, run_id, run_mode, status, target_date, temporal_contract_status, updated_at.
- `data/runs/2026-04-25/run_20260425_100729/run_manifest.json`: 2.7 KB, JSON/JSONL generated run metadata; top-level keys only: run_id, target_date, created_at, run_dir, status, odds_snapshot_file, xg_snapshot_file, xg_rows, xg_snapshot_hash, xg_asof, temporal_contract_version, xg_target_leagues, updated_at, picks_file, picks_rows, ledger_file, ledger_added_rows, ledger_total_rows, alias_pending_file, alias_pending_rows.
- `data/runs/2026-04-25/run_20260425_100729/odds_snapshot.csv`: 3.3 MB, generated CSV; header + first 2 rows only.
```csv
run_id;collected_at;source;league;match_datetime;home_team;away_team;match_name;market_raw;selection_raw;odd;event_url;market_type;market_scope;side;line;target_team_role;target_team_name;normalized_status
run_20260425_100729;2026-04-25 10:07:30;betano;Premier League;2026-04-25 11:00;Liverpool;Crystal Palace;Liverpool - Crystal Palace;Total de Gols Mais/Menos;Mais de 3.5;2.32;https://www.betano.bet.br/odds/liverpool-crystal-palace/83978504/;total_goals;full_time;over;3.5;geral;geral;ok
run_20260425_100729;2026-04-25 10:07:30;betano;Premier League;2026-04-25 11:00;Liverpool;Crystal Palace;Liverpool - Crystal Palace;Total de Gols Mais/Menos (alternativas);Menos de 0.5;12.0;https://www.betano.bet.br/odds/liverpool-crystal-palace/83978504/;;full_time;;;;;ignored_market
```
### `data/replays/`

- `data/replays/catalog.jsonl`: 16.2 KB, replay/comparison metadata; top-level keys only: catalog_version, configs, created_at, manifest_file, manifest_schema_quality, replay_dir, replay_id, replay_mode, replay_strength, source_run_dir, status, summary_file, target_date, updated_at.
- `data/replays/2026-04-25/comparison_run_20260425_100729/comparison_summary.json`: 192.2 KB, replay/comparison metadata; top-level keys only: none detected.
- `data/replays/2026-04-25/replay_run_20260425_100729_legacy_v2/raw_candidates.csv`: 1.0 MB, generated replay CSV; header + first 2 rows only.
```csv
run_id;odds_source_run_id;xg_source_run_id;generated_at;league;match_datetime;home_team;away_team;match_name;market_type;market_scope;market_raw;selection_raw;line;side;target_team_role;target_team_name;event_url;odd_entrada;prob_model;odd_justa;ev_decimal;mu_total;lambda_home;lambda_away;match_status_home;match_status_away;match_source_home;match_source_away;alias_confidence_home;alias_confidence_away;registry_file_home;registry_file_away;xg_fallback_home;xg_fallback_away;candidate_stage
replay_run_20260425_100729_legacy_v2;run_20260425_100729;run_20260425_100729;2026-04-25 12:57:19;Premier League;2026-04-25 11:00;Liverpool;Crystal Palace;Liverpool - Crystal Palace;total_goals;full_time;Total de Gols Mais/Menos;Mais de 3.5;3.5;over;geral;geral;https://www.betano.bet.br/odds/liverpool-crystal-palace/83978504/;2.32;0.33709;2.9665711628972335;-0.21795235219160392;2.93;1.725;1.205;MATCH_REGISTRY_APPROVED;MATCH_REGISTRY_APPROVED;team_registry;team_registry;1.0000;1.0000;configs/team_registry/betano_footystats_aliases.csv;configs/team_registry/betano_footystats_aliases.csv;False;False;raw_candidate
replay_run_20260425_100729_legacy_v2;run_20260425_100729;run_20260425_100729;2026-04-25 12:57:19;Premier League;2026-04-25 11:00;Liverpool;Crystal Palace;Liverpool - Crystal Palace;btts;full_time;Ambas equipes Marcam;Não;;no;geral;geral;https://www.betano.bet.br/odds/liverpool-crystal-palace/83978504/;2.27;0.424468;2.355890123734584;-0.03645761017004889;2.93;1.725;1.205;MATCH_REGISTRY_APPROVED;MATCH_REGISTRY_APPROVED;team_registry;team_registry;1.0000;1.0000;configs/team_registry/betano_footystats_aliases.csv;configs/team_registry/betano_footystats_aliases.csv;False;False;raw_candidate
```
### `data/service/` and archived service artifacts

- `data/service/`: no current non-`.gitkeep` service job/log files after the previous cleanup pass.
- `data/_archive/pre_cycle7_cleanup/data/service/jobs/job_20260423_221031_25499bf9.json`: 3.0 KB, archived job JSON; top-level keys only: id, job_type, status, title, created_at, started_at, finished_at, resource_key, request, phases, log_path, exit_code, error, command_preview.
- `data/_archive/pre_cycle7_cleanup/data/service/logs/job_20260423_221031_25499bf9.log`: 8.1 KB, archived log; first 5 lines only.
```text
=== [2026-04-23T22:10:31.865094] INICIO analysis ===
$ bash /mnt/c/Users/Netto/Documents/VCBet/run_project.sh --mode full --date 2026-04-24 --alias-file /mnt/c/Users/Netto/Documents/VCBet/alias_times.json --ledger-file /mnt/c/Users/Netto/Documents/VCBet/data/history/bets_ledger.csv --output-dir /mnt/c/Users/Netto/Documents/VCBet/data/runs --python-bin python3 --config-name legacy_v2
[FULL] Run ID: run_20260423_221031
[FULL] Data:   2026-04-24
[FULL] Pasta:  /mnt/c/Users/Netto/Documents/VCBet/data/runs/2026-04-24/run_20260423_221031
```
### `data/team_registry/`

- `data/team_registry/alias_review_pending.csv`: 150 B, runtime alias queue; header + first 2 rows only.
```csv
league;betano_name;betano_team_id;betano_url;suggested_footystats_name;top_score;review_reason;ambiguous_options;status;source;created_at;updated_at
```
- `data/team_registry/alias_review_rejected.csv`: 593 B, runtime alias queue; header + first 2 rows only.
```csv
league;betano_name;betano_team_id;betano_url;suggested_footystats_name;top_score;review_reason;ambiguous_options;status;source;created_at;updated_at
Bundesliga;odds atualizadas da Bundesliga e aposte;216;https://www.betano.bet.br/sport/futebol/alemanha/bundesliga/216/;FC St. Pauli;0.2727;below_threshold|low_score_gap;FC St. Pauli:0.2727 | Rasen Ballsport Leipzig:0.2712 | VfB Stuttgart 1893:0.2400 | 1. FSV Mainz 05:0.2400 | Borussia VfL Mönchengladbach:0.2333;rejected;https://www.betano.bet.br/sport/futebol/alemanha/bundesliga/216/?bt=standings;2026-04-25 07:45:40;2026-04-25 07:47:12
```
- `data/team_registry/betano_teams_snapshot.json`: 17.3 KB, runtime team snapshot/cache; top-level keys only: league, source, betano_teams, footystats_teams, approved_count, review_count, approved_aliases, review_aliases, parse_diagnostics, coverage, status, coverage_status.
### `data/_archive/`

- `data/_archive/pre_cycle7_cleanup/data/results/_debug/mls.html`: 796.0 KB, archived HTML debug artifact; title/tag summary only.
```text
title: MLS 2026 Results - Football/USA
tag counts in first 64KB: html=1, head=1, body=1, script=34, table=0, div=29, a=4
```
### `dev_asset/`

- No current files found under `dev_asset/`; the directory remains excluded by policy because it is reserved for local debug assets.
### `legacy/history_snapshots/`

- `legacy/history_snapshots/bets_ledger_rerun.csv`: 3.3 KB, tracked legacy ledger snapshot; header + first 2 rows only.
```csv
bet_id;run_id;created_at;settled_at;league;match_datetime;home_team;away_team;match_name;market_raw;event_url;market_type;market_scope;target_team_role;target_team_name;side;line;selection_raw;odd_entrada;odd_justa;prob_model;ev_percent;confidence_score;stake_units;entry_reason;risk_flags;bet_executed;executed_at;odd_executada;stake_units_executada;execution_note;auto_home_goals;auto_away_goals;auto_bet_status;auto_settlement_status;auto_odd_fechamento;manual_home_goals;manual_away_goals;manual_bet_status;manual_settlement_status;manual_odd_fechamento;final_home_goals;final_away_goals;final_bet_status;final_settlement_status;final_odd_fechamento;settlement_source;settlement_confidence;settlement_note;override_reason;override_updated_at;result_units_model;result_units_real
8ea1923429cf;run_20260423_004727_rerun;2026-04-23 00:57:57;;La Liga;2026-04-23 15:00;Rayo Vallecano;Espanyol;Rayo Vallecano - Espanyol;Total de Gols Mais/Menos;https://www.betano.bet.br/odds/rayo-vallecano-espanyol/82821106/;total_goals;full_time;geral;geral;over;2.5;Mais de 2.5;2.15;1.75;0.571186;22.8;5;1.0;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|LIGA_ESTAVEL;SEM_FLAG;no;;;;;;;open;pending;;;;;;;;;open;pending;;;;;;;;
2cd370f7ea93;run_20260423_004727_rerun;2026-04-23 00:57:57;;La Liga;2026-04-23 14:00;Levante;Sevilha FC;Levante - Sevilha FC;Total de Gols Mais/Menos;https://www.betano.bet.br/odds/levante-sevilha-fc/80074591/;total_goals;full_time;geral;geral;over;2.5;Mais de 2.5;2.15;1.82;0.54823;17.87;5;1.0;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|LIGA_ESTAVEL;SEM_FLAG;no;;;;;;;open;pending;;;;;;;;;open;pending;;;;;;;;
```
- `legacy/history_snapshots/bets_ledger_rerun2.csv`: 3.3 KB, tracked legacy ledger snapshot; header + first 2 rows only.
```csv
bet_id;run_id;created_at;settled_at;league;match_datetime;home_team;away_team;match_name;market_raw;event_url;market_type;market_scope;target_team_role;target_team_name;side;line;selection_raw;odd_entrada;odd_justa;prob_model;ev_percent;confidence_score;stake_units;entry_reason;risk_flags;bet_executed;executed_at;odd_executada;stake_units_executada;execution_note;auto_home_goals;auto_away_goals;auto_bet_status;auto_settlement_status;auto_odd_fechamento;manual_home_goals;manual_away_goals;manual_bet_status;manual_settlement_status;manual_odd_fechamento;final_home_goals;final_away_goals;final_bet_status;final_settlement_status;final_odd_fechamento;settlement_source;settlement_confidence;settlement_note;override_reason;override_updated_at;result_units_model;result_units_real
c50f54214362;run_20260423_004727_rerun2;2026-04-23 01:01:17;;La Liga;2026-04-23 15:00;Rayo Vallecano;Espanyol;Rayo Vallecano - Espanyol;Total de Gols Mais/Menos;https://www.betano.bet.br/odds/rayo-vallecano-espanyol/82821106/;total_goals;full_time;geral;geral;over;2.5;Mais de 2.5;2.15;1.75;0.571186;22.8;5;1.0;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|LIGA_ESTAVEL;SEM_FLAG;no;;;;;;;open;pending;;;;;;;;;open;pending;;;;;;;;
a30006c1acd0;run_20260423_004727_rerun2;2026-04-23 01:01:17;;La Liga;2026-04-23 14:00;Levante;Sevilha FC;Levante - Sevilha FC;Total de Gols Mais/Menos;https://www.betano.bet.br/odds/levante-sevilha-fc/80074591/;total_goals;full_time;geral;geral;over;2.5;Mais de 2.5;2.15;1.82;0.54823;17.87;5;1.0;EDGE_FORTE|MERCADO_PRINCIPAL|DADO_COMPLETO|LIGA_ESTAVEL;SEM_FLAG;no;;;;;;;open;pending;;;;;;;;;open;pending;;;;;;;;
```
### Python caches

- `scripts/__pycache__/__init__.cpython-310.pyc`: 147 B, Python bytecode cache; metadata only.
- `scripts/__pycache__/audit_data_artifacts.cpython-310.pyc`: 6.9 KB, Python bytecode cache; metadata only.
- `scripts/__pycache__/data_catalog_utils.cpython-310.pyc`: 5.1 KB, Python bytecode cache; metadata only.
- `scripts/__pycache__/sync_team_aliases.cpython-310.pyc`: 23.7 KB, Python bytecode cache; metadata only.
- `tests/__pycache__/test_closing_watcher.cpython-310.pyc`: 2.0 KB, Python bytecode cache; metadata only.

## Exception Policy

- Ledger audit: include only a tiny sampled ledger or the exact file requested by the user; never upload the full operational ledger by default.
- Replay bug: include one specific replay directory manifest and the minimum failing artifact needed to reproduce the issue.
- Results/settlement bug: include relevant result CSV headers and a few rows, plus the exact settlement code under review.
- Alias bug: include `data/team_registry/alias_review_pending.csv` only if it contains pending rows, and include only the smallest useful excerpt.
- Service job bug: include one job JSON and the corresponding first log excerpt; avoid uploading entire service log directories.

## Current `.codexignore` Alignment

`.codexignore` contains all required default exclusion rules listed above.

Additional alignment now present:
- `.codexignore` also excludes the tracked `.codex` file itself.
- `.codexignore` also excludes `legacy/history_snapshots/**` because those files are data-like historical snapshots.

This document was updated to reflect the `.codexignore` alignment patch.
