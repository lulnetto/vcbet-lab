# Frontend UI Context Pack

## Purpose

Work on the static operator UI: screens, state, API calls, tables, styling, and workflows for runs, jobs, dashboard, replay, aliases, and team registry.

## Include by Default

- `vcbet/service/static/index.html`
- `vcbet/service/static/css/tokens.css`
- `vcbet/service/static/css/layout.css`
- `vcbet/service/static/css/components.css`
- `vcbet/service/static/css/tables.css`
- `vcbet/service/static/js/api.js`
- `vcbet/service/static/js/app.js`
- `vcbet/service/static/js/components.js`
- `vcbet/service/static/js/screens.js`
- `vcbet/service/static/js/state.js`

## Include Only If Needed

- `vcbet/service/api.py` when route payloads or endpoint names change.
- `vcbet/service/schemas.py` when API request/response contracts change.
- `vcbet/service/team_registry_api.py` for team registry workflow changes.
- `docs/FRONTEND_MAP.md` for existing UI map context.
- `scripts/smoke_ui.sh` for manual smoke-test expectations.

## Exclude

- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs, replays, and results
- full ledgers

## Key Invariants

- Static UI must continue to work against the existing FastAPI routes.
- Dashboard, jobs, replay, alias review, and team registry workflows must preserve operator actions and state transitions.
- Route payload shape changes require coordinated service and frontend updates in the same task.
- UI files should not embed business rules that belong to domain or application layers.

## Validation Commands

- No narrow automated frontend test currently exists.
- Closest available after starting the service: `bash scripts/smoke_ui.sh`
- For API shape changes, also run the relevant service tests from `context_packs/service_api.md`.

## Known Hotspots

- `vcbet/service/static/js/screens.js` is roughly 967 LOC and mixes all screen renderers, workflow actions, and state updates.
- `vcbet/service/static/js/components.js` is also large enough to review carefully when table or display helpers change.

## Refactor Direction

Split screen modules by workflow and keep shared rendering helpers small. Treat the API layer as the boundary and avoid duplicating backend policy decisions in browser code.
