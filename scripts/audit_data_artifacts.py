#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from data_catalog_utils import first_value, infer_mode, project_root, read_json, relpath


REPORT_PATH = Path("data/artifact_inventory_report.md")
TARGET_ROOTS = [
    Path("data/runs"),
    Path("data/replays"),
    Path("data/history"),
    Path("data/results"),
    Path("data/service/jobs"),
    Path("data/service/logs"),
]
PROTECTED = {
    "data/history/bets_ledger.csv",
    "data/runs/catalog.jsonl",
    "data/replays/catalog.jsonl",
}


@dataclass(frozen=True)
class Artifact:
    path: str
    kind: str
    classification: str
    mode: str
    reason: str


def date_from_parts(path: Path) -> str | None:
    for part in path.parts:
        if len(part) == 10 and part[4] == "-" and part[7] == "-":
            return part
    return None


def classify_history_file(path: Path) -> tuple[str, str, str]:
    rel = path.as_posix()
    name = path.name.lower()
    if rel == "data/history/bets_ledger.csv":
        return "keep", "official", "canonical official ledger"
    if "test" in name:
        return "archive", "sandbox", "sandbox ledger artifact"
    if "rerun" in name:
        return "archive", "sandbox", "rerun ledger artifact"
    if name.endswith(".bak"):
        return "review", "legacy/dev artifact", "ledger backup needs owner review"
    if "ledger" in name:
        return "review", "unknown", "ledger-like file outside canonical official path"
    return "review", "unknown", "history file requires review"


def classify_run_dir(path: Path) -> tuple[str, str, str]:
    manifest, status = read_json(path / "run_manifest.json")
    mode = infer_mode(path, manifest)
    rel = path.as_posix().lower()
    day = date_from_parts(path)
    ledger = str(first_value(manifest, "ledger_file") or "").lower()
    if "bets_ledger.csv" in ledger and "ch_bets_ledger" not in ledger and "rerun" not in rel:
        return "keep", "official", "run linked to canonical official ledger"
    if "rerun" in rel:
        return "archive", "sandbox", "rerun development run"
    if day and day < "2026-04-24":
        return "archive", mode, "older development run retained as archive candidate"
    if status != "ok":
        return "review", mode, f"manifest {status}"
    return "keep", mode, "recent run artifact"


def classify_replay_dir(path: Path) -> tuple[str, str, str]:
    manifest, status = read_json(path / "run_manifest.json")
    day = date_from_parts(path)
    if path.name.startswith("comparison_"):
        mode = "replay"
        if day and day < "2026-04-24":
            return "archive", mode, "older replay comparison summary"
        return "keep", mode, "recent replay comparison summary"
    mode = infer_mode(path, manifest, is_replay=True)
    if day and day < "2026-04-24":
        return "archive", mode, "older replay artifact retained as archive candidate"
    if status != "ok":
        return "review", mode, f"manifest {status}"
    return "keep", mode, "recent replay artifact"


def classify_results_file(path: Path) -> tuple[str, str, str]:
    lower = path.as_posix().lower()
    if "/_debug/" in lower:
        return "delete_candidate", "debug", "debug collector output"
    if path.name in {"results_auto.csv", "results_overrides.csv", "ch_results_auto.csv"}:
        return "review", "unknown", "results file may be needed for settlement"
    return "review", "unknown", "results artifact requires review"


def classify_service_file(path: Path) -> tuple[str, str, str]:
    try:
        size = path.stat().st_size
    except OSError:
        size = -1
    if size == 0:
        return "delete_candidate", "debug", "empty service artifact"
    return "archive", "debug", "stale service job/log runtime artifact"


def inventory(root: Path) -> list[Artifact]:
    artifacts: list[Artifact] = []
    data_root = root / "data"
    if not data_root.exists():
        return artifacts

    for run_dir in sorted((root / "data" / "runs").glob("*/*")):
        if run_dir.is_dir():
            cls, mode, reason = classify_run_dir(run_dir)
            artifacts.append(Artifact(relpath(run_dir, root), "run_dir", cls, mode, reason))

    for replay_dir in sorted((root / "data" / "replays").glob("*/*")):
        if replay_dir.is_dir():
            cls, mode, reason = classify_replay_dir(replay_dir)
            artifacts.append(Artifact(relpath(replay_dir, root), "replay_dir", cls, mode, reason))

    for file_path in sorted((root / "data" / "history").glob("*")):
        if file_path.is_file():
            cls, mode, reason = classify_history_file(Path(relpath(file_path, root)))
            artifacts.append(Artifact(relpath(file_path, root), "ledger_file", cls, mode, reason))

    for file_path in sorted((root / "data" / "results").glob("**/*")):
        if file_path.is_file():
            cls, mode, reason = classify_results_file(file_path)
            artifacts.append(Artifact(relpath(file_path, root), "result_file", cls, mode, reason))

    for rel_root in ("data/service/jobs", "data/service/logs"):
        for file_path in sorted((root / rel_root).glob("*")):
            if file_path.is_file() and file_path.name != ".gitkeep":
                cls, mode, reason = classify_service_file(file_path)
                artifacts.append(Artifact(relpath(file_path, root), "service_artifact", cls, mode, reason))

    for rel in sorted(PROTECTED):
        path = root / rel
        if path.exists() and rel not in {item.path for item in artifacts}:
            artifacts.append(Artifact(rel, "protected_file", "keep", "catalog" if "catalog" in rel else "official", "protected governance artifact"))

    return artifacts


def write_report(root: Path, artifacts: list[Artifact]) -> Path:
    counts = Counter(item.classification for item in artifacts)
    by_kind = Counter(item.kind for item in artifacts)
    grouped: dict[str, list[Artifact]] = defaultdict(list)
    for item in artifacts:
        grouped[item.classification].append(item)

    lines = [
        "# Data Artifact Inventory",
        "",
        "Generated by `python3 scripts/audit_data_artifacts.py`.",
        "",
        "## Scope",
        "",
    ]
    lines.extend(f"- `{path.as_posix()}/`" for path in TARGET_ROOTS)
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Classification | Count |",
            "| --- | ---: |",
        ]
    )
    for name in ("keep", "archive", "delete_candidate", "review"):
        lines.append(f"| {name} | {counts.get(name, 0)} |")
    lines.extend(["", "| Kind | Count |", "| --- | ---: |"])
    for kind, count in sorted(by_kind.items()):
        lines.append(f"| {kind} | {count} |")

    for name in ("keep", "archive", "delete_candidate", "review"):
        lines.extend(["", f"## {name}", "", "| Path | Kind | Mode | Reason |", "| --- | --- | --- | --- |"])
        for item in grouped.get(name, []):
            lines.append(f"| `{item.path}` | {item.kind} | {item.mode} | {item.reason} |")

    output = root / REPORT_PATH
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def main() -> int:
    root = project_root()
    artifacts = inventory(root)
    output = write_report(root, artifacts)
    print(f"wrote {len(artifacts)} artifact records to {relpath(output, root)}")
    print(json.dumps(Counter(item.classification for item in artifacts), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
