from __future__ import annotations

from collections import Counter

import pandas as pd

from vcbet.core.team_registry import DEFAULT_REGISTRY_FILE
from vcbet.core.team_matcher import PendingAliasRow, match_team_name, write_pending_aliases
from vcbet.team_identity.review_writer import upsert_pending_to_functional_file


FUZZY_HIGH_REVIEW_REASON = "MATCH_FUZZY_HIGH_CONFIDENCE"


def prepare_team_resolution_state(df_xg: pd.DataFrame) -> dict[str, object]:
    return {
        "xg_by_league": {league: league_df.copy() for league, league_df in df_xg.groupby("league")},
        "pending_rows": [],
        "pending_seen": set(),
        "registry_stale_leagues": set(),
        "status_counts": {key: 0 for key in ["MATCH_REGISTRY_APPROVED", "auto_exact", "auto_fuzzy_high", "pending_review", "blocked"]},
    }


def resolve_row_teams(
    *,
    linha,
    df_xg_liga: pd.DataFrame,
    run_id: str,
    generated_at: str,
    pending_rows: list[PendingAliasRow],
    pending_seen: set,
    registry_stale_leagues: set,
    status_counts: dict[str, int],
    high_threshold: int,
    review_threshold: int,
    registry_file=DEFAULT_REGISTRY_FILE,
) -> dict[str, object] | None:
    liga_jogo = linha["league"]
    candidates = df_xg_liga["team_name"].tolist()
    time_casa = str(linha.get("home_team", "")).strip()
    time_fora = str(linha.get("away_team", "")).strip()

    xg_source = str(df_xg_liga["source"].iloc[0]).strip().casefold() if "source" in df_xg_liga.columns and not df_xg_liga.empty else "footystats"
    source_team_id_map: dict[str, str] = {}
    if "source_team_id" in df_xg_liga.columns:
        source_team_id_map = {
            str(row["team_name"]): str(row["source_team_id"])
            for _, row in df_xg_liga.iterrows()
            if pd.notna(row.get("source_team_id")) and pd.notna(row.get("team_name"))
        }

    home_match = match_team_name(
        time_casa,
        candidates,
        league=liga_jogo,
        high_threshold=high_threshold,
        review_threshold=review_threshold,
        xg_source=xg_source,
        source_team_id_map=source_team_id_map,
        registry_file=registry_file,
    )
    away_match = match_team_name(
        time_fora,
        candidates,
        league=liga_jogo,
        high_threshold=high_threshold,
        review_threshold=review_threshold,
        xg_source=xg_source,
        source_team_id_map=source_team_id_map,
        registry_file=registry_file,
    )

    for res, side in ((home_match, "home"), (away_match, "away")):
        status_counts[res.match_status] = status_counts.get(res.match_status, 0) + 1
        if res.match_status in {"auto_fuzzy_high", "pending_review", "blocked"}:
            registry_stale_leagues.add(str(liga_jogo))
        if res.match_status in {"auto_fuzzy_high", "pending_review", "blocked"}:
            suggested_name = str(res.suggestion or "")
            key = (liga_jogo, res.source_name, suggested_name)
            if key not in pending_seen:
                is_fuzzy_high = res.match_status == "auto_fuzzy_high"
                registry_reason = (
                    "match_fuzzy_high_confidence"
                    if is_fuzzy_high
                    else ("match_requires_registry_review" if res.match_status == "pending_review" else "unresolved_or_blocked_team_match")
                )
                match_confidence = f"{res.score / 100:.4f}" if res.score else ""
                suggested_fotmob_name = suggested_name if xg_source == "fotmob" else ""
                suggested_fotmob_team_id = source_team_id_map.get(suggested_name, "") if xg_source == "fotmob" else ""
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
                    registry_status="registry_pending" if res.match_status in {"auto_fuzzy_high", "pending_review"} else "registry_stale",
                    registry_reason=registry_reason,
                    registry_pending_key=f"{liga_jogo}|{res.source_name}|{suggested_name}",
                    recommended_action="sync_team_registry",
                    suggested_fotmob_name=suggested_fotmob_name,
                    suggested_fotmob_team_id=suggested_fotmob_team_id,
                    match_confidence=match_confidence,
                    match_method="auto_fuzzy_high" if is_fuzzy_high else res.match_status,
                    review_reason=FUZZY_HIGH_REVIEW_REASON if is_fuzzy_high else "",
                    source="run_pipeline",
                    event_url=str(linha.get("event_url", "") or ""),
                    updated_at=generated_at,
                ))

    if not home_match.matched_name or not away_match.matched_name:
        return None

    return {
        "home_match": home_match,
        "away_match": away_match,
        "home_xg_row": df_xg_liga.loc[df_xg_liga["team_name"] == home_match.matched_name].iloc[0],
        "away_xg_row": df_xg_liga.loc[df_xg_liga["team_name"] == away_match.matched_name].iloc[0],
    }


def write_and_report_alias_review(
    *,
    pending_rows: list[PendingAliasRow],
    alias_pending_file,
    status_counts: dict[str, int],
    functional_pending_file: str | None = None,
) -> dict[str, object]:
    write_pending_aliases(pending_rows, alias_pending_file)

    if functional_pending_file:
        upserted = upsert_pending_to_functional_file(pending_rows, path=functional_pending_file)
        print(f" -> Fila funcional de aliases: {functional_pending_file} (+{upserted} upsertados)")
    else:
        print(" -> Fila funcional de aliases desabilitada (dry-run)")

    unique_pending_counts = Counter(row.match_status for row in pending_rows)
    unique_pending_by_league = Counter(row.league for row in pending_rows)
    print(
        " -> Pareamento: "
        f"{status_counts['auto_exact']} exatos, "
        f"{status_counts['MATCH_REGISTRY_APPROVED']} registry, "
        f"{status_counts['auto_fuzzy_high']} fuzzy altos, "

        f"{status_counts['pending_review']} pendentes, "
        f"{status_counts['blocked']} bloqueados"
    )
    print(
        " -> Aliases únicos: "
        f"{len(pending_rows)} total | "
        f"{unique_pending_counts.get('auto_fuzzy_high', 0)} fuzzy altos | "
        f"{unique_pending_counts.get('pending_review', 0)} pendentes | "
        f"{unique_pending_counts.get('blocked', 0)} bloqueados"
    )
    print(f" -> Fila manual de aliases: {alias_pending_file}")
    return {
        "unique_pending_counts": unique_pending_counts,
        "unique_pending_by_league": unique_pending_by_league,
    }
