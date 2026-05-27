from __future__ import annotations

from collections import Counter

import pandas as pd

from vcbet.core.config_ligas import obter_nomes_ligas_ativas
from vcbet.core.market_exceptions import (
    EV_EXCEPTION_BTTS_YES_EXPERIMENTAL,
    apply_market_exception_fields,
    btts_yes_ev_exception_meta,
)
from vcbet.core.line_selector import select_top_picks
from vcbet.core.sport_sense_policy import apply_sport_sense_policy
from vcbet.core.temporal_contract import TEMPORAL_CONTRACT_VERSION


def build_normalization_filter(df_betano: pd.DataFrame, df_xg: pd.DataFrame, supported_markets: set[str]) -> dict[str, object]:
    ligas_do_dia = df_betano["league"].dropna().unique()
    print(f" -> Ligas ativas hoje: {', '.join(ligas_do_dia)}")

    ligas_config = obter_nomes_ligas_ativas()
    ligas_fora_config = sorted(set(ligas_do_dia) - ligas_config)
    if ligas_fora_config:
        print(f"[ALERTA] Ligas presentes no CSV mas ausentes do ligas.json: {', '.join(ligas_fora_config)}")

    print(f" -> Base xG carregada com sucesso ({len(df_xg)} equipas disponíveis).")

    if "normalized_status" not in df_betano.columns:
        raise ValueError("Snapshot de odds sem coluna normalized_status após carregamento.")

    normalized_status_counts = Counter(df_betano["normalized_status"].fillna("missing"))
    market_scope_counts = Counter(df_betano.get("market_scope", pd.Series(dtype=object)).fillna("missing"))
    normalized_market_type_counts = Counter(df_betano.loc[df_betano["normalized_status"] == "ok", "market_type"].fillna("missing"))

    base_filter_discard_counts = Counter()
    for _, row in df_betano.iterrows():
        if row.get("normalized_status") != "ok":
            base_filter_discard_counts["normalized_status_not_ok"] += 1
            continue
        if row.get("market_scope") != "full_time":
            base_filter_discard_counts["market_scope_not_full_time"] += 1
            continue
        if row.get("market_type") not in supported_markets:
            base_filter_discard_counts["unsupported_market_type"] += 1
            continue

    df_alvo = df_betano[
        (df_betano["normalized_status"] == "ok")
        & (df_betano["market_scope"] == "full_time")
        & (df_betano["market_type"].isin(supported_markets))
    ].copy()

    # Skip leagues that exist in odds but have no xG coverage before pricing
    ligas_odds = set(df_betano["league"].dropna().unique())
    ligas_xg = set(df_xg["league"].dropna().unique())
    ligas_sem_xg = sorted(ligas_odds - ligas_xg)
    league_skipped_missing_xg_snapshot: dict[str, int] = {}
    for league in ligas_sem_xg:
        count = int((df_betano["league"] == league).sum())
        if count > 0:
            league_skipped_missing_xg_snapshot[league] = count
    if ligas_sem_xg:
        print(f"[ALERTA] Ligas com odds mas sem xG — excluídas antes do pricing: {', '.join(ligas_sem_xg)}")
        df_alvo = df_alvo[~df_alvo["league"].isin(ligas_sem_xg)].copy()

    print("[3] Normalização/Filtro base: " f"{len(df_alvo)} linhas elegíveis de {len(df_betano)} totais")

    return {
        "df_alvo": df_alvo,
        "normalized_status_counts": normalized_status_counts,
        "market_scope_counts": market_scope_counts,
        "normalized_market_type_counts": normalized_market_type_counts,
        "base_filter_discard_counts": base_filter_discard_counts,
        "league_skipped_missing_xg_snapshot": league_skipped_missing_xg_snapshot,
    }


def apply_profile_policies(df_candidates: pd.DataFrame, runtime_config) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df_candidates.empty:
        return df_candidates.copy(), pd.DataFrame()

    approved_rows: list[dict] = []
    blocked_rows: list[dict] = []
    for row in df_candidates.to_dict("records"):
        evaluated = apply_sport_sense_policy(row, runtime_config)
        if evaluated.get("sport_sense_status") == "blocked":
            exception_meta = None
            if str(evaluated.get("sport_sense_reason") or "").upper() == "EV_BELOW_MARKET_MIN":
                exception_meta = btts_yes_ev_exception_meta(evaluated, runtime_config)
            if exception_meta is not None:
                evaluated = apply_market_exception_fields(evaluated, exception_meta)
                evaluated["sport_sense_status"] = "approved"
                evaluated["sport_sense_reason"] = EV_EXCEPTION_BTTS_YES_EXPERIMENTAL
                approved_rows.append(evaluated)
                continue
            blocked = dict(evaluated)
            reason = str(blocked.get("sport_sense_reason") or "SPORT_SENSE_BLOCKED")
            blocked["candidate_stage"] = "profile_policy_blocked_candidate"
            blocked["pick_safety_status"] = "blocked"
            blocked["decision_policy_status"] = "blocked_by_profile_policy"
            blocked["decision_reject_reason"] = reason
            blocked["selection_policy_status"] = "blocked_by_profile_policy"
            blocked["selection_reject_reason"] = reason
            blocked["safety_reject_reason"] = reason
            blocked_rows.append(blocked)
        else:
            approved_rows.append(evaluated)

    approved_df = pd.DataFrame(approved_rows)
    blocked_df = pd.DataFrame(blocked_rows)
    return approved_df, blocked_df


def select_and_annotate_final_picks(
    *,
    df_candidates: pd.DataFrame,
    df_blocked_candidates: pd.DataFrame,
    generated_at: str,
    runtime_config,
    config_snapshot_file,
    run_id: str,
    run_group_id: str | None = None,
    ledger_path: str | None = None,
    source_snapshot_id: str | None = None,
    odds_path,
    xg_path,
    odds_snapshot_hash: str,
    xg_snapshot_hash: str,
    odds_snapshot_time: str | None,
    xg_asof: str | None,
    temporal_status: str,
    signal_version: str,
    pipeline_version: str,
) -> dict[str, object]:
    df_policy_candidates, df_profile_policy_blocked = apply_profile_policies(df_candidates, runtime_config)
    if not df_policy_candidates.empty:
        df_final, df_portfolio_rejected = select_top_picks(df_policy_candidates, return_meta=True)
    else:
        df_final = pd.DataFrame()
        df_portfolio_rejected = pd.DataFrame()
    if not df_final.empty:
        df_final = df_final.copy()
        df_final["candidate_stage"] = "official_accepted_pick"
        df_final["pick_safety_status"] = "safe"
        df_final["decision_timestamp"] = generated_at
        df_final["config_name"] = runtime_config.name
        df_final["config_fingerprint"] = runtime_config.fingerprint
        df_final["config_source_path"] = runtime_config.source_path or ""
        df_final["config_snapshot_file"] = str(config_snapshot_file)
        df_final["run_group_id"] = run_group_id or ""
        df_final["ledger_path"] = ledger_path or ""
        df_final["source_run_id"] = run_id
        df_final["source_snapshot_id"] = source_snapshot_id or ""
        df_final["source_snapshot_ref"] = f"odds:{odds_path}|xg:{xg_path}"
        df_final["odds_snapshot_file"] = str(odds_path)
        df_final["xg_snapshot_file"] = str(xg_path)
        df_final["odds_snapshot_hash"] = odds_snapshot_hash
        df_final["xg_snapshot_hash"] = xg_snapshot_hash
        df_final["odds_snapshot_time"] = odds_snapshot_time or ""
        df_final["xg_asof"] = xg_asof or ""
        df_final["temporal_contract_version"] = TEMPORAL_CONTRACT_VERSION
        df_final["temporal_contract_status"] = temporal_status
        df_final["signal_version"] = signal_version
        df_final["pipeline_version"] = pipeline_version

    safety_gate_blocked_total = int((df_blocked_candidates.get("pick_safety_status", pd.Series(dtype=object)) == "blocked").sum()) if not df_blocked_candidates.empty else 0
    official_unsafe_total = int((df_final.get("pick_safety_status", pd.Series(dtype=object)) != "safe").sum()) if not df_final.empty else 0
    if official_unsafe_total:
        run_safety_status = "unsafe_official_picks"
    elif safety_gate_blocked_total:
        run_safety_status = "safe_with_blocked_candidates"
    else:
        run_safety_status = "safe"

    return {
        "df_final": df_final,
        "df_portfolio_rejected": df_portfolio_rejected,
        "df_profile_policy_blocked": df_profile_policy_blocked,
        "safety_gate_blocked_total": safety_gate_blocked_total,
        "official_unsafe_total": official_unsafe_total,
        "run_safety_status": run_safety_status,
    }
