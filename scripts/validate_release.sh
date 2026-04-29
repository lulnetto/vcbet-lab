#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_BIN="${CONDA_BIN:-/home/otten/miniforge3/bin/conda}"
CONDA_ENV="${CONDA_ENV:-ubet}"
GATE_TMP="$(mktemp -d)"
trap 'rm -rf "$GATE_TMP"' EXIT

run_python() {
  "$CONDA_BIN" run -n "$CONDA_ENV" python "$@"
}

cd "$PROJECT_ROOT"

echo "[gate] VCBet minimal release gate"
echo "[gate] project: $PROJECT_ROOT"
echo "[gate] env:     $CONDA_ENV via $CONDA_BIN"

echo "[gate] 1/5 structural regression tests"
run_python -m unittest \
  tests.test_data_health \
  tests.test_odds_collector \
  tests.test_fotmob_xg_collector \
  tests.test_footystats_xg_collector \
  tests.test_service_composed_workflows

echo "[gate] 2/6 operational entrypoint smoke"
bash run_project.sh --help >/dev/null
fake_python="$GATE_TMP/fake_python.sh"
fake_output_dir="$GATE_TMP/runs"
fake_args_log="$GATE_TMP/pipeline_args.txt"
cat > "$fake_python" <<SH
#!/usr/bin/env bash
set -euo pipefail
if [[ "\$1" == "-" ]]; then
  printf 'Liga Smoke\n'
  exit 0
fi
module="\$2"
case "\$module" in
  vcbet.collectors.odds_collector)
    mkdir -p "$fake_output_dir/2026-04-24/run_release_gate"
    printf 'league;home;away\nLiga Smoke;A;B\n' > "$fake_output_dir/2026-04-24/run_release_gate/odds_snapshot.csv"
    ;;
  vcbet.collectors.xg_daily_store)
    mkdir -p "$fake_output_dir/2026-04-24/run_release_gate"
    printf 'team,xg\nA,1.0\n' > "$fake_output_dir/2026-04-24/run_release_gate/xg_snapshot.csv"
    ;;
  vcbet.core.pipeline_ev)
    printf '%s\n' "\$@" > "$fake_args_log"
    ;;
  *)
    echo "unexpected module: \$module" >&2
    exit 2
    ;;
esac
SH
chmod +x "$fake_python"
bash run_project.sh \
  --mode full \
  --date 2026-04-24 \
  --run-id run_release_gate \
  --output-dir "$fake_output_dir" \
  --ledger-file "$GATE_TMP/ledger.csv" \
  --python-bin "$fake_python" \
  --config-name legacy_v2 >/dev/null
grep -q -- "--config-name" "$fake_args_log"
grep -q -- "legacy_v2" "$fake_args_log"

echo "[gate] 3/6 config and project guidance smoke"
run_python - <<'PY'
from pathlib import Path
import json

root = Path.cwd()
for path in sorted((root / "configs").glob("*.json")) + [root / "ligas.json"]:
    with path.open("r", encoding="utf-8") as fh:
        json.load(fh)
print("json_ok")
PY

echo "[gate] 4/6 service/command import smoke"
VCBET_SERVICE_JOBS_DIR="$GATE_TMP/jobs" VCBET_SERVICE_LOGS_DIR="$GATE_TMP/logs" run_python - <<'PY'
from pathlib import Path

from vcbet.service.api import app
from vcbet.service.commands import build_daily_commands
from vcbet.service.schemas import DailyRunRequest

commands = build_daily_commands(
    Path.cwd(),
    DailyRunRequest(
        config_name="legacy_v2",
        skip_closing_odds=True,
        skip_results_collection=True,
        skip_settlement=True,
    ),
)
assert commands and "--config-name" in commands[0].command
assert len(app.routes) > 0
print("service_ok")
PY

echo "[gate] 5/6 web UI runtime smoke"
bash scripts/smoke_ui.sh

echo "[gate] 6/6 data catalog freshness smoke"
run_python scripts/build_run_catalog.py
run_python scripts/build_replay_catalog.py
run_python - <<'PY'
import json
from pathlib import Path

for rel in ("data/runs/catalog.jsonl", "data/replays/catalog.jsonl"):
    path = Path(rel)
    assert path.exists(), f"missing catalog: {rel}"
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                json.loads(line)
print("catalogs_ok")
PY

echo "[gate] PASS"
