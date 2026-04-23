from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from config_ligas import obter_nomes_ligas_ativas
from correlation_rules import select_top_picks
from market_normalizer import normalize_odds_dataframe
from pick_filter import evaluate_pick_candidate_with_meta, is_xg_fallback
from pricing_engine import calculate_lambdas, expected_value_decimal, fair_odd_from_probs, price_market_selection
from run_utils import ensure_run_dir, now_str, save_quality_report, update_manifest
from ledger_manager import DEFAULT_LEDGER_FILE, append_new_picks_to_ledger
from team_matcher import PendingAliasRow, load_alias_cache, match_team_name, write_pending_aliases


HIGH_MATCH_THRESHOLD = 90
REVIEW_MATCH_THRESHOLD = 75
SUPPORTED_MARKETS = {
    "total_goals",
    "team_total",
    "btts",
    "asian_total",
    "asian_handicap",
}


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

    if "normalized_status" not in df_betano.columns:
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


def build_candidate_row(
    *,
    run_id: str,
    odds_run_id: str,
    xg_run_id: str,
    generated_at: str,
    row: pd.Series,
    home_match_status: str,
    away_match_status: str,
    lambda_bundle: dict[str, float],
    pricing_result: dict,
    home_xg_row: pd.Series,
    away_xg_row: pd.Series,
) -> dict:
    probs = pricing_result["probs"]
    fair_odd = fair_odd_from_probs(probs)
    ev_decimal = expected_value_decimal(probs, float(row["odd"]))

    return {
        "run_id": run_id,
        "odds_source_run_id": odds_run_id,
        "xg_source_run_id": xg_run_id,
        "generated_at": generated_at,
        "league": row["league"],
        "match_datetime": row["match_datetime"],
        "home_team": row["home_team"],
        "away_team": row["away_team"],
        "match_name": row["match_name"],
        "market_type": row["market_type"],
        "market_scope": row["market_scope"],
        "market_raw": row["market_raw"],
        "selection_raw": row["selection_raw"],
        "line": None if pd.isna(row.get("line")) else float(row.get("line")),
        "side": row.get("side"),
        "target_team_role": row.get("target_team_role"),
        "target_team_name": row.get("target_team_name"),
        "event_url": row.get("event_url"),
        "odd_entrada": float(row["odd"]),
        "prob_model": round(probs["win"] + 0.5 * probs["half_win"], 6),
        "odd_justa": fair_odd,
        "ev_decimal": ev_decimal,
        "mu_total": lambda_bundle["mu_total"],
        "lambda_home": lambda_bundle["lambda_home"],
        "lambda_away": lambda_bundle["lambda_away"],
        "match_status_home": home_match_status,
        "match_status_away": away_match_status,
        "xg_fallback_home": is_xg_fallback(home_xg_row),
        "xg_fallback_away": is_xg_fallback(away_xg_row),
    }


def processar_pipeline(
    odds_file: str,
    xg_file: str,
    run_id: str | None = None,
    output_dir: str = "data/runs",
    alias_file: str = "alias_times.json",
    ledger_file: str = str(DEFAULT_LEDGER_FILE),
    modo_debug: bool = False,
):
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
    status_counts = {key: 0 for key in ["auto_exact", "auto_fuzzy_high", "manual_approved", "pending_review", "blocked"]}
    generated_at = now_str()

    processing_discard_counts = Counter()
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
        home_match = match_team_name(time_casa, candidates, alias_cache, high_threshold=HIGH_MATCH_THRESHOLD, review_threshold=REVIEW_MATCH_THRESHOLD)
        away_match = match_team_name(time_fora, candidates, alias_cache, high_threshold=HIGH_MATCH_THRESHOLD, review_threshold=REVIEW_MATCH_THRESHOLD)

        for res, side in ((home_match, "home"), (away_match, "away")):
            status_counts[res.match_status] = status_counts.get(res.match_status, 0) + 1
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
            lambda_bundle=lambda_bundle,
            pricing_result=pricing_result,
            home_xg_row=home_xg_row,
            away_xg_row=away_xg_row,
        )
        evaluated, reject_reason = evaluate_pick_candidate_with_meta(candidate)
        if evaluated:
            candidate_rows.append(evaluated)
            approved_market_counts[linha["market_type"]] += 1
        else:
            processing_discard_counts[f"pick_filter_{reject_reason or 'rejected'}"] += 1

    write_pending_aliases(pending_rows, alias_pending_file)

    unique_pending_counts = Counter(row.match_status for row in pending_rows)
    unique_pending_by_league = Counter(row.league for row in pending_rows)
    print(
        " -> Pareamento: "
        f"{status_counts['auto_exact']} exatos, "
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
    df_final = select_top_picks(df_candidates) if not df_candidates.empty else pd.DataFrame()

    print(
        "[4] Pricing/Filtro: "
        f"{sum(priced_market_counts.values())} linhas precificadas | "
        f"{len(df_candidates)} aprovadas no filtro de pick | "
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
            "confidence_score",
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
        },
        "processing": {
            "priced_candidates_total": int(sum(priced_market_counts.values())),
            "priced_candidates_by_market_type": to_sorted_dict(priced_market_counts),
            "pick_filter_approved_total": int(len(df_candidates)),
            "pick_filter_approved_by_market_type": to_sorted_dict(approved_market_counts),
            "discard_reason_counts": to_sorted_dict(processing_discard_counts),
        },
        "outputs": {
            "final_picks_total": int(len(df_final)),
            "final_picks_by_market_type": to_sorted_dict(final_picks_by_market),
            "final_picks_by_league": to_sorted_dict(final_picks_by_league),
            "final_picks_by_confidence": to_sorted_dict(final_picks_by_confidence),
            "alias_pending_file": str(alias_pending_file),
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
                "prob_model", "ev_percent", "confidence_score", "stake_units", "entry_reason",
                "risk_flags", "odds_source_run_id", "xg_source_run_id", "correlation_level", "coexistence_status",
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
    args = parser.parse_args()

    processar_pipeline(
        odds_file=args.odds_file,
        xg_file=args.xg_file,
        run_id=args.run_id,
        output_dir=args.output_dir,
        alias_file=args.alias_file,
        ledger_file=args.ledger_file,
        modo_debug=args.debug,
    )
