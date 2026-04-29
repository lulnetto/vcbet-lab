from __future__ import annotations

import csv
import os
from argparse import Namespace
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from vcbet.core.config_ligas import carregar_ligas
from vcbet.core.team_registry import (
    APPROVED_COLUMNS,
    DEFAULT_REGISTRY_FILE,
    DEFAULT_REVIEW_FILE,
    REVIEW_COLUMNS,
    RegistryAlias,
    is_valid_betano_team_identity,
    normalize_team_name,
    read_registry,
)
from vcbet.team_identity.sync_service import standings_url_for_league, sync_league


APPROVED_OUTPUT_COLUMNS = [
    *APPROVED_COLUMNS,
    "suggested_footystats_name",
    "top_score",
    "review_reason",
    "ambiguous_options",
    "status",
    "created_at",
    "updated_at",
]

PENDING_OPTIONAL_COLUMNS = []
REJECTED_REVIEW_FILE = DEFAULT_REVIEW_FILE.with_name("alias_review_rejected.csv")
QUARANTINE_REGISTRY_FILE = DEFAULT_REGISTRY_FILE.with_name("betano_footystats_aliases_quarantine.csv")
LOW_CONFIDENCE_THRESHOLD = 0.75


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _full_path(project_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()


def _read_csv(path: Path, fallback_columns: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], list(fallback_columns)
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        fieldnames = list(reader.fieldnames or fallback_columns)
        rows = []
        for row in reader:
            rows.append({str(k): "" if v is None else str(v) for k, v in row.items() if k is not None})
        return rows, fieldnames


def _write_csv_atomic(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    os.replace(tmp_path, path)


def _review_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        str(row.get("league", "")).strip(),
        str(row.get("betano_team_id", "")).strip(),
        normalize_team_name(str(row.get("betano_name", "")).strip()),
    )


def _matches_identity(row: dict[str, str], payload: dict[str, Any]) -> bool:
    league = str(payload.get("league", "") or "").strip()
    team_id = str(payload.get("betano_team_id", "") or "").strip()
    betano_name = str(payload.get("betano_name", "") or "").strip()
    if league and str(row.get("league", "")).strip() != league:
        return False
    if team_id and str(row.get("betano_team_id", "")).strip() == team_id:
        return True
    if betano_name and normalize_team_name(str(row.get("betano_name", ""))) == normalize_team_name(betano_name):
        return True
    return False


def _normalize_pending_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {name: str(row.get(name, "") or "") for name in [*REVIEW_COLUMNS, *PENDING_OPTIONAL_COLUMNS]}
    normalized["status"] = normalized.get("status") or "pending_review"
    normalized["source"] = normalized.get("source") or "sync_team_aliases"
    return normalized


def _normalize_approved_row(row: RegistryAlias) -> dict[str, str]:
    data = asdict(row)
    data.update({
        "suggested_footystats_name": row.footystats_name,
        "top_score": row.match_confidence,
        "review_reason": "",
        "ambiguous_options": "",
        "status": row.match_status,
        "created_at": row.approved_at,
        "updated_at": row.approved_at,
    })
    return data


def registry_row_warnings(row: dict[str, str]) -> list[str]:
    warnings: list[str] = []
    if not is_valid_betano_team_identity(row.get("betano_name", ""), row.get("betano_team_id", ""), row.get("betano_url", "")):
        warnings.append("identidade_betano_invalida")
    try:
        score = float(str(row.get("top_score") or row.get("match_confidence") or "1").replace(",", "."))
    except ValueError:
        score = 0.0
    if score < LOW_CONFIDENCE_THRESHOLD:
        warnings.append("score_baixo")
    status_blob = " ".join(str(row.get(key, "")) for key in ("status", "review_reason", "coverage_status", "source"))
    if any(token in status_blob for token in ("failed_partial_coverage", "standings_not_found_or_not_rendered", "blocked")):
        warnings.append("cobertura_parcial")
    return warnings


def cleanup_invalid_approved_registry(project_root: Path) -> dict[str, Any]:
    registry_path = _full_path(project_root, DEFAULT_REGISTRY_FILE)
    rows, fieldnames = _read_csv(registry_path, APPROVED_COLUMNS)
    if not rows:
        return {"removed": 0, "quarantine_file": str(QUARANTINE_REGISTRY_FILE)}
    valid: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []
    now = _now_str()
    for row in rows:
        if is_valid_betano_team_identity(row.get("betano_name", ""), row.get("betano_team_id", ""), row.get("betano_url", "")):
            valid.append(row)
        else:
            invalid.append({**row, "quarantine_reason": "invalid_betano_team_identity", "quarantined_at": now})
    if invalid:
        _write_csv_atomic(registry_path, valid, _approved_fieldnames(fieldnames))
        quarantine_path = _full_path(project_root, QUARANTINE_REGISTRY_FILE)
        existing, quarantine_fields = _read_csv(quarantine_path, [*APPROVED_COLUMNS, "quarantine_reason", "quarantined_at"])
        existing.extend(invalid)
        merged_fields = list(dict.fromkeys([*quarantine_fields, *APPROVED_COLUMNS, "quarantine_reason", "quarantined_at"]))
        _write_csv_atomic(quarantine_path, existing, merged_fields)
    return {"removed": len(invalid), "quarantine_file": str(QUARANTINE_REGISTRY_FILE)}


def load_pending_registry_reviews(project_root: Path) -> dict[str, Any]:
    path = _full_path(project_root, DEFAULT_REVIEW_FILE)
    rows, fieldnames = _read_csv(path, [*REVIEW_COLUMNS, *PENDING_OPTIONAL_COLUMNS])
    items = []
    for row in rows:
        if str(row.get("status", "pending_review")).lower() in {"rejected", "ignored", "approved"}:
            continue
        normalized = _normalize_pending_row(row)
        warnings = registry_row_warnings(normalized)
        normalized["validation_warnings"] = "|".join(warnings)
        normalized["approval_blocked"] = "true" if any(w in warnings for w in ("identidade_betano_invalida", "cobertura_parcial")) else "false"
        normalized["manual_override_required"] = "true" if "score_baixo" in warnings and normalized["approval_blocked"] != "true" else "false"
        items.append(normalized)
    by_league: dict[str, int] = {}
    for item in items:
        league = item.get("league") or "sem_liga"
        by_league[league] = by_league.get(league, 0) + 1
    return {
        "items": items,
        "total": len(items),
        "by_league": by_league,
        "file": str(DEFAULT_REVIEW_FILE),
        "exists": path.exists(),
        "fieldnames": fieldnames,
    }


def load_approved_registry_aliases(project_root: Path) -> dict[str, Any]:
    cleanup = cleanup_invalid_approved_registry(project_root)
    path = _full_path(project_root, DEFAULT_REGISTRY_FILE)
    items = [_normalize_approved_row(row) for row in read_registry(path)]
    by_league: dict[str, int] = {}
    for item in items:
        league = item.get("league") or "sem_liga"
        by_league[league] = by_league.get(league, 0) + 1
    return {
        "items": items,
        "total": len(items),
        "by_league": by_league,
        "file": str(DEFAULT_REGISTRY_FILE),
        "exists": path.exists(),
        "cleanup": cleanup,
    }


def _approved_duplicate(existing: list[RegistryAlias], row: dict[str, str]) -> bool:
    league = row.get("league", "")
    team_id = row.get("betano_team_id", "")
    betano_norm = normalize_team_name(row.get("betano_name", ""))
    for item in existing:
        if item.league != league:
            continue
        if team_id and item.betano_team_id and item.betano_team_id == team_id:
            return True
        if normalize_team_name(item.betano_name) == betano_norm:
            return True
    return False


def _pending_fieldnames(existing: list[str]) -> list[str]:
    merged = list(existing or [])
    for name in [*REVIEW_COLUMNS, *PENDING_OPTIONAL_COLUMNS]:
        if name not in merged:
            merged.append(name)
    return merged


def _approved_fieldnames(existing: list[str]) -> list[str]:
    merged = list(existing or [])
    for name in APPROVED_COLUMNS:
        if name not in merged:
            merged.append(name)
    return merged


def approve_registry_alias(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    review_path = _full_path(project_root, DEFAULT_REVIEW_FILE)
    registry_path = _full_path(project_root, DEFAULT_REGISTRY_FILE)
    pending_rows, pending_fields = _read_csv(review_path, [*REVIEW_COLUMNS, *PENDING_OPTIONAL_COLUMNS])
    approved_rows, approved_fields = _read_csv(registry_path, APPROVED_COLUMNS)
    existing = read_registry(registry_path)

    match = next((row for row in pending_rows if _matches_identity(row, payload)), None)
    base = dict(match or {})
    for key in ("league", "betano_name", "betano_team_id", "betano_url"):
        if payload.get(key) not in (None, ""):
            base[key] = str(payload.get(key) or "")

    footystats_name = str(
        payload.get("footystats_name")
        or payload.get("suggested_footystats_name")
        or base.get("suggested_footystats_name")
        or ""
    ).strip()
    if not base.get("league") or not base.get("betano_name") or not footystats_name:
        raise ValueError("league, betano_name e footystats_name são obrigatórios para aprovar alias.")
    if not match:
        for item in existing:
            item_payload = asdict(item)
            if _matches_identity(item_payload, base):
                return {
                    "added": 0,
                    "resolved_pending": 0,
                    "approved_file": str(DEFAULT_REGISTRY_FILE),
                    "pending_file": str(DEFAULT_REVIEW_FILE),
                    "alias": item_payload,
                }
    validation_base = {
        **base,
        "top_score": payload.get("top_score") or base.get("top_score") or payload.get("match_confidence") or "",
        "coverage_status": payload.get("coverage_status") or base.get("coverage_status") or "",
    }
    warnings = registry_row_warnings(validation_base)
    if "identidade_betano_invalida" in warnings:
        raise ValueError("alias rejeitado: identidade Betano inválida.")
    if "cobertura_parcial" in warnings:
        raise ValueError("alias rejeitado: linha veio de cobertura parcial/bloqueada.")
    if "score_baixo" in warnings and not (
        payload.get("manual_override") is True and str(payload.get("manual_override_reason") or "").strip()
    ):
        raise ValueError("alias de score baixo exige manual_override=true e manual_override_reason.")

    now = _now_str()
    fotmob_team_name = str(payload.get("fotmob_team_name") or base.get("fotmob_team_name") or "").strip()
    fotmob_team_id = str(payload.get("fotmob_team_id") or base.get("fotmob_team_id") or "").strip()
    fotmob_short_name = str(payload.get("fotmob_short_name") or base.get("fotmob_short_name") or "").strip()
    xg_provider_preferred = str(payload.get("xg_provider_preferred") or base.get("xg_provider_preferred") or "").strip()
    canonical_team_name = str(payload.get("canonical_team_name") or base.get("canonical_team_name") or fotmob_team_name or footystats_name or "").strip()

    approved_row = {
        "league": str(base.get("league", "")).strip(),
        "betano_name": str(base.get("betano_name", "")).strip(),
        "betano_team_id": str(base.get("betano_team_id", "")).strip(),
        "betano_url": str(base.get("betano_url", "")).strip(),
        "footystats_name": footystats_name,
        "match_status": "MATCH_REGISTRY_APPROVED",
        "match_confidence": str(payload.get("match_confidence") or base.get("top_score") or "1.0000"),
        "match_method": str(payload.get("match_method") or "registry_review"),
        "approved_at": now,
        "source": "ui_review",
        "fotmob_team_name": fotmob_team_name,
        "fotmob_team_id": fotmob_team_id,
        "fotmob_short_name": fotmob_short_name,
        "xg_provider_preferred": xg_provider_preferred,
        "canonical_team_name": canonical_team_name,
    }

    added = 0
    if not _approved_duplicate(existing, approved_row):
        approved_rows.append(approved_row)
        added = 1
        approved_rows.sort(key=lambda item: (item.get("league", ""), normalize_team_name(item.get("betano_name", ""))))
        _write_csv_atomic(registry_path, approved_rows, _approved_fieldnames(approved_fields))

    remaining: list[dict[str, str]] = []
    resolved = 0
    for row in pending_rows:
        if _matches_identity(row, approved_row):
            resolved += 1
            row = dict(row)
            row["status"] = "approved"
            row["updated_at"] = now
            continue
        remaining.append(row)
    if pending_rows or review_path.exists():
        _write_csv_atomic(review_path, remaining, _pending_fieldnames(pending_fields))

    return {
        "added": added,
        "resolved_pending": resolved,
        "approved_file": str(DEFAULT_REGISTRY_FILE),
        "pending_file": str(DEFAULT_REVIEW_FILE),
        "alias": approved_row,
    }


def reject_registry_alias(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    review_path = _full_path(project_root, DEFAULT_REVIEW_FILE)
    rejected_path = _full_path(project_root, REJECTED_REVIEW_FILE)
    rows, fieldnames = _read_csv(review_path, [*REVIEW_COLUMNS, *PENDING_OPTIONAL_COLUMNS])
    now = _now_str()
    remaining: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    for row in rows:
        if _matches_identity(row, payload):
            marked = dict(row)
            marked["status"] = str(payload.get("status") or "rejected")
            marked["updated_at"] = now
            marked["source"] = marked.get("source") or "ui_review"
            rejected.append(marked)
        else:
            remaining.append(row)

    if rows or review_path.exists():
        _write_csv_atomic(review_path, remaining, _pending_fieldnames(fieldnames))
    if rejected:
        rejected_rows, rejected_fields = _read_csv(rejected_path, _pending_fieldnames(fieldnames))
        rejected_rows.extend(rejected)
        _write_csv_atomic(rejected_path, rejected_rows, _pending_fieldnames(rejected_fields))

    return {"rejected": len(rejected), "remaining": len(remaining), "rejected_file": str(REJECTED_REVIEW_FILE)}


def update_registry_pending_alias(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    review_path = _full_path(project_root, DEFAULT_REVIEW_FILE)
    rows, fieldnames = _read_csv(review_path, [*REVIEW_COLUMNS, *PENDING_OPTIONAL_COLUMNS])
    if not rows:
        return {"updated": 0, "pending_file": str(DEFAULT_REVIEW_FILE)}
    allowed = set(REVIEW_COLUMNS) | set(PENDING_OPTIONAL_COLUMNS)
    changed = 0
    now = _now_str()
    for row in rows:
        if not _matches_identity(row, payload):
            continue
        for key, value in payload.items():
            if key in allowed and value is not None:
                row[key] = str(value)
        row["updated_at"] = now
        changed += 1
    _write_csv_atomic(review_path, rows, _pending_fieldnames(fieldnames))
    return {"updated": changed, "pending_file": str(DEFAULT_REVIEW_FILE)}


def list_registry_leagues(project_root: Path) -> dict[str, Any]:
    pending = load_pending_registry_reviews(project_root)
    approved = load_approved_registry_aliases(project_root)
    items = []
    for item in carregar_ligas():
        name = str(item.get("nome") or "")
        if not name or not item.get("betano_path") or not item.get("footystats_url"):
            continue
        pending_count = int(pending["by_league"].get(name, 0))
        approved_count = int(approved["by_league"].get(name, 0))
        items.append({
            "id": name,
            "name": name,
            "label": item.get("nome_exibicao") or name,
            "betano_url": standings_url_for_league(name) or "",
            "approved_count": approved_count,
            "pending_count": pending_count,
            "coverage_status": "pending_review" if pending_count else ("approved" if approved_count else "not_synced"),
        })
    return {"items": items, "total": len(items)}


def sync_registry_league(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    league = str(payload.get("league") or "").strip()
    if not league:
        raise ValueError("league é obrigatório.")
    source = str(payload.get("source") or "configured_url")
    html_path = str(payload.get("html_path") or "").strip()
    if source == "saved_html" and not html_path:
        raise ValueError("html_path é obrigatório quando source=saved_html.")
    args = Namespace(
        league=league,
        all=False,
        from_html=html_path if source == "saved_html" else None,
        url=None,
        xg_file=payload.get("xg_file"),
        dry_run=False,
        threshold=float(payload.get("threshold") or 0.94),
        margin=float(payload.get("margin") or 0.08),
        force_refresh_phase=bool(payload.get("force_refresh_phase") or False),
        debug_network=bool(payload.get("debug_network") or False),
        verbose=False,
        debug_output=False,
    )
    try:
        summary = sync_league(args, league, root=project_root)
    except Exception as exc:
        return {"status": "error", "league": league, "error": str(exc)}

    coverage = summary.get("coverage") or {}
    missing = len(coverage.get("footystats_without_betano_candidate") or []) + len(coverage.get("betano_without_footystats_candidate") or [])
    sync_status = str(summary.get("status") or "ok")
    coverage_status = str(summary.get("coverage_status") or ("pending_review" if int(summary.get("review_count") or 0) else ("incomplete" if missing else "ok")))
    return {
        "status": sync_status,
        "league": league,
        "phase_id": (summary.get("parse_diagnostics") or {}).get("phase_id", ""),
        "phase_title": (summary.get("parse_diagnostics") or {}).get("phase_title", ""),
        "debug_artifact": (summary.get("parse_diagnostics") or {}).get("debug_artifact", ""),
        "debug_reason": (summary.get("parse_diagnostics") or {}).get("error", ""),
        "betano_total": len(summary.get("betano_teams") or []),
        "footystats_total": len(summary.get("footystats_teams") or []),
        "auto_approved": int(summary.get("approved_count") or 0),
        "review_count": int(summary.get("review_count") or 0),
        "missing_count": missing,
        "coverage_status": coverage_status,
        "registry_added": int(summary.get("registry_added") or 0),
        "registry_total": int(summary.get("registry_total") or 0),
        "review_written": int(summary.get("review_written") or 0),
        "source": summary.get("source"),
    }


def sync_all_registry_leagues(project_root: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    results = []
    for item in list_registry_leagues(project_root).get("items", []):
        league = str(item.get("name") or item.get("id") or "")
        if not league:
            continue
        result = sync_registry_league(project_root, {
            "league": league,
            "source": "configured_url",
            "threshold": payload.get("threshold", 0.94),
            "margin": payload.get("margin", 0.08),
        })
        results.append(result)
    failed = [item for item in results if item.get("status") != "ok"]
    return {"status": "partial" if failed else "ok", "items": results, "failed": failed, "total": len(results)}
