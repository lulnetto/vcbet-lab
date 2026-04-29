import argparse
import shutil
from pathlib import Path
from typing import Iterable

import pandas as pd

from vcbet.collectors.fotmob_client import FotMobClient
from vcbet.collectors.fotmob_xg_collector import parse_fotmob_league_xg
from vcbet.collectors.footystats_xg_collector import (
    _fetch_html_requests,
    extrair_dados_completos,
)
from vcbet.core.config_ligas import carregar_ligas_fotmob, carregar_ligas_footystats
from vcbet.core.run_utils import ensure_run_dir


def _try_fotmob_league(
    league_name: str,
    league_id: int,
    ccode3: str,
    client: FotMobClient,
    run_id: str,
    collected_at: str,
) -> tuple[pd.DataFrame | None, str | None]:
    result = client.fetch_league_data(league_id=league_id, ccode3=ccode3)
    if not result.ok:
        return None, result.error or f"HTTP {result.status_code}"
    if result.json_data is None:
        return None, "empty_json"
    try:
        df = parse_fotmob_league_xg(
            league_name=league_name,
            league_id=league_id,
            ccode3=ccode3,
            json_data=result.json_data,
            run_id=run_id,
            collected_at=collected_at,
        )
        return (df if not df.empty else None), None
    except Exception as exc:
        return None, str(exc)


def _try_footystats_league(
    league_name: str,
    url_base: str,
    run_id: str,
    collected_at: str,
) -> tuple[pd.DataFrame | None, str | None]:
    try:
        html = _fetch_html_requests(f"{url_base}/xg")
        df = extrair_dados_completos(html)
        if df is None or df.empty:
            return None, "empty_dataframe"
        df = df.copy()
        df["run_id"] = run_id
        df["collected_at"] = collected_at
        df["source"] = "footystats"
        df["league"] = league_name
        df["xg_split_method"] = "footystats_global"
        return df, None
    except Exception as exc:
        return None, str(exc)


def construir_banco_dados_unificado(
    run_id: str,
    target_date: str,
    output_dir: str,
    ligas_alvo: Iterable[str] | None = None,
    snapshot_date: str | None = None,
):
    print(f"================ [ ATUALIZANDO BANCO DE DADOS DE xG (UNIFICADO) | RUN_ID: {run_id} ] ================")
    snapshot_date = snapshot_date or target_date
    run_dir = ensure_run_dir(run_id=run_id, target_date=snapshot_date, base_output_dir=output_dir)

    mapa_fotmob = carregar_ligas_fotmob(ligas_nomes=ligas_alvo)
    mapa_footystats = carregar_ligas_footystats(ligas_nomes=ligas_alvo)

    if ligas_alvo:
        alvos = set(ligas_alvo)
        print(f" -> Filtro de ligas ativo: {', '.join(sorted(alvos))}")
    else:
        alvos = set(mapa_fotmob.keys()) | set(mapa_footystats.keys())

    if not alvos:
        print("\n[FALHA] Nenhuma liga válida foi selecionada para a coleta de xG.")
        return

    client = FotMobClient()
    warmup = client.warmup()
    if not warmup.ok:
        print(f"[ALERTA] FotMob warmup falhou: {warmup.error}")

    collected_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    lista_dfs: list[pd.DataFrame] = []

    fotmob_ok: list[str] = []
    footystats_fallback: list[str] = []
    skipped: list[str] = []
    skip_reasons: dict[str, str] = {}

    for league in sorted(alvos):
        fotmob_config = mapa_fotmob.get(league)
        footystats_url = mapa_footystats.get(league)

        # Try FotMob first
        df_league: pd.DataFrame | None = None
        fotmob_error: str | None = None
        if fotmob_config:
            print(f" -> Baixando: {league} (FotMob id={fotmob_config['fotmob_league_id']})...")
            df_league, fotmob_error = _try_fotmob_league(
                league_name=league,
                league_id=fotmob_config["fotmob_league_id"],
                ccode3=fotmob_config["fotmob_ccode3"],
                client=client,
                run_id=run_id,
                collected_at=collected_at,
            )
            if df_league is not None:
                lista_dfs.append(df_league)
                fotmob_ok.append(league)
                print(f"    [OK] {len(df_league)} equipas extraídas via FotMob.")
                continue
            else:
                print(f"    [ALERTA] FotMob falhou para {league}: {fotmob_error}")
        else:
            print(f" -> Baixando: {league} (sem config FotMob, tentando FootyStats)...")

        # Fallback to FootyStats
        if footystats_url:
            df_league, fs_error = _try_footystats_league(
                league_name=league,
                url_base=footystats_url,
                run_id=run_id,
                collected_at=collected_at,
            )
            if df_league is not None:
                lista_dfs.append(df_league)
                footystats_fallback.append(league)
                print(f"    [OK] {len(df_league)} equipas extraídas via FootyStats (fallback).")
                continue
            else:
                print(f"    [ALERTA] FootyStats fallback falhou para {league}: {fs_error}")
                skip_reasons[league] = f"fotmob:{fotmob_error or 'n/a'} | footystats:{fs_error}"
        else:
            skip_reasons[league] = f"fotmob:{fotmob_error or 'n/a'} | footystats:no_url"

        skipped.append(league)
        print(f"    [SKIP] Liga {league} pulada — sem xG de nenhuma fonte.")

    if lista_dfs:
        df_final = pd.concat(lista_dfs, ignore_index=True)
        snapshot_path = run_dir / "xg_snapshot.csv"
        df_final.to_csv(snapshot_path, index=False, sep=";", encoding="utf-8-sig")
        print(f"\n[SUCESSO] Snapshot gerado com {len(df_final)} equipas: '{snapshot_path}'")
        print(
            f" -> Resumo: fotmob_ok={len(fotmob_ok)}, "
            f"footystats_fallback={len(footystats_fallback)}, "
            f"skipped={len(skipped)}"
        )
        if skipped:
            print(f" -> Ligas puladas: {', '.join(skipped)}")
    else:
        print("\n[FALHA] Nenhum dado foi extraído de nenhuma liga.")


def get_or_build_daily_xg(
    target_date: str,
    source: str,
    leagues: str | None = None,
    output_dir: str = "data/xg",
    snapshot_date: str | None = None,
):
    snapshot_date = snapshot_date or pd.Timestamp.now().strftime("%Y-%m-%d")
    daily_dir = Path(output_dir) / snapshot_date
    daily_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = daily_dir / "xg_snapshot.csv"

    if snapshot_path.exists():
        print(f"[xG CACHE] Reutilizando snapshot diário: {snapshot_path}")
        return str(snapshot_path)

    run_id = "daily"
    ligas_alvo = [l.strip() for l in leagues.split(",") if l.strip()] if leagues else None

    # Unified collector with per-league fallback (ignores legacy 'source' arg)
    construir_banco_dados_unificado(
        run_id=run_id,
        target_date=target_date,
        output_dir=output_dir,
        ligas_alvo=ligas_alvo,
        snapshot_date=snapshot_date,
    )

    src = ensure_run_dir(run_id=run_id, target_date=snapshot_date, base_output_dir=output_dir) / "xg_snapshot.csv"
    if not src.exists():
        raise FileNotFoundError(f"xG snapshot não gerado em {src}")

    shutil.copy(str(src), str(snapshot_path))
    print(f"[xG CACHE] Snapshot diário criado: {snapshot_path}")
    return str(snapshot_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cache/snapshot diário de xG")
    parser.add_argument("--date", required=True, help="Data alvo YYYY-MM-DD")
    parser.add_argument("--source", default="fotmob", choices=["fotmob", "footystats"])
    parser.add_argument("--leagues", default="Premier League,Championship,La Liga,Segunda División,Ligue 1,Bundesliga,2. Bundesliga,Serie A,Serie B,Liga NOS,MLS,Brasileirão Série A,Liga dos Campeões,Liga Europa,Liga Conferência", help="Ligas separadas por vírgula")
    parser.add_argument("--output-dir", default="data/xg")
    parser.add_argument("--snapshot-date", default=None, help="Data do snapshot YYYY-MM-DD (padrão: hoje)")
    args = parser.parse_args()
    get_or_build_daily_xg(
        target_date=args.date,
        source=args.source,
        leagues=args.leagues or None,
        output_dir=args.output_dir,
        snapshot_date=args.snapshot_date,
    )
