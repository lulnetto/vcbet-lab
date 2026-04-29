from __future__ import annotations

from collections import Counter

import pandas as pd

from vcbet.core.decision_policy import evaluate_pick_candidate_with_details
from vcbet.core.pick_features import build_candidate_row
from vcbet.core.pricing_engine import calculate_lambdas, price_market_selection
from vcbet.core.pipeline.team_resolution import resolve_row_teams, write_and_report_alias_review


def build_priced_candidates(
    *,
    df_alvo: pd.DataFrame,
    resolution_state: dict[str, object],
    run_id: str,
    odds_run_id: str,
    xg_run_id: str,
    generated_at: str,
    alias_pending_file,
    high_match_threshold: int,
    review_match_threshold: int,
    functional_pending_file: str | None = None,
) -> dict[str, object]:
    processing_discard_counts = Counter()
    raw_candidate_rows: list[dict] = []
    blocked_candidate_rows: list[dict] = []
    candidate_rows: list[dict] = []
    priced_market_counts = Counter()
    approved_market_counts = Counter()

    xg_by_league = resolution_state["xg_by_league"]
    pending_rows = resolution_state["pending_rows"]
    pending_seen = resolution_state["pending_seen"]
    registry_stale_leagues = resolution_state["registry_stale_leagues"]
    status_counts = resolution_state["status_counts"]

    for _, linha in df_alvo.iterrows():
        time_casa = str(linha.get("home_team", "")).strip()
        time_fora = str(linha.get("away_team", "")).strip()
        if not time_casa or not time_fora:
            processing_discard_counts["missing_home_or_away_team"] += 1
            continue

        liga_jogo = linha["league"]
        df_xg_liga = xg_by_league.get(liga_jogo)
        if df_xg_liga is None or df_xg_liga.empty:
            processing_discard_counts["missing_xg_league_snapshot"] += 1
            continue

        resolved = resolve_row_teams(
            linha=linha,
            df_xg_liga=df_xg_liga,
            run_id=run_id,
            generated_at=generated_at,
            pending_rows=pending_rows,
            pending_seen=pending_seen,
            registry_stale_leagues=registry_stale_leagues,
            status_counts=status_counts,
            high_threshold=high_match_threshold,
            review_threshold=review_match_threshold,
        )
        if not resolved:
            processing_discard_counts["unresolved_team_match"] += 1
            continue

        home_match = resolved["home_match"]
        away_match = resolved["away_match"]
        home_xg_row = resolved["home_xg_row"]
        away_xg_row = resolved["away_xg_row"]

        lambda_bundle = calculate_lambdas(
            home_xg_row["xg_home"],
            home_xg_row["xga_home"] if "xga_home" in home_xg_row.index else home_xg_row["xga"],
            away_xg_row["xg_away"],
            away_xg_row["xga_away"] if "xga_away" in away_xg_row.index else away_xg_row["xga"],
        )

        pricing_result = price_market_selection(
            market_type=linha["market_type"],
            side=str(linha.get("side")),
            line=None if pd.isna(linha.get("line")) else float(linha.get("line")),
            target_team_role=str(linha.get("target_team_role") or "geral"),
            lambda_home=lambda_bundle["lambda_home"],
            lambda_away=lambda_bundle["lambda_away"],
        )
        if not pricing_result:
            processing_discard_counts["pricing_unavailable"] += 1
            continue

        priced_market_counts[linha["market_type"]] += 1
        candidate = build_candidate_row(
            run_id=run_id,
            odds_run_id=odds_run_id or run_id,
            xg_run_id=xg_run_id or run_id,
            generated_at=generated_at,
            row=linha,
            home_match_status=home_match.match_status,
            away_match_status=away_match.match_status,
            home_match_source=home_match.match_source,
            away_match_source=away_match.match_source,
            home_alias_confidence=home_match.alias_confidence,
            away_alias_confidence=away_match.alias_confidence,
            home_registry_file=home_match.registry_file,
            away_registry_file=away_match.registry_file,
            lambda_bundle=lambda_bundle,
            pricing_result=pricing_result,
            home_xg_row=home_xg_row,
            away_xg_row=away_xg_row,
        )
        raw_candidate_rows.append({**candidate, "candidate_stage": "raw_candidate"})
        evaluated, reject_reason, rejected_payload = evaluate_pick_candidate_with_details(candidate)
        if evaluated:
            candidate_rows.append(evaluated)
            approved_market_counts[linha["market_type"]] += 1
        else:
            processing_discard_counts[f"pick_filter_{reject_reason or 'rejected'}"] += 1
            if rejected_payload:
                blocked_candidate_rows.append(rejected_payload)

    alias_summary = write_and_report_alias_review(
        pending_rows=pending_rows,
        alias_pending_file=alias_pending_file,
        status_counts=status_counts,
        functional_pending_file=functional_pending_file,
    )

    return {
        "processing_discard_counts": processing_discard_counts,
        "raw_candidate_rows": raw_candidate_rows,
        "blocked_candidate_rows": blocked_candidate_rows,
        "candidate_rows": candidate_rows,
        "priced_market_counts": priced_market_counts,
        "approved_market_counts": approved_market_counts,
        "pending_rows": pending_rows,
        "registry_stale_leagues": registry_stale_leagues,
        "status_counts": status_counts,
        **alias_summary,
    }
