#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

from audit_data_artifacts import PROTECTED, inventory
from data_catalog_utils import project_root, relpath


ARCHIVE_ROOT = Path("data/_archive/pre_cycle7_cleanup")


@dataclass(frozen=True)
class Action:
    operation: str
    source: str
    destination: str | None
    reason: str


def is_inside_data(rel: str) -> bool:
    return rel == "data" or rel.startswith("data/")


def selected_actions(root: Path, *, delete: bool) -> list[Action]:
    actions: list[Action] = []
    for item in inventory(root):
        if item.path in PROTECTED:
            continue
        if not is_inside_data(item.path):
            continue
        source = root / item.path
        if not source.exists():
            continue
        if item.classification == "archive":
            destination = ARCHIVE_ROOT / item.path
            actions.append(Action("archive", item.path, destination.as_posix(), item.reason))
        elif item.classification == "delete_candidate":
            if delete:
                actions.append(Action("delete", item.path, None, item.reason))
            else:
                destination = ARCHIVE_ROOT / item.path
                actions.append(Action("archive", item.path, destination.as_posix(), item.reason))
    return actions


def assert_safe(root: Path, action: Action) -> None:
    source = (root / action.source).resolve()
    data_root = (root / "data").resolve()
    if data_root not in source.parents and source != data_root:
        raise RuntimeError(f"refusing to touch path outside data/: {action.source}")
    if action.source in PROTECTED:
        raise RuntimeError(f"refusing to touch protected path: {action.source}")
    if action.destination:
        dest = (root / action.destination).resolve()
        archive_root = (root / ARCHIVE_ROOT).resolve()
        if archive_root not in dest.parents and dest != archive_root:
            raise RuntimeError(f"refusing archive destination outside archive root: {action.destination}")


def apply_action(root: Path, action: Action) -> None:
    assert_safe(root, action)
    source = root / action.source
    if action.operation == "archive":
        if action.destination is None:
            raise RuntimeError("archive action missing destination")
        destination = root / action.destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise RuntimeError(f"archive destination already exists: {action.destination}")
        shutil.move(str(source), str(destination))
    elif action.operation == "delete":
        if source.is_dir():
            shutil.rmtree(source)
        else:
            source.unlink()
    else:
        raise RuntimeError(f"unknown operation: {action.operation}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or archive obsolete VCBet data artifacts.")
    parser.add_argument("--apply", action="store_true", help="perform planned archive/delete actions")
    parser.add_argument("--delete", action="store_true", help="hard-delete delete_candidate artifacts instead of archiving them")
    args = parser.parse_args()

    root = project_root()
    actions = selected_actions(root, delete=args.delete)
    mode = "APPLY" if args.apply else "DRY-RUN"
    delete_note = " with hard delete enabled" if args.delete else " archive-only"
    print(f"{mode}:{delete_note}")
    if not actions:
        print("no cleanup actions planned")
        return 0

    for action in actions:
        if action.destination:
            print(f"{action.operation}: {action.source} -> {action.destination} ({action.reason})")
        else:
            print(f"{action.operation}: {action.source} ({action.reason})")

    if not args.apply:
        print("dry-run only; no files moved or deleted")
        return 0

    for action in actions:
        apply_action(root, action)
    print(f"applied {len(actions)} cleanup actions")
    print(f"archive root: {relpath(root / ARCHIVE_ROOT, root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
