from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from vcbet.service.dashboard import apply_filters, build_dashboard_payload, load_ledger

from . import RouteContext


def register_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/dashboard/summary")
    def dashboard_summary(
        ledger_file: str = Query("data/history/bets_ledger.csv"),
        run_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        league: str | None = None,
        market_type: str | None = None,
        only_executed: bool = False,
        only_settled: bool = False,
    ):
        try:
            df = load_ledger(ctx.resolve_project_path(ledger_file))
            filtered = apply_filters(
                df,
                run_id=run_id,
                date_from=date_from,
                date_to=date_to,
                league=league,
                market_type=market_type,
                only_executed=only_executed,
                only_settled=only_settled,
            )
            payload = build_dashboard_payload(filtered)
            payload["applied_filters"] = {
                "ledger_file": ledger_file,
                "run_id": run_id,
                "date_from": date_from,
                "date_to": date_to,
                "league": league,
                "market_type": market_type,
                "only_executed": only_executed,
                "only_settled": only_settled,
            }
            return payload
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"erro ao montar dashboard: {exc}")

    @app.get("/dashboard/entries")
    def dashboard_entries(
        ledger_file: str = Query("data/history/bets_ledger.csv"),
        run_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        league: str | None = None,
        market_type: str | None = None,
        only_executed: bool = False,
        only_settled: bool = False,
        limit: int = 100,
    ):
        try:
            df = load_ledger(ctx.resolve_project_path(ledger_file))
            filtered = apply_filters(
                df,
                run_id=run_id,
                date_from=date_from,
                date_to=date_to,
                league=league,
                market_type=market_type,
                only_executed=only_executed,
                only_settled=only_settled,
            )
            payload = build_dashboard_payload(filtered, entries_limit=limit)
            return {
                "items": payload["entries"],
                "total_filtered": int(len(filtered)),
                "limit": limit,
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"erro ao listar entradas: {exc}")
