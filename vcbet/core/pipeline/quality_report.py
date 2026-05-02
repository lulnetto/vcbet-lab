from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pandas as pd

from vcbet.core.run_utils import save_quality_report
from vcbet.core.temporal_contract import TEMPORAL_CONTRACT_VERSION
from vcbet.core.xg_residuals import (
    pricing_variant_from_payload,
    quality_xg_residual_adjustment_payload,
)


PRE_SNAPSHOT_DISCARDS_FILENAME = "odds_discarded_pre_snapshot.csv"
PRE_SNAPSHOT_DISCARD_SAMPLE_FIELDS = [
    "league",
    "match_name",
    "market_raw",
    "selection_raw",
    "odd_raw",
    "betano_market_type_id",
]


def to_sorted_dict(counter_like) -> dict:
    if isinstance(counter_like, Counter):
        items = counter_like.items()
    elif isinstance(counter_like, dict):
        items = counter_like.items()
    else:
        items = counter_like
    return {str(k): int(v) for k, v in sorted(items, key=lambda item: str(item[0]))}


def _resolve_pre_snapshot_discard_path(path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        return candidate / PRE_SNAPSHOT_DISCARDS_FILENAME
    if candidate.name == PRE_SNAPSHOT_DISCARDS_FILENAME:
        return candidate
    return candidate.parent / PRE_SNAPSHOT_DISCARDS_FILENAME


def build_pre_snapshot_discard_summary(path, sample_limit_per_reason: int = 20) -> dict[str, object]:
    discard_path = _resolve_pre_snapshot_discard_path(path)
    if not discard_path.exists():
        return {
            "pre_snapshot_discard_counts": {},
            "pre_snapshot_discard_samples": {},
        }

    counts: Counter = Counter()
    samples: dict[str, list[dict]] = {}
    with open(discard_path, "r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            reason = str(row.get("discard_reason") or "missing")
            counts[reason] += 1
            bucket = samples.setdefault(reason, [])
            if len(bucket) < sample_limit_per_reason:
                bucket.append({field: row.get(field, "") for field in PRE_SNAPSHOT_DISCARD_SAMPLE_FIELDS})

    return {
        "pre_snapshot_discard_counts": to_sorted_dict(counts),
        "pre_snapshot_discard_samples": samples,
    }


def _numeric_candidate_series(df: pd.DataFrame, column: str) -> pd.Series:
    if df.empty or column not in df.columns:
        return pd.Series(0.0, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def build_xg_residual_summary(df_candidates: pd.DataFrame) -> dict[str, object]:
    if df_candidates.empty:
        return {
            "candidates_with_adjustment": 0,
            "avg_abs_lambda_home_adjustment_pct": 0.0,
            "avg_abs_lambda_away_adjustment_pct": 0.0,
            "max_abs_lambda_adjustment_pct": 0.0,
        }
    home_abs = _numeric_candidate_series(df_candidates, "lambda_home_adjustment_pct").abs()
    away_abs = _numeric_candidate_series(df_candidates, "lambda_away_adjustment_pct").abs()
    adjusted_mask = (home_abs > 1e-12) | (away_abs > 1e-12)
    max_abs = max(float(home_abs.max()) if not home_abs.empty else 0.0, float(away_abs.max()) if not away_abs.empty else 0.0)
    return {
        "candidates_with_adjustment": int(adjusted_mask.sum()),
        "avg_abs_lambda_home_adjustment_pct": round(float(home_abs.mean()) if not home_abs.empty else 0.0, 6),
        "avg_abs_lambda_away_adjustment_pct": round(float(away_abs.mean()) if not away_abs.empty else 0.0, 6),
        "max_abs_lambda_adjustment_pct": round(max_abs, 6),
    }


def build_portfolio_correlation_summary(df_final: pd.DataFrame, df_portfolio_rejected: pd.DataFrame) -> dict[str, object]:
    frames = []
    for df in (df_final, df_portfolio_rejected):
        if not df.empty and "correlation_cluster_key" in df.columns:
            frames.append(df.copy())
    if frames:
        combined = pd.concat(frames, ignore_index=True)
        cluster_keys = combined.get("correlation_cluster_key", pd.Series(dtype=object)).fillna("").astype(str)
        clustered = combined[cluster_keys.str.strip() != ""].copy()
        if not clustered.empty:
            cluster_sizes = clustered.groupby("correlation_cluster_key").size()
            clusters_with_multiple = int((cluster_sizes > 1).sum())
            clusters_total = clusters_with_multiple
        else:
            clusters_total = 0
            clusters_with_multiple = 0
    else:
        clusters_total = 0
        clusters_with_multiple = 0

    reject_reasons = (
        Counter(df_portfolio_rejected.get("portfolio_reject_reason", pd.Series(dtype=object)).fillna("missing"))
        if not df_portfolio_rejected.empty
        else Counter()
    )
    return {
        "clusters_total": clusters_total,
        "clusters_with_multiple_candidates": clusters_with_multiple,
        "rejected_equivalent": int(reject_reasons.get("EQUIVALENT_MARKET_LOWER_SCORE", 0)),
        "rejected_high_correlation": int(reject_reasons.get("HIGH_CORRELATION_LOWER_SCORE", 0)),
        "rejected_contradictory": int(reject_reasons.get("CONTRADICTORY_WITH_SELECTED", 0)),
    }


def _avg_numeric_column(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    if values.empty:
        return 0.0
    return round(float(values.mean()), 6)


def build_entry_quality_summary(df_final: pd.DataFrame, df_portfolio_rejected: pd.DataFrame) -> dict[str, object]:
    if not df_final.empty and "entry_quality_tier" in df_final.columns:
        tiers = Counter(df_final["entry_quality_tier"].fillna("missing"))
    else:
        tiers = Counter()
    return {
        "avg_entry_quality_score": _avg_numeric_column(df_final, "entry_quality_score"),
        "picks_by_quality_tier": {tier: int(tiers.get(tier, 0)) for tier in ("A", "B", "C", "D")},
        "portfolio_rejected_avg_quality_score": _avg_numeric_column(df_portfolio_rejected, "entry_quality_score"),
    }


def print_pricing_summary(
    *,
    priced_market_counts: Counter,
    df_candidates: pd.DataFrame,
    safety_gate_blocked_total: int,
    df_final: pd.DataFrame,
    processing_discard_counts: Counter,
    approved_market_counts: Counter,
) -> None:
    print(
        "[4] Pricing/Filtro: "
        f"{sum(priced_market_counts.values())} linhas precificadas | "
        f"{len(df_candidates)} aprovadas no filtro de pick | "
        f"{safety_gate_blocked_total} bloqueadas por safety gate | "
        f"{len(df_final)} picks finais"
    )
    print(" -> Descartes por motivo:", ", ".join(f"{k}={v}" for k, v in sorted(processing_discard_counts.items())) or "nenhum")
    print(" -> Precificadas por mercado:", ", ".join(f"{k}={v}" for k, v in sorted(priced_market_counts.items())) or "nenhuma")
    print(" -> Aprovadas no filtro por mercado:", ", ".join(f"{k}={v}" for k, v in sorted(approved_market_counts.items())) or "nenhuma")


def print_scan_report(df_final: pd.DataFrame) -> dict[str, Counter]:
    print("\n================ [ SCAN REPORT ] ================")
    if not df_final.empty:
        preview_cols = [
            "league",
            "match_name",
            "market_type",
            "selection_raw",
            "odd_entrada",
            "odd_justa",
            "ev_percent",
            "pricing_signal_type",
            "confidence_score",
            "confidence_score_type",
            "stake_units",
            "risk_flags",
        ]
        print(df_final[preview_cols].to_string(index=False))
        final_picks_by_market = Counter(df_final["market_type"].fillna("missing"))
        final_picks_by_league = Counter(df_final["league"].fillna("missing"))
        final_picks_by_confidence = Counter(df_final["confidence_score"].fillna("missing"))
        print(" -> Picks finais por mercado:", ", ".join(f"{k}={v}" for k, v in sorted(final_picks_by_market.items())))
        print(" -> Picks finais por liga:", ", ".join(f"{k}={v}" for k, v in sorted(final_picks_by_league.items())))
        print(" -> Picks finais por confiança:", ", ".join(f"{k}={v}" for k, v in sorted(final_picks_by_confidence.items())))
    else:
        final_picks_by_market = Counter()
        final_picks_by_league = Counter()
        final_picks_by_confidence = Counter()
        print("0 entradas aprovadas na régua da Entrega 4.")
    return {
        "final_picks_by_market": final_picks_by_market,
        "final_picks_by_league": final_picks_by_league,
        "final_picks_by_confidence": final_picks_by_confidence,
    }


def build_quality_report(
    *,
    run_id: str,
    target_date: str,
    runtime_config,
    config_snapshot_file,
    generated_at: str,
    odds_path,
    xg_path,
    odds_run_id: str,
    xg_run_id: str,
    odds_snapshot_hash: str,
    xg_snapshot_hash: str,
    odds_snapshot_time: str | None,
    xg_asof: str | None,
    temporal_status: str,
    snapshot_validation: dict[str, object],
    signal_version: str,
    pipeline_version: str,
    ledger_file: str,
    df_betano: pd.DataFrame,
    df_xg: pd.DataFrame,
    df_alvo: pd.DataFrame,
    normalized_status_counts: Counter,
    market_scope_counts: Counter,
    normalized_market_type_counts: Counter,
    base_filter_discard_counts: Counter,
    league_skipped_missing_xg_snapshot: dict[str, int],
    status_counts: dict[str, int],
    pending_rows: list,
    unique_pending_counts: Counter,
    unique_pending_by_league: Counter,
    registry_stale_leagues: set,
    processing_discard_counts: Counter,
    df_raw_candidates: pd.DataFrame,
    priced_market_counts: Counter,
    df_candidates: pd.DataFrame,
    approved_market_counts: Counter,
    df_blocked_candidates: pd.DataFrame,
    safety_gate_blocked_total: int,
    df_portfolio_rejected: pd.DataFrame,
    run_safety_status: str,
    official_unsafe_total: int,
    df_final: pd.DataFrame,
    final_picks_by_market: Counter,
    final_picks_by_league: Counter,
    final_picks_by_confidence: Counter,
    alias_pending_file,
    raw_candidates_file,
    blocked_candidates_file,
    pick_filter_approved_file,
    portfolio_rejected_file,
    picks_file,
) -> dict[str, object]:
    pre_snapshot_summary = build_pre_snapshot_discard_summary(odds_path)
    return {
        "run_id": run_id,
        "target_date": target_date,
        "pricing_variant": pricing_variant_from_payload(runtime_config.payload),
        "xg_residual_adjustment": quality_xg_residual_adjustment_payload(runtime_config.payload),
        "xg_residual_summary": build_xg_residual_summary(df_raw_candidates),
        "portfolio_correlation_summary": build_portfolio_correlation_summary(df_final, df_portfolio_rejected),
        "entry_quality_summary": build_entry_quality_summary(df_final, df_portfolio_rejected),
        "pre_snapshot_discard_counts": pre_snapshot_summary["pre_snapshot_discard_counts"],
        "pre_snapshot_discard_samples": pre_snapshot_summary["pre_snapshot_discard_samples"],
        "strategy_config": {
            "name": runtime_config.name,
            "label": runtime_config.label,
            "fingerprint": runtime_config.fingerprint,
            "source_path": runtime_config.source_path,
            "snapshot_file": str(config_snapshot_file),
        },
        "provenance": {
            "decision_timestamp": generated_at,
            "source_run_id": run_id,
            "source_snapshot_ref": f"odds:{odds_path}|xg:{xg_path}",
            "odds_source_run_id": odds_run_id or run_id,
            "xg_source_run_id": xg_run_id or run_id,
            "odds_snapshot_file": str(odds_path),
            "xg_snapshot_file": str(xg_path),
            "odds_snapshot_hash": odds_snapshot_hash,
            "xg_snapshot_hash": xg_snapshot_hash,
            "odds_snapshot_time": odds_snapshot_time,
            "xg_asof": xg_asof,
            "temporal_contract_version": TEMPORAL_CONTRACT_VERSION,
            "temporal_contract_status": temporal_status,
            "max_snapshot_age_hours": snapshot_validation.get("max_snapshot_age_hours"),
            "snapshot_validation_status": snapshot_validation.get("status"),
            "signal_version": signal_version,
            "pipeline_version": pipeline_version,
        },
        "data_quality": {
            "snapshot_validation": snapshot_validation,
            "league_skipped_missing_xg_snapshot": league_skipped_missing_xg_snapshot,
        },
        "source_files": {
            "odds_file": str(odds_path),
            "xg_file": str(xg_path),
            "ledger_file": str(ledger_file),
        },
        "inputs": {
            "odds_rows_total": int(len(df_betano)),
            "xg_rows_total": int(len(df_xg)),
            "odds_rows_by_league": to_sorted_dict(Counter(df_betano["league"].fillna("missing"))),
            "xg_rows_by_league": to_sorted_dict(Counter(df_xg["league"].fillna("missing"))),
        },
        "normalization": {
            "normalized_status_counts": to_sorted_dict(normalized_status_counts),
            "market_scope_counts": to_sorted_dict(market_scope_counts),
            "normalized_market_type_counts": to_sorted_dict(normalized_market_type_counts),
            "base_filter_discard_counts": to_sorted_dict(base_filter_discard_counts),
            "eligible_rows_total": int(len(df_alvo)),
            "eligible_rows_by_league": to_sorted_dict(Counter(df_alvo["league"].fillna("missing"))),
            "eligible_rows_by_market_type": to_sorted_dict(Counter(df_alvo["market_type"].fillna("missing"))),
        },
        "matching": {
            "status_occurrences": to_sorted_dict(status_counts),
            "unique_alias_rows_total": int(len(pending_rows)),
            "unique_alias_rows_by_status": to_sorted_dict(unique_pending_counts),
            "unique_alias_rows_by_league": to_sorted_dict(unique_pending_by_league),
            "registry_stale": bool(
                status_counts.get("auto_fuzzy_high", 0)
                or unique_pending_counts.get("pending_review", 0)
                or unique_pending_counts.get("blocked", 0)
                or processing_discard_counts.get("unresolved_team_match", 0)
            ),
            "registry_stale_leagues": sorted(registry_stale_leagues),
            "registry_pending": bool(
                unique_pending_counts.get("auto_fuzzy_high", 0)
                or unique_pending_counts.get("pending_review", 0)
                or unique_pending_counts.get("blocked", 0)
            ),
            "registry_issue_counts_by_league": to_sorted_dict(unique_pending_by_league),
            "registry_recommendation": "Rode python3 scripts/sync_team_aliases.py --league '<liga>' para ligas com MATCH_FUZZY ou unresolved_team_match.",
            "registry_recommended_commands": [
                f"python3 scripts/sync_team_aliases.py --league \"{league}\""
                for league in sorted(registry_stale_leagues)
            ],
        },
        "processing": {
            "raw_candidates_total": int(len(df_raw_candidates)),
            "priced_candidates_total": int(sum(priced_market_counts.values())),
            "priced_candidates_by_market_type": to_sorted_dict(priced_market_counts),
            "pick_filter_approved_total": int(len(df_candidates)),
            "pick_filter_approved_by_market_type": to_sorted_dict(approved_market_counts),
            "blocked_candidates_total": int(len(df_blocked_candidates)),
            "blocked_candidates_by_reason": to_sorted_dict(Counter(df_blocked_candidates.get("safety_reject_reason", pd.Series(dtype=object)).fillna("missing"))) if not df_blocked_candidates.empty else {},
            "safety_gate_blocked_total": safety_gate_blocked_total,
            "safety_gate_blocked_by_flag": to_sorted_dict(Counter("|".join(df_blocked_candidates.get("safety_gate_reason", pd.Series(dtype=object)).fillna("")).split("|"))) if not df_blocked_candidates.empty else {},
            "portfolio_rejected_total": int(len(df_portfolio_rejected)),
            "portfolio_rejected_by_reason": to_sorted_dict(Counter(df_portfolio_rejected.get("portfolio_reject_reason", pd.Series(dtype=object)).fillna("missing"))) if not df_portfolio_rejected.empty else {},
            "portfolio_correlation_summary": build_portfolio_correlation_summary(df_final, df_portfolio_rejected),
            "discard_reason_counts": to_sorted_dict(processing_discard_counts),
        },
        "safety": {
            "run_safety_status": run_safety_status,
            "official_unsafe_total": official_unsafe_total,
            "safety_gate_blocked_total": safety_gate_blocked_total,
            "blocked_candidates_file": str(blocked_candidates_file) if not df_blocked_candidates.empty else None,
        },
        "outputs": {
            "final_picks_total": int(len(df_final)),
            "final_picks_by_market_type": to_sorted_dict(final_picks_by_market),
            "final_picks_by_league": to_sorted_dict(final_picks_by_league),
            "final_picks_by_confidence": to_sorted_dict(final_picks_by_confidence),
            "alias_pending_file": str(alias_pending_file),
            "raw_candidates_file": str(raw_candidates_file),
            "blocked_candidates_file": str(blocked_candidates_file),
            "pick_filter_approved_file": str(pick_filter_approved_file),
            "portfolio_rejected_file": str(portfolio_rejected_file),
            "picks_file": str(picks_file),
        },
    }


def build_snapshot_rejection_report(
    *,
    run_id: str,
    target_date: str,
    runtime_config,
    config_snapshot_file,
    generated_at: str,
    odds_path,
    xg_path,
    odds_run_id: str,
    xg_run_id: str,
    odds_snapshot_hash: str,
    xg_snapshot_hash: str,
    odds_snapshot_time: str | None,
    xg_asof: str | None,
    temporal_status: str,
    snapshot_validation: dict[str, object],
    signal_version: str,
    pipeline_version: str,
    ledger_file: str,
) -> dict[str, object]:
    pre_snapshot_summary = build_pre_snapshot_discard_summary(odds_path)
    return {
        "run_id": run_id,
        "target_date": target_date,
        "quality_status": "rejected",
        "pricing_variant": pricing_variant_from_payload(runtime_config.payload),
        "xg_residual_adjustment": quality_xg_residual_adjustment_payload(runtime_config.payload),
        "xg_residual_summary": build_xg_residual_summary(pd.DataFrame()),
        "entry_quality_summary": build_entry_quality_summary(pd.DataFrame(), pd.DataFrame()),
        "pre_snapshot_discard_counts": pre_snapshot_summary["pre_snapshot_discard_counts"],
        "pre_snapshot_discard_samples": pre_snapshot_summary["pre_snapshot_discard_samples"],
        "error": {
            "code": "snapshot_validation_failed",
            "message": "SnapshotValidator rejected odds/xG inputs before pricing.",
            "details": snapshot_validation.get("errors", []),
        },
        "strategy_config": {
            "name": runtime_config.name,
            "label": runtime_config.label,
            "fingerprint": runtime_config.fingerprint,
            "source_path": runtime_config.source_path,
            "snapshot_file": str(config_snapshot_file),
        },
        "provenance": {
            "decision_timestamp": generated_at,
            "source_run_id": run_id,
            "source_snapshot_ref": f"odds:{odds_path}|xg:{xg_path}",
            "odds_source_run_id": odds_run_id or run_id,
            "xg_source_run_id": xg_run_id or run_id,
            "odds_snapshot_file": str(odds_path),
            "xg_snapshot_file": str(xg_path),
            "odds_snapshot_hash": odds_snapshot_hash,
            "xg_snapshot_hash": xg_snapshot_hash,
            "odds_snapshot_time": odds_snapshot_time,
            "xg_asof": xg_asof,
            "temporal_contract_version": TEMPORAL_CONTRACT_VERSION,
            "temporal_contract_status": temporal_status,
            "max_snapshot_age_hours": snapshot_validation.get("max_snapshot_age_hours"),
            "snapshot_validation_status": snapshot_validation.get("status"),
            "signal_version": signal_version,
            "pipeline_version": pipeline_version,
        },
        "data_quality": {
            "snapshot_validation": snapshot_validation,
        },
        "source_files": {
            "odds_file": str(odds_path),
            "xg_file": str(xg_path),
            "ledger_file": str(ledger_file),
        },
        "outputs": {
            "final_picks_total": 0,
            "picks_file": None,
        },
    }


def save_run_quality_report(run_dir, quality_report: dict[str, object]):
    return save_quality_report(run_dir, quality_report)
