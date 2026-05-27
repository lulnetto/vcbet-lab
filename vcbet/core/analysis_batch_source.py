from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable

from vcbet.core.run_utils import build_manifest, save_manifest, update_manifest


SOURCE_SNAPSHOT_FILES = ("odds_snapshot.csv", "xg_snapshot.csv")


def _has_source_snapshots(run_dir: Path) -> bool:
    return all((run_dir / name).exists() for name in SOURCE_SNAPSHOT_FILES)


def _snapshot_mtime(run_dir: Path) -> float:
    mtimes = []
    for name in SOURCE_SNAPSHOT_FILES:
        try:
            mtimes.append((run_dir / name).stat().st_mtime)
        except OSError:
            pass
    return max(mtimes, default=0.0)


def find_reusable_source(output_dir: Path, run_date: str, source_dir: Path) -> Path | None:
    if _has_source_snapshots(source_dir):
        return source_dir
    day_dir = output_dir / run_date
    if not day_dir.exists():
        return None
    candidates = [
        candidate
        for candidate in day_dir.iterdir()
        if candidate.is_dir() and candidate != source_dir and _has_source_snapshots(candidate)
    ]
    if not candidates:
        return None
    candidates.sort(key=_snapshot_mtime, reverse=True)
    return candidates[0]


def copy_source_artifacts(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in SOURCE_SNAPSHOT_FILES:
        shutil.copy2(source / name, target / name)
    for optional_name in (
        "odds_collection_manifest.json",
        "odds_snapshot.json",
        "pre_snapshot_discards.csv",
    ):
        optional_source = source / optional_name
        if optional_source.exists():
            shutil.copy2(optional_source, target / optional_name)


def _read_active_leagues(odds_snapshot: Path) -> list[str]:
    if not odds_snapshot.exists():
        return []
    with odds_snapshot.open("r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=delimiter)
        leagues: list[str] = []
        seen: set[str] = set()
        for row in reader:
            league = str(row.get("league") or row.get("Liga") or "").strip()
            if league and league not in seen:
                seen.add(league)
                leagues.append(league)
        return leagues


def _run(command: list[str], cwd: Path) -> None:
    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _daily_xg_snapshot_path(project_root: Path) -> Path:
    snapshot_date = datetime.now().strftime("%Y-%m-%d")
    return project_root / "data" / "xg" / snapshot_date / "xg_snapshot.csv"


def collect_source_artifacts(
    *,
    project_root: Path,
    output_dir: Path,
    run_date: str,
    source_snapshot_id: str,
    python_bin: str,
    json_output: bool,
    xg_source: str,
) -> Path:
    source_dir = output_dir / run_date / source_snapshot_id
    source_dir.mkdir(parents=True, exist_ok=True)

    odds_command = [
        python_bin,
        "-m",
        "vcbet.collectors.odds_collector",
        "--run-id", source_snapshot_id,
        "--d", run_date,
        "--output-dir", str(output_dir),
    ]
    if json_output:
        odds_command.append("--json")
    _run(odds_command, project_root)

    odds_snapshot = source_dir / "odds_snapshot.csv"
    if not odds_snapshot.exists():
        raise FileNotFoundError(f"odds_snapshot.csv nao foi gerado em {source_dir}")

    active_leagues = _read_active_leagues(odds_snapshot)
    if not active_leagues:
        update_manifest(
            source_dir,
            status="batch_source_empty",
            run_group_source_status="empty_odds",
            run_group_source_message="Nenhuma liga ativa encontrada no snapshot de odds.",
        )
        raise RuntimeError("Nenhuma liga ativa encontrada no snapshot de odds.")

    xg_command = [
        python_bin,
        "-m",
        "vcbet.collectors.xg_daily_store",
        "--date", run_date,
        "--source", xg_source,
    ]
    _run(xg_command, project_root)
    daily_xg = _daily_xg_snapshot_path(project_root)
    if not daily_xg.exists():
        raise FileNotFoundError(f"xg_snapshot.csv diario nao encontrado: {daily_xg}")
    shutil.copy2(daily_xg, source_dir / "xg_snapshot.csv")
    return source_dir


def prepare_batch_source(
    *,
    project_root: Path,
    run_date: str,
    run_group_id: str,
    source_snapshot_id: str,
    output_dir: Path,
    reuse_snapshot: bool,
    python_bin: str,
    json_output: bool,
    xg_source: str,
) -> Path:
    source_dir = output_dir / run_date / source_snapshot_id
    source_dir.mkdir(parents=True, exist_ok=True)
    save_manifest(
        source_dir,
        build_manifest(
            run_id=source_snapshot_id,
            target_date=run_date,
            run_dir=source_dir,
            status="batch_source_initialized",
            run_group_id=run_group_id,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_ref=f"odds:{source_dir / 'odds_snapshot.csv'}|xg:{source_dir / 'xg_snapshot.csv'}",
            run_mode="analysis_batch_source",
        ),
    )

    reused_from = find_reusable_source(output_dir, run_date, source_dir) if reuse_snapshot else None
    if reused_from is not None:
        if reused_from != source_dir:
            copy_source_artifacts(reused_from, source_dir)
        update_manifest(
            source_dir,
            status="batch_source_reused",
            run_group_id=run_group_id,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_ref=f"odds:{source_dir / 'odds_snapshot.csv'}|xg:{source_dir / 'xg_snapshot.csv'}",
            reused_from=str(reused_from),
        )
        print(f"[BATCH] Source snapshot reutilizado: {reused_from}")
        return source_dir

    collected = collect_source_artifacts(
        project_root=project_root,
        output_dir=output_dir,
        run_date=run_date,
        source_snapshot_id=source_snapshot_id,
        python_bin=python_bin,
        json_output=json_output,
        xg_source=xg_source,
    )
    update_manifest(
        collected,
        status="batch_source_collected",
        run_group_id=run_group_id,
        source_snapshot_id=source_snapshot_id,
        source_snapshot_ref=f"odds:{collected / 'odds_snapshot.csv'}|xg:{collected / 'xg_snapshot.csv'}",
    )
    print(f"[BATCH] Source snapshot preparado: {collected}")
    return collected


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepara source snapshot unico para batch de perfis")
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--run-group-id", required=True)
    parser.add_argument("--source-snapshot-id", required=True)
    parser.add_argument("--output-dir", default="data/runs")
    parser.add_argument("--python-bin", default="python3")
    parser.add_argument("--xg-source", default="fotmob")
    parser.add_argument("--reuse-snapshot", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    project_root = Path.cwd().resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = (project_root / output_dir).resolve()
    prepare_batch_source(
        project_root=project_root,
        run_date=args.run_date,
        run_group_id=args.run_group_id,
        source_snapshot_id=args.source_snapshot_id,
        output_dir=output_dir,
        reuse_snapshot=args.reuse_snapshot,
        python_bin=args.python_bin,
        json_output=args.json,
        xg_source=args.xg_source,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
