# Frontend Map

The frontend is a static UI served by the VCBet service from `vcbet/service/static/`.

It uses classic global scripts, not ES modules. Preserve global functions referenced by inline handlers in `index.html`.

## Files

- `index.html`: application shell, screen containers, tabs, forms, and script/style includes.
- `css/tokens.css`: design tokens such as colors, spacing, typography, shadows, and shared variables.
- `css/layout.css`: page layout, navigation, tab structure, cockpit layout, grids, and responsive screen structure.
- `css/components.css`: cards, buttons, badges, forms, drawers, empty states, alerts, and reusable visual components.
- `css/tables.css`: table layout, wrappers, row states, and dense data presentation.
- `js/api.js`: API wrapper functions used by screens and actions.
- `js/state.js`: shared frontend state, cache, selected tabs, and cross-screen data.
- `js/components.js`: reusable render helpers, formatting helpers, badges, table rendering, drawer rendering, and common UI fragments.
- `js/screens.js`: screen-specific load and render logic for Hoje, Carteira, Replay Lab, Qualidade de Dados, and Monitor.
- `js/app.js`: application bootstrap, navigation wiring, initial loads, and global event setup.

## Entity Selectors

The normal UI uses selectors for operational dates, configs, ledgers, runs, and replays. The selectors are populated from read-only service endpoints and generated local catalogs when they exist. Manual text/path fields stay under `Avançado` so existing backend command payloads continue to receive the same strings.

If `data/runs/catalog.jsonl` or `data/replays/catalog.jsonl` is missing, selector empty states should explain that the catalogs can be regenerated with `scripts/build_run_catalog.py` and `scripts/build_replay_catalog.py`.

## Development Rules

- Keep the frontend framework-free for now.
- Keep scripts as classic global scripts unless a deliberate migration is planned.
- Preserve global functions used by inline `onclick` handlers.
- Prefer adding reusable UI helpers to `js/components.js`.
- Prefer adding screen-specific behavior to `js/screens.js`.
- Prefer styling through existing CSS classes and the split CSS files.
- Avoid putting new behavior back into `index.html` unless it is structural shell markup.
- Do not change API contracts from frontend work unless the backend change is part of the same planned task.

## Screen Ownership

- Hoje: operational cockpit and daily workflow context.
- Carteira: ledger/picks/portfolio review.
- Replay Lab: replay and config comparison workflow.
- Qualidade de Dados: aliases and data-quality issue review.
- Monitor: jobs, logs, and observability.
