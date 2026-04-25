from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from vcbet.core.config_ligas import obter_nomes_ligas_ativas
from vcbet.core.decision_policy import evaluate_pick_candidate_with_details
from vcbet.core.line_selector import select_top_picks
from vcbet.core.market_normalizer import normalize_odds_dataframe
from vcbet.core.pick_features import build_candidate_row
from vcbet.core.pricing_engine import calculate_lambdas, price_market_selection
from vcbet.core.run_utils import ensure_run_dir, now_str, save_quality_report, update_manifest
from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE, append_new_picks_to_ledger
from vcbet.core.strategy_config import configure_runtime, get_runtime_config, save_runtime_snapshot
from vcbet.core.team_matcher import PendingAliasRow, load_alias_cache, match_team_name, write_pending_aliases
from vcbet.core.temporal_contract import (
    TEMPORAL_CONTRACT_VERSION,
    file_md5,
    snapshot_time_from_dataframe,
    temporal_contract_status,
)


HIGH_MATCH_THRESHOLD = 90
REVIEW_MATCH_THRESHOLD = 75
SUPPORTED_MARKETS = {
    "total_goals",
    "team_total",
    "btts",
    "asian_total",
    "asian_handicap",
}
SIGNAL_VERSION = "ev_pipeline_v1"
PIPELINE_VERSION = "pipeline_ev_phase3_provenance"


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


def to_sorted_dict(counter_like) -> dict:
    if isinstance(counter_like, Counter):
        items = counter_like.items()
    elif isinstance(counter_like, dict):
        items = counter_like.items()
    else:
        items = counter_like
    return {str(k): int(v) for k, v in sorted(items, key=lambda item: str(item[0]))}


def processar_pipeline(
    odds_file: str,
    xg_file: str,
    run_id: str | None = None,
    output_dir: str = "data/runs",
    alias_file: str = "alias_times.json",
    ledger_file: str = str(DEFAULT_LEDGER_FILE),
    modo_debug: bool = False,
    config_file: str | None = None,
    config_name: str | None = None,
):
    runtime_config = configure_runtime(config_name=config_name, config_file=config_file)
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
    run_id = run_id or odds_run_id or xg_run_id
    if not run_id:
        raise ValueError("run_id não informado e não encontrado nos snapshots.")

    target_date = odds_path.parent.parent.name if odds_path.parent.parent.name else pd.Timestamp.now().strftime("%Y-%m-%d")
    run_dir = ensure_run_dir(run_id=run_id, target_date=target_date, base_output_dir=output_dir)
    alias_pending_file = run_dir / "alias_review_pending.csv"
    picks_file = run_dir / "picks_snapshot.csv"
    config_snapshot_file = save_runtime_snapshot(run_dir)
    odds_snapshot_hash = file_md5(odds_path)
    xg_snapshot_hash = file_md5(xg_path)
    odds_snapshot_time = snapshot_time_from_dataframe(df_betano)
    xg_asof = snapshot_time_from_dataframe(df_xg)

    print(f"[0] Configuração ativa: {runtime_config.label} ({runtime_config.fingerprint})")
    print(f"    source: {runtime_config.source_path or 'default_embutida'}")
    print(f"[1] Arquivo de odds carregado: {odds_path}")
    print(f"[2] Arquivo de xG carregado: {xg_path}")

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
        if row.get("market_type") not in SUPPORTED_MARKETS:
            base_filter_discard_counts["unsupported_market_type"] += 1
            continue

    df_alvo = df_betano[
        (df_betano["normalized_status"] == "ok")
        & (df_betano["market_scope"] == "full_time")
        & (df_betano["market_type"].isin(SUPPORTED_MARKETS))
    ].copy()
    print("[3] Normalização/Filtro base: " f"{len(df_alvo)} linhas elegíveis de {len(df_betano)} totais")

    alias_cache = load_alias_cache(alias_file)
    xg_by_league = {league: league_df.copy() for league, league_df in df_xg.groupby("league")}
    pending_rows: list[PendingAliasRow] = []
    pending_seen = set()
    registry_stale_leagues = set()
    status_counts = {key: 0 for key in ["MATCH_REGISTRY_APPROVED", "auto_exact", "auto_fuzzy_high", "manual_approved", "pending_review", "blocked"]}
    generated_at = now_str()
    temporal_status = temporal_contract_status(
        decision_timestamp=generated_at,
        odds_snapshot_time=odds_snapshot_time,
        xg_asof=xg_asof,
    )

    processing_discard_counts = Counter()
    raw_candidate_rows: list[dict] = []
    blocked_candidate_rows: list[dict] = []
    candidate_rows: list[dict] = []
    priced_market_counts = Counter()
    approved_market_counts = Counter()

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

        candidates = df_xg_liga["team_name"].tolist()
        home_match = match_team_name(time_casa, candidates, alias_cache, league=liga_jogo, high_threshold=HIGH_MATCH_THRESHOLD, review_threshold=REVIEW_MATCH_THRESHOLD)
        away_match = match_team_name(time_fora, candidates, alias_cache, league=liga_jogo, high_threshold=HIGH_MATCH_THRESHOLD, review_threshold=REVIEW_MATCH_THRESHOLD)

        for res, side in ((home_match, "home"), (away_match, "away")):
            status_counts[res.match_status] = status_counts.get(res.match_status, 0) + 1
            if res.match_status in {"auto_fuzzy_high", "pending_review", "blocked"}:
                registry_stale_leagues.add(str(liga_jogo))
            if res.match_status in {"pending_review", "blocked"}:
                key = (liga_jogo, res.source_name, side)
                if key not in pending_seen:
                    pending_seen.add(key)
                    pending_rows.append(PendingAliasRow(
                        run_id=run_id,
                        created_at=generated_at,
                        league=liga_jogo,
                        match_name=str(linha["match_name"]),
                        side=side,
                        source_name=res.source_name,
                        suggestion=res.suggestion,
                        score=res.score,
                        match_status=res.match_status,
                    ))

        if not home_match.matched_name or not away_match.matched_name:
            processing_discard_counts["unresolved_team_match"] += 1
            continue

        home_xg_row = df_xg_liga.loc[df_xg_liga["team_name"] == home_match.matched_name].iloc[0]
        away_xg_row = df_xg_liga.loc[df_xg_liga["team_name"] == away_match.matched_name].iloc[0]

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

    write_pending_aliases(pending_rows, alias_pending_file)

    unique_pending_counts = Counter(row.match_status for row in pending_rows)
    unique_pending_by_league = Counter(row.league for row in pending_rows)
    print(
        " -> Pareamento: "
        f"{status_counts['auto_exact']} exatos, "
        f"{status_counts['MATCH_REGISTRY_APPROVED']} registry, "
        f"{status_counts['auto_fuzzy_high']} fuzzy altos, "
        f"{status_counts['manual_approved']} manuais, "
        f"{status_counts['pending_review']} pendentes, "
        f"{status_counts['blocked']} bloqueados"
    )
    print(
        " -> Aliases únicos: "
        f"{len(pending_rows)} total | "
        f"{unique_pending_counts.get('pending_review', 0)} pendentes | "
        f"{unique_pending_counts.get('blocked', 0)} bloqueados"
    )
    print(f" -> Fila manual de aliases: {alias_pending_file}")

    df_candidates = pd.DataFrame(candidate_rows)
    df_raw_candidates = pd.DataFrame(raw_candidate_rows)
    df_blocked_candidates = pd.DataFrame(blocked_candidate_rows)
    pick_filter_approved_file = run_dir / "pick_filter_approved.csv"
    raw_candidates_file = run_dir / "raw_candidates.csv"
    blocked_candidates_file = run_dir / "blocked_candidates.csv"
    portfolio_rejected_file = run_dir / "portfolio_rejected.csv"
    if not df_candidates.empty:
        df_final, df_portfolio_rejected = select_top_picks(df_candidates, return_meta=True)
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
        df_final["source_run_id"] = run_id
        df_final["source_snapshot_ref"] = f"odds:{odds_path}|xg:{xg_path}"
        df_final["odds_snapshot_file"] = str(odds_path)
        df_final["xg_snapshot_file"] = str(xg_path)
        df_final["odds_snapshot_hash"] = odds_snapshot_hash
        df_final["xg_snapshot_hash"] = xg_snapshot_hash
        df_final["odds_snapshot_time"] = odds_snapshot_time or ""
        df_final["xg_asof"] = xg_asof or ""
        df_final["temporal_contract_version"] = TEMPORAL_CONTRACT_VERSION
        df_final["temporal_contract_status"] = temporal_status
        df_final["signal_version"] = SIGNAL_VERSION
        df_final["pipeline_version"] = PIPELINE_VERSION

    safety_gate_blocked_total = int((df_blocked_candidates.get("pick_safety_status", pd.Series(dtype=object)) == "blocked").sum()) if not df_blocked_candidates.empty else 0
    official_unsafe_total = int((df_final.get("pick_safety_status", pd.Series(dtype=object)) != "safe").sum()) if not df_final.empty else 0
    if official_unsafe_total:
        run_safety_status = "unsafe_official_picks"
    elif safety_gate_blocked_total:
        run_safety_status = "safe_with_blocked_candidates"
    else:
        run_safety_status = "safe"

    if not df_raw_candidates.empty:
        df_raw_candidates.to_csv(raw_candidates_file, index=False, sep=";", encoding="utf-8-sig")
    if not df_candidates.empty:
        df_candidates.to_csv(pick_filter_approved_file, index=False, sep=";", encoding="utf-8-sig")
    if not df_blocked_candidates.empty:
        df_blocked_candidates.to_csv(blocked_candidates_file, index=False, sep=";", encoding="utf-8-sig")
    if not df_portfolio_rejected.empty:
        df_portfolio_rejected.to_csv(portfolio_rejected_file, index=False, sep=";", encoding="utf-8-sig")

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

    quality_report = {
        "run_id": run_id,
        "target_date": target_date,
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
            "signal_version": SIGNAL_VERSION,
            "pipeline_version": PIPELINE_VERSION,
        },
        "source_files": {
            "odds_file": str(odds_path),
            "xg_file": str(xg_path),
            "alias_file": str(alias_file),
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
            "registry_recommendation": "Rode scripts/sync_team_aliases.py --league '<liga>' para ligas com MATCH_FUZZY ou unresolved_team_match.",
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
    quality_report_file = save_quality_report(run_dir, quality_report)

    if not df_final.empty:
        if not modo_debug:
            export_cols = [
                "bet_id", "run_id", "generated_at", "league", "match_datetime", "home_team", "away_team",
                "match_name", "market_type", "market_scope", "market_raw", "event_url", "selection_raw",
                "line", "side", "target_team_role", "target_team_name", "odd_entrada", "odd_justa",
                "prob_model", "ev_percent", "pricing_signal_type", "confidence_score",
                "confidence_score_type", "confidence_score_scale", "stake_units", "entry_reason",
                "risk_flags", "pick_safety_status", "candidate_stage", "safety_gate_reason",
                "decision_policy_status", "decision_reject_reason", "selection_policy_status",
                "portfolio_risk_status", "portfolio_risk_reason", "portfolio_exposure_scope",
                "portfolio_exposure_after", "market_family",
                "strategy_config_name", "strategy_config_fingerprint", "config_name", "config_fingerprint",
                "config_source_path", "config_snapshot_file", "source_run_id", "source_snapshot_ref",
                "odds_source_run_id", "xg_source_run_id", "odds_snapshot_file", "xg_snapshot_file",
                "odds_snapshot_hash", "xg_snapshot_hash", "odds_snapshot_time", "xg_asof",
                "temporal_contract_version", "temporal_contract_status", "decision_timestamp", "signal_version",
                "pipeline_version", "correlation_level", "coexistence_status",
            ]
            df_final[export_cols].to_csv(picks_file, index=False, sep=";", encoding="utf-8-sig")
            ledger_path, ledger_added_rows, ledger_total_rows = append_new_picks_to_ledger(df_final[export_cols], ledger_file)
            print(f"\n[+] Picks exportadas com sucesso: {picks_file}")
            print(f"[+] Ledger atualizado: {ledger_path} | novas={ledger_added_rows} | total={ledger_total_rows}")
            print(f"[+] Quality report salvo: {quality_report_file}")
            update_manifest(
                run_dir,
                status="pipeline_completed",
                picks_file=str(picks_file),
                picks_rows=len(df_final),
                ledger_file=str(ledger_path),
                ledger_added_rows=ledger_added_rows,
                ledger_total_rows=ledger_total_rows,
                alias_pending_file=str(alias_pending_file),
                alias_pending_rows=len(pending_rows),
                team_match_status_counts=status_counts,
                quality_report_file=str(quality_report_file),
                run_safety_status=run_safety_status,
                safety_gate_blocked_total=safety_gate_blocked_total,
                strategy_config_name=runtime_config.name,
                strategy_config_fingerprint=runtime_config.fingerprint,
                strategy_config_file=str(config_snapshot_file),
                config_name=runtime_config.name,
                config_fingerprint=runtime_config.fingerprint,
                config_source_path=runtime_config.source_path,
                config_snapshot_file=str(config_snapshot_file),
                source_run_id=run_id,
                source_snapshot_ref=f"odds:{odds_path}|xg:{xg_path}",
                odds_snapshot_hash=odds_snapshot_hash,
                xg_snapshot_hash=xg_snapshot_hash,
                odds_snapshot_time=odds_snapshot_time,
                xg_asof=xg_asof,
                temporal_contract_version=TEMPORAL_CONTRACT_VERSION,
                temporal_contract_status=temporal_status,
                signal_version=SIGNAL_VERSION,
                pipeline_version=PIPELINE_VERSION,
            )
        else:
            print("\n[!] MODO DEBUG: execução concluída sem salvar picks.")
            print(f"[+] Quality report salvo: {quality_report_file}")
            update_manifest(
                run_dir,
                status="pipeline_debug",
                picks_rows=len(df_final),
                alias_pending_file=str(alias_pending_file),
                alias_pending_rows=len(pending_rows),
                team_match_status_counts=status_counts,
                quality_report_file=str(quality_report_file),
                run_safety_status=run_safety_status,
                safety_gate_blocked_total=safety_gate_blocked_total,
                strategy_config_name=runtime_config.name,
                strategy_config_fingerprint=runtime_config.fingerprint,
                strategy_config_file=str(config_snapshot_file),
                config_name=runtime_config.name,
                config_fingerprint=runtime_config.fingerprint,
                config_source_path=runtime_config.source_path,
                config_snapshot_file=str(config_snapshot_file),
                source_run_id=run_id,
                source_snapshot_ref=f"odds:{odds_path}|xg:{xg_path}",
                odds_snapshot_hash=odds_snapshot_hash,
                xg_snapshot_hash=xg_snapshot_hash,
                odds_snapshot_time=odds_snapshot_time,
                xg_asof=xg_asof,
                temporal_contract_version=TEMPORAL_CONTRACT_VERSION,
                temporal_contract_status=temporal_status,
                signal_version=SIGNAL_VERSION,
                pipeline_version=PIPELINE_VERSION,
            )
    else:
        print(f"[+] Quality report salvo: {quality_report_file}")
        update_manifest(
            run_dir,
            status="pipeline_empty",
            picks_rows=0,
            alias_pending_file=str(alias_pending_file),
            alias_pending_rows=len(pending_rows),
            team_match_status_counts=status_counts,
            quality_report_file=str(quality_report_file),
            run_safety_status=run_safety_status,
            safety_gate_blocked_total=safety_gate_blocked_total,
            strategy_config_name=runtime_config.name,
            strategy_config_fingerprint=runtime_config.fingerprint,
            strategy_config_file=str(config_snapshot_file),
            config_name=runtime_config.name,
            config_fingerprint=runtime_config.fingerprint,
            config_source_path=runtime_config.source_path,
            config_snapshot_file=str(config_snapshot_file),
            source_run_id=run_id,
            source_snapshot_ref=f"odds:{odds_path}|xg:{xg_path}",
            odds_snapshot_hash=odds_snapshot_hash,
            xg_snapshot_hash=xg_snapshot_hash,
            odds_snapshot_time=odds_snapshot_time,
            xg_asof=xg_asof,
            temporal_contract_version=TEMPORAL_CONTRACT_VERSION,
            temporal_contract_status=temporal_status,
            signal_version=SIGNAL_VERSION,
            pipeline_version=PIPELINE_VERSION,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline EV com pricing estruturado")
    parser.add_argument("--odds-file", required=True, help="Caminho do odds_snapshot.csv")
    parser.add_argument("--xg-file", required=True, help="Caminho do xg_snapshot.csv")
    parser.add_argument("--run-id", help="Identificador único da execução")
    parser.add_argument("--output-dir", default="data/runs", help="Diretório base para salvar as runs")
    parser.add_argument("--alias-file", default="alias_times.json", help="Arquivo JSON com aliases aprovados manualmente")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE), help="Caminho do bets_ledger.csv")
    parser.add_argument("--debug", action="store_true", help="Executa normalmente, mas não salva arquivos no final")
    parser.add_argument("--config-file", help="Arquivo JSON de configuração de estratégia")
    parser.add_argument("--config-name", help="Nome do preset em ./configs sem .json")
    args = parser.parse_args()

    processar_pipeline(
        odds_file=args.odds_file,
        xg_file=args.xg_file,
        run_id=args.run_id,
        output_dir=args.output_dir,
        alias_file=args.alias_file,
        ledger_file=args.ledger_file,
        modo_debug=args.debug,
        config_file=args.config_file,
        config_name=args.config_name,
    )
