from __future__ import annotations

from fastapi import FastAPI

from vcbet.service.schemas import AliasApproveRequest

from . import RouteContext


def register_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/aliases/files")
    def list_alias_files(include_blocked: bool = True, scope: str = "runs_recent", include_resolved: bool = False):
        items = []
        approved_keys = ctx.registry_approved_keys()
        for file_path in ctx.alias_candidate_files(scope=scope):
            payload = ctx.alias_file_payload(
                file_path,
                include_blocked=include_blocked,
                cleanup_empty=True,
                include_resolved=include_resolved,
                approved_keys=approved_keys,
            )
            if not payload:
                continue
            if not include_resolved and int(payload.get("total") or 0) == 0:
                continue
            items.append({
                "pending_file": payload["pending_file"],
                "status_counts": payload["status_counts"],
                "total": payload["total"],
            })
        items.sort(key=lambda item: item["pending_file"], reverse=True)
        return {"items": items}

    @app.get("/aliases/review")
    def get_alias_review(pending_file: str, include_blocked: bool = True, include_resolved: bool = False):
        pending_path = ctx.resolve_project_path(pending_file)
        payload = ctx.alias_file_payload(
            pending_path,
            include_blocked=include_blocked,
            cleanup_empty=False,
            include_resolved=include_resolved,
            approved_keys=ctx.registry_approved_keys(),
        )
        if not payload:
            return {
                "pending_file": pending_file,
                "status_counts": {"pending_review": 0, "blocked": 0},
                "items": [],
                "total": 0,
                "message": "sem aliases pendentes",
            }
        return payload

    @app.post("/aliases/approve")
    def approve_aliases(req: AliasApproveRequest):
        pending_path = ctx.resolve_project_path(req.pending_file)
        rows, delimiter, fieldnames = ctx.read_text_csv(pending_path)
        if not rows:
            if pending_path.exists():
                pending_path.unlink()
            return {"saved": 0, "remaining": 0, "deleted_pending_file": True}

        normalized = ctx.normalize_alias_rows(rows)
        approvals_by_id = {item.row_id: item for item in req.approvals}

        remaining: list[dict[str, str]] = []
        saved = 0
        for row in normalized:
            approval = approvals_by_id.get(row["row_id"])
            if approval:
                saved += 1
                continue
            remaining_row = {k: v for k, v in row.items() if k != "row_id"}
            remaining.append(remaining_row)

        still_visible = [
            row for row in remaining
            if row.get("match_status") == "pending_review" or (req.include_blocked and row.get("match_status") == "blocked")
        ]
        deleted = not still_visible
        ctx.write_text_csv(pending_path, remaining if still_visible else [], fieldnames, delimiter)

        return {
            "saved": saved,
            "remaining": len(still_visible),
            "deleted_pending_file": deleted,
        }
