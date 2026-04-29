from __future__ import annotations

from collections import Counter

import pandas as pd

from vcbet.core.team_matcher import PendingAliasRow, load_alias_cache, match_team_name, write_pending_aliases
from vcbet.team_identity.review_writer import upsert_pending_to_functional_file


def prepare_team_resolution_state(alias_file: str, df_xg: pd.DataFrame) -> dict[str, object]:
    return {
        "alias_cache": load_alias_cache(alias_file),
        "xg_by_league": {league: league_df.copy() for league, league_df in df_xg.groupby("league")},
        "pending_rows": [],
        "pending_seen": set(),
        "registry_stale_leagues": set(),
        "status_counts": {key: 0 for key in ["MATCH_REGISTRY_APPROVED", "auto_exact", "auto_fuzzy_high", "manual_approved", "pending_review", "blocked"]},
    }


def resolve_row_teams(
    *,
    linha,
    df_xg_liga: pd.DataFrame,
    alias_cache: dict[str, str],
    run_id: str,
    generated_at: str,
    pending_rows: list[PendingAliasRow],
    pending_seen: set,
    registry_stale_leagues: set,
    status_counts: dict[str, int],
    high_threshold: int,
    review_threshold: int,
) -> dict[str, object] | None:
    liga_jogo = linha["league"]
    candidates = df_xg_liga["team_name"].tolist()
    time_casa = str(linha.get("home_team", "")).strip()
    time_fora = str(linha.get("away_team", "")).strip()

    xg_source = str(df_xg_liga["source"].iloc[0]) if "source" in df_xg_liga.columns and not df_xg_liga.empty else "footystats"
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
        alias_cache,
        league=liga_jogo,
        high_threshold=high_threshold,
        review_threshold=review_threshold,
        xg_source=xg_source,
        source_team_id_map=source_team_id_map,
    )
    away_match = match_team_name(
        time_fora,
        candidates,
        alias_cache,
        league=liga_jogo,
        high_threshold=high_threshold,
        review_threshold=review_threshold,
        xg_source=xg_source,
        source_team_id_map=source_team_id_map,
    )

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
                    registry_status="registry_pending" if res.match_status == "pending_review" else "registry_stale",
                    registry_reason="match_requires_registry_review" if res.match_status == "pending_review" else "unresolved_or_blocked_team_match",
                    registry_pending_key=f"{liga_jogo}|{res.source_name}",
                    recommended_action="sync_team_registry",
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
    return {
        "unique_pending_counts": unique_pending_counts,
        "unique_pending_by_league": unique_pending_by_league,
    }
