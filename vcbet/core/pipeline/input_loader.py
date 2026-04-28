from __future__ import annotations

from pathlib import Path

import pandas as pd

from vcbet.core.data_health import validate_snapshot_health
from vcbet.core.market_normalizer import normalize_odds_dataframe
from vcbet.core.run_utils import ensure_run_dir
from vcbet.core.strategy_config import save_runtime_snapshot
from vcbet.core.temporal_contract import file_md5, snapshot_time_from_dataframe


def carregar_snapshot_odds(odds_file: str | Path) -> pd.DataFrame:
    df_betano = pd.read_csv(odds_file, sep=";")

    rename_map = {
        "Liga": "league",
        "Data": "match_datetime",
        "Jogo": "match_name",
        "Mercado": "market_raw",
        "Selecao": "selection_raw",
        "Odd": "odd",
        "run_id": "run_id",
        "home_team": "home_team",
        "away_team": "away_team",
        "market_type": "market_type",
        "market_scope": "market_scope",
        "side": "side",
        "line": "line",
        "target_team_role": "target_team_role",
        "target_team_name": "target_team_name",
        "normalized_status": "normalized_status",
        "event_url": "event_url",
    }
    df_betano = df_betano.rename(columns=rename_map)

    if "match_name" in df_betano.columns and "home_team" not in df_betano.columns:
        split_cols = df_betano["match_name"].astype(str).str.split(" - ", n=1, expand=True)
        if not split_cols.empty:
            df_betano["home_team"] = split_cols[0].fillna("").str.strip()
            df_betano["away_team"] = split_cols[1].fillna("").str.strip() if split_cols.shape[1] > 1 else ""

    if {"market_raw", "selection_raw", "home_team", "away_team"}.issubset(df_betano.columns):
        df_betano = normalize_odds_dataframe(df_betano)
    elif "normalized_status" not in df_betano.columns:
        df_betano = normalize_odds_dataframe(df_betano)

    return df_betano


def carregar_snapshot_xg(xg_file: str | Path) -> pd.DataFrame:
    df_xg = pd.read_csv(xg_file, sep=";")
    rename_map = {
        "Time_FS": "team_name",
        "Liga": "league",
        "xG": "xg",
        "xGA": "xga",
        "xG_Casa": "xg_home",
        "xG_Fora": "xg_away",
        "xGA_Casa": "xga_home",
        "xGA_Fora": "xga_away",
    }
    return df_xg.rename(columns=rename_map)


def load_pipeline_inputs(
    *,
    odds_file: str,
    xg_file: str,
    run_id: str | None,
    output_dir: str,
    runtime_config,
) -> dict[str, object]:
    odds_path = Path(odds_file)
    xg_path = Path(xg_file)

    if not odds_path.exists():
        raise FileNotFoundError(f"Arquivo de odds não encontrado: {odds_path}")
    if not xg_path.exists():
        raise FileNotFoundError(f"Arquivo de xG não encontrado: {xg_path}")

    df_betano = carregar_snapshot_odds(odds_path)
    df_xg = carregar_snapshot_xg(xg_path)

    odds_run_id = str(df_betano.get("run_id", pd.Series([""])).iloc[0] or "").strip()
    xg_run_id = str(df_xg.get("run_id", pd.Series([""])).iloc[0] or "").strip()
    resolved_run_id = run_id or odds_run_id or xg_run_id
    if not resolved_run_id:
        raise ValueError("run_id não informado e não encontrado nos snapshots.")

    target_date = odds_path.parent.parent.name if odds_path.parent.parent.name else pd.Timestamp.now().strftime("%Y-%m-%d")
    run_dir = ensure_run_dir(run_id=resolved_run_id, target_date=target_date, base_output_dir=output_dir)
    config_snapshot_file = save_runtime_snapshot(run_dir)

    print(f"[0] Configuração ativa: {runtime_config.label} ({runtime_config.fingerprint})")
    print(f"    source: {runtime_config.source_path or 'default_embutida'}")
    print(f"[1] Arquivo de odds carregado: {odds_path}")
    print(f"[2] Arquivo de xG carregado: {xg_path}")

    return {
        "odds_path": odds_path,
        "xg_path": xg_path,
        "df_betano": df_betano,
        "df_xg": df_xg,
        "odds_run_id": odds_run_id,
        "xg_run_id": xg_run_id,
        "run_id": resolved_run_id,
        "target_date": target_date,
        "run_dir": run_dir,
        "alias_pending_file": run_dir / "alias_review_pending.csv",
        "picks_file": run_dir / "picks_snapshot.csv",
        "config_snapshot_file": config_snapshot_file,
        "odds_snapshot_hash": file_md5(odds_path),
        "xg_snapshot_hash": file_md5(xg_path),
        "odds_snapshot_time": snapshot_time_from_dataframe(df_betano),
        "xg_asof": snapshot_time_from_dataframe(df_xg),
    }
