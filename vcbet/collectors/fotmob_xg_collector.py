import argparse
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List

import pandas as pd

from vcbet.collectors.fotmob_client import FotMobClient, FotMobFetchResult
from vcbet.core.config_ligas import carregar_ligas_fotmob
from vcbet.core.run_utils import build_manifest, ensure_run_dir, generate_run_id, save_manifest, update_manifest
from vcbet.core.temporal_contract import TEMPORAL_CONTRACT_VERSION, file_md5, snapshot_time_from_dataframe


def parse_leagues_arg(raw_value: str | None) -> List[str] | None:
    if not raw_value:
        return None
    leagues = [item.strip() for item in raw_value.split(",") if item.strip()]
    return leagues or None


def _extract_goals_per_match(home_row: dict | None, away_row: dict | None, played: int) -> dict[str, float | None]:
    if played <= 0:
        return {
            "goals_home_per_match": None,
            "goals_away_per_match": None,
            "goals_for_per_match": None,
            "goals_against_per_match": None,
        }
    goals_for = 0.0
    goals_against = 0.0
    if home_row:
        scores = home_row.get("scoresStr", "")
        if isinstance(scores, str) and "-" in scores:
            parts = scores.split("-")
            if len(parts) == 2:
                try:
                    goals_for += float(parts[0].strip())
                    goals_against += float(parts[1].strip())
                except ValueError:
                    pass
    if away_row:
        scores = away_row.get("scoresStr", "")
        if isinstance(scores, str) and "-" in scores:
            parts = scores.split("-")
            if len(parts) == 2:
                try:
                    goals_for += float(parts[0].strip())
                    goals_against += float(parts[1].strip())
                except ValueError:
                    pass
    return {
        "goals_home_per_match": (goals_for / played) if home_row else None,
        "goals_away_per_match": (goals_for / played) if away_row else None,
        "goals_for_per_match": goals_for / played,
        "goals_against_per_match": goals_against / played,
    }


def _find_team_row(table_data: list[dict], team_id: int) -> dict | None:
    for row in table_data:
        if row.get("teamId") == team_id or row.get("id") == team_id:
            return row
    return None


def extract_mls_supporters_shield_xg_table(payload: dict) -> dict:
    """Extract the Supporters Shield subtable from MLS composite response.

    MLS (leagueId 130) returns multiple subtables under table[0].data.tables.
    The aggregated table containing all teams is the one whose leagueName
    equals 'Supporters Shield'. This function returns the inner table dict
    (which contains xg, home, away, all) so the normal parser can consume it.
    """
    tables = payload.get("table", [])
    if not tables:
        raise ValueError("fotmob_missing_table: no 'table' key in response")

    table_root = tables[0]
    if not isinstance(table_root, dict):
        raise ValueError("fotmob_invalid_table: table[0] is not a dict")

    data = table_root.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("fotmob_invalid_table: table[0].data is not a dict")

    subtables = data.get("tables", [])
    if not isinstance(subtables, list):
        raise ValueError("fotmob_invalid_table: table[0].data.tables is not a list")

    for sub in subtables:
        if not isinstance(sub, dict):
            continue
        if sub.get("leagueName") == "Supporters Shield":
            inner_table = sub.get("table", {})
            if not isinstance(inner_table, dict):
                raise ValueError("fotmob_invalid_table: Supporters Shield subtable.table is not a dict")
            if not inner_table.get("xg"):
                raise ValueError("fotmob_missing_xg_table: Supporters Shield subtable has no xG data")
            return inner_table

    raise ValueError("fotmob_missing_mls_supporters_shield: no 'Supporters Shield' subtable found")


def parse_fotmob_league_xg(
    league_name: str,
    league_id: int,
    ccode3: str,
    json_data: dict,
    run_id: str,
    collected_at: str,
) -> pd.DataFrame:
    details = json_data.get("details") or {}
    data_provider = details.get("dataProvider") or json_data.get("dataProvider") or "fotmob"

    tables = json_data.get("table", [])
    if not tables:
        raise ValueError("fotmob_missing_table: no 'table' key in response")

    is_mls = (league_id == 130) or (str(league_name).strip().upper() == "MLS")
    if is_mls:
        try:
            table_data = extract_mls_supporters_shield_xg_table(json_data)
        except ValueError:
            raise
    else:
        table_root = tables[0]
        if isinstance(table_root, dict):
            table_data = table_root.get("data", {}).get("table", {})
        else:
            table_data = {}

    xg_table = table_data.get("xg", []) if isinstance(table_data, dict) else []
    home_table = table_data.get("home", []) if isinstance(table_data, dict) else []
    away_table = table_data.get("away", []) if isinstance(table_data, dict) else []

    if not xg_table:
        raise ValueError("fotmob_missing_xg_table: no xG sub-table found")

    rows: list[dict[str, Any]] = []
    skipped_reasons: dict[str, int] = {}

    for xg_row in xg_table:
        team_id = xg_row.get("teamId") or xg_row.get("id")
        team_name = xg_row.get("teamName") or xg_row.get("name")
        played = xg_row.get("played")
        raw_xg = xg_row.get("xg")
        raw_xga = xg_row.get("xgConceded")
        xpoints = xg_row.get("xPoints")

        if not team_name:
            skipped_reasons["missing_team_name"] = skipped_reasons.get("missing_team_name", 0) + 1
            continue
        if played is None or played <= 0:
            skipped_reasons["zero_or_missing_played"] = skipped_reasons.get("zero_or_missing_played", 0) + 1
            continue
        if raw_xg is None:
            skipped_reasons["missing_xg"] = skipped_reasons.get("missing_xg", 0) + 1
            continue
        if raw_xga is None:
            skipped_reasons["missing_xg_conceded"] = skipped_reasons.get("missing_xg_conceded", 0) + 1
            continue

        try:
            raw_xg_val = float(raw_xg)
            raw_xga_val = float(raw_xga)
            played_val = int(played)
        except (ValueError, TypeError):
            skipped_reasons["unparseable_numeric"] = skipped_reasons.get("unparseable_numeric", 0) + 1
            continue

        xg_per_match = raw_xg_val / played_val
        xga_per_match = raw_xga_val / played_val

        home_row = _find_team_row(home_table, team_id) if isinstance(team_id, int) else None
        away_row = _find_team_row(away_table, team_id) if isinstance(team_id, int) else None
        goals_ctx = _extract_goals_per_match(home_row, away_row, played_val)

        rows.append(
            {
                "run_id": run_id,
                "collected_at": collected_at,
                "source": "fotmob",
                "league": league_name,
                "team_name": str(team_name).strip(),
                "xg": round(xg_per_match, 4),
                "xga": round(xga_per_match, 4),
                "xg_home": round(xg_per_match, 4),
                "xg_away": round(xg_per_match, 4),
                "xga_home": round(xga_per_match, 4),
                "xga_away": round(xga_per_match, 4),
                "xg_split_method": "fotmob_global_duplicated",
                "source_team_id": team_id,
                "source_data_provider": data_provider,
                "fotmob_league_id": league_id,
                "fotmob_ccode3": ccode3,
                "xg_raw_total": raw_xg_val,
                "xga_raw_total": raw_xga_val,
                "xpoints": xpoints,
                **goals_ctx,
            }
        )

    if skipped_reasons:
        for reason, count in sorted(skipped_reasons.items()):
            print(f"      [ALERTA] FotMob skip reason: {reason}={count}")

    if not rows:
        raise ValueError("fotmob_no_valid_teams: all teams skipped due to missing/invalid data")

    df = pd.DataFrame(rows)
    ordered_columns = [
        "run_id",
        "collected_at",
        "source",
        "league",
        "team_name",
        "xg",
        "xga",
        "xg_home",
        "xg_away",
        "xga_home",
        "xga_away",
    ]
    extra = [c for c in df.columns if c not in ordered_columns]
    return df[ordered_columns + extra]


def construir_banco_dados(
    run_id: str,
    target_date: str,
    output_dir: str,
    ligas_alvo: Iterable[str] | None = None,
    modo_debug: bool = False,
):
    print(f"================ [ ATUALIZANDO BANCO DE DADOS DE xG (FOTMOB) | RUN_ID: {run_id} ] ================")
    run_dir = ensure_run_dir(run_id=run_id, target_date=target_date, base_output_dir=output_dir)

    manifest = build_manifest(
        run_id=run_id,
        target_date=target_date,
        run_dir=run_dir,
        odds_snapshot_file=str(run_dir / "odds_snapshot.csv"),
        xg_snapshot_file=str(run_dir / "xg_snapshot.csv"),
        status="xg_initialized",
    )
    save_manifest(run_dir, manifest)

    mapa_fotmob = carregar_ligas_fotmob(ligas_nomes=ligas_alvo)
    if ligas_alvo:
        print(f" -> Filtro de ligas ativo: {', '.join(mapa_fotmob.keys()) if mapa_fotmob else '(nenhuma liga válida)'}")

    if not mapa_fotmob:
        update_manifest(
            run_dir,
            status="xg_empty",
            xg_rows=0,
            xg_target_leagues=list(ligas_alvo or []),
            xg_source_mode="fotmob",
        )
        print("\n[FALHA] Nenhuma liga válida com fotmob_league_id foi selecionada para a coleta de xG.")
        return

    client = FotMobClient()
    warmup = client.warmup()
    if not warmup.ok:
        print(f"[ALERTA] FotMob warmup falhou: {warmup.error}")

    lista_dfs = []
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    league_failures: list[dict] = []
    data_provider: str | None = None

    for liga, config in mapa_fotmob.items():
        print(f" -> Baixando: {liga} (id={config['fotmob_league_id']}, ccode3={config['fotmob_ccode3']})...")
        try:
            result: FotMobFetchResult = client.fetch_league_data(
                league_id=config["fotmob_league_id"],
                ccode3=config["fotmob_ccode3"],
            )
            if not result.ok:
                print(f"    [ERRO] Fetch falhou para {liga}: {result.error} (status={result.status_code})")
                league_failures.append({"league": liga, "error": result.error, "status_code": result.status_code})
                continue

            if result.json_data is None:
                print(f"    [ERRO] JSON vazio para {liga}")
                league_failures.append({"league": liga, "error": "empty_json", "status_code": result.status_code})
                continue

            # Try to extract data provider from first successful league
            if data_provider is None:
                details = result.json_data.get("details") or {}
                data_provider = details.get("dataProvider") or result.json_data.get("dataProvider")

            df = parse_fotmob_league_xg(
                league_name=liga,
                league_id=config["fotmob_league_id"],
                ccode3=config["fotmob_ccode3"],
                json_data=result.json_data,
                run_id=run_id,
                collected_at=collected_at,
            )
            if not df.empty:
                lista_dfs.append(df)
                print(f"    [OK] {len(df)} equipas extraídas.")
            else:
                print(f"    [ERRO] DataFrame vazio retornado para {liga}.")
        except Exception:
            print(f"    [ERRO FATAL] Falha processando {liga}:")
            traceback.print_exc()
            league_failures.append({"league": liga, "error": "exception", "status_code": None})

    if lista_dfs:
        df_final = pd.concat(lista_dfs, ignore_index=True)
        xg_snapshot_path = run_dir / "xg_snapshot.csv"

        if not modo_debug:
            df_final.to_csv(xg_snapshot_path, index=False, sep=";", encoding="utf-8-sig")
            print(f"\n[SUCESSO] Snapshot gerado com {len(df_final)} equipas: '{xg_snapshot_path}'")
        else:
            print(f"\n[!] MODO DEBUG: Extração concluída ({len(df_final)} equipas). Arquivo CSV NÃO foi gerado.")
            print("\n--- AMOSTRA DOS DADOS EXTRAÍDOS ---")
            print(df_final.head(15).to_string(index=False))

        update_manifest(
            run_dir,
            status="xg_completed",
            xg_rows=len(df_final),
            xg_snapshot_file=str(xg_snapshot_path),
            xg_snapshot_hash=file_md5(xg_snapshot_path) if xg_snapshot_path.exists() else None,
            xg_asof=snapshot_time_from_dataframe(df_final),
            temporal_contract_version=TEMPORAL_CONTRACT_VERSION,
            xg_target_leagues=list(mapa_fotmob.keys()),
            xg_source_mode="fotmob",
            xg_source_data_provider=data_provider,
            xg_league_failures=league_failures if league_failures else None,
        )
    else:
        update_manifest(
            run_dir,
            status="xg_empty",
            xg_rows=0,
            xg_target_leagues=list(mapa_fotmob.keys()),
            xg_source_mode="fotmob",
            xg_source_data_provider=data_provider,
            xg_league_failures=league_failures if league_failures else None,
        )
        print("\n[FALHA] Nenhum dado foi extraído.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coletor de snapshot xG via FotMob")
    parser.add_argument("--debug", action="store_true", help="Executa normalmente, mas não salva arquivos no final")
    parser.add_argument("--run-id", type=str, help="Identificador único da execução")
    parser.add_argument("--output-dir", type=str, default="data/runs", help="Diretório base para salvar as runs")
    parser.add_argument("--data", type=str, help="Data da run no formato YYYY-MM-DD")
    parser.add_argument("--leagues", type=str, help="Lista de ligas separadas por vírgula para limitar a coleta de xG")
    args = parser.parse_args()

    target_date = args.data or datetime.today().strftime("%Y-%m-%d")
    run_id = args.run_id or generate_run_id()
    ligas_alvo = parse_leagues_arg(args.leagues)
    construir_banco_dados(
        run_id=run_id,
        target_date=target_date,
        output_dir=args.output_dir,
        ligas_alvo=ligas_alvo,
        modo_debug=args.debug,
    )
