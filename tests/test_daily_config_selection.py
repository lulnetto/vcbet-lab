from __future__ import annotations

import subprocess
from pathlib import Path

from vcbet.service.commands import build_daily_commands
from vcbet.service.schemas import DailyRunRequest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_daily_command_includes_selected_config_name() -> None:
    for config_name in ("legacy_v2", "champion_strict"):
        commands = build_daily_commands(
            PROJECT_ROOT,
            DailyRunRequest(
                config_name=config_name,
                skip_closing_odds=True,
                skip_results_collection=True,
                skip_settlement=True,
            ),
        )

        assert len(commands) == 1
        assert "--config-name" in commands[0].command
        assert commands[0].command[commands[0].command.index("--config-name") + 1] == config_name


def test_run_project_full_mode_forwards_config_name_to_pipeline(tmp_path: Path) -> None:
    for config_name in ("legacy_v2", "champion_strict"):
        run_id = f"run_config_smoke_{config_name}"
        output_dir = tmp_path / config_name / "runs"
        ledger_file = tmp_path / config_name / "ledger.csv"
        python_bin = tmp_path / config_name / "fake_python.sh"
        args_log = tmp_path / config_name / "pipeline_args.txt"
        python_bin.parent.mkdir(parents=True, exist_ok=True)
        python_bin.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "-" ]]; then
  printf 'Liga Smoke\\n'
  exit 0
fi
module="$2"
case "$module" in
  vcbet.collectors.odds_collector)
    mkdir -p "{output_dir}/2026-04-24/{run_id}"
    printf 'league;home;away\\nLiga Smoke;A;B\\n' > "{output_dir}/2026-04-24/{run_id}/odds_snapshot.csv"
    ;;
  vcbet.collectors.footystats_xg_collector)
    mkdir -p "{output_dir}/2026-04-24/{run_id}"
    printf 'team,xg\\nA,1.0\\n' > "{output_dir}/2026-04-24/{run_id}/xg_snapshot.csv"
    ;;
  vcbet.core.pipeline_ev)
    printf '%s\\n' "$@" > "{args_log}"
    ;;
  *)
    echo "unexpected module: $module" >&2
    exit 2
    ;;
esac
""",
            encoding="utf-8",
        )
        python_bin.chmod(0o755)

        subprocess.run(
            [
                "bash",
                str(PROJECT_ROOT / "run_project.sh"),
                "--mode",
                "full",
                "--date",
                "2026-04-24",
                "--run-id",
                run_id,
                "--output-dir",
                str(output_dir),
                "--ledger-file",
                str(ledger_file),
                "--python-bin",
                str(python_bin),
                "--config-name",
                config_name,
            ],
            cwd=PROJECT_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        pipeline_args = args_log.read_text(encoding="utf-8").splitlines()
        assert "--config-name" in pipeline_args
        assert pipeline_args[pipeline_args.index("--config-name") + 1] == config_name
