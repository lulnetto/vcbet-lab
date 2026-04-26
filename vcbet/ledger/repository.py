from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd

from vcbet.ledger.schema import LEDGER_COLUMNS, normalize_ledger_schema
from vcbet.paths import DEFAULT_LEDGER_FILE


try:
    import fcntl
except ImportError:  # pragma: no cover - VCBet runtime is WSL/Linux.
    fcntl = None

T = TypeVar("T")


def _ledger_lock_path(ledger_file: str | Path) -> Path:
    path = Path(ledger_file)
    return path.with_name(f"{path.name}.lock")


@contextmanager
def ledger_file_lock(ledger_file: str | Path):
    path = Path(ledger_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _ledger_lock_path(path)
    if fcntl is None:
        try:
            from filelock import FileLock
        except ImportError as exc:  # pragma: no cover - defensive fallback.
            raise RuntimeError("Ledger file locking requires fcntl or filelock") from exc
        with FileLock(str(lock_path)):
            yield
        return

    with lock_path.open("a", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _fsync_directory(path: Path) -> None:
    try:
        dir_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def write_ledger_csv_unlocked(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            encoding="utf-8-sig",
            newline="",
        ) as tmp:
            tmp_name = tmp.name
            df.to_csv(tmp, index=False, sep=";")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
        _fsync_directory(path.parent)
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except FileNotFoundError:
                pass


def ensure_ledger_unlocked(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> Path:
    path = Path(ledger_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_ledger_csv_unlocked(pd.DataFrame(columns=LEDGER_COLUMNS), path)
    return path


def load_ledger_unlocked(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> pd.DataFrame:
    path = ensure_ledger_unlocked(ledger_file)
    df = pd.read_csv(path, sep=";")
    return normalize_ledger_schema(df)


def save_ledger_unlocked(df: pd.DataFrame, ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> Path:
    path = ensure_ledger_unlocked(ledger_file)
    write_ledger_csv_unlocked(normalize_ledger_schema(df), path)
    return path


def ensure_ledger(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> Path:
    with ledger_file_lock(ledger_file):
        return ensure_ledger_unlocked(ledger_file)


def load_ledger(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> pd.DataFrame:
    with ledger_file_lock(ledger_file):
        return load_ledger_unlocked(ledger_file)


def save_ledger(df: pd.DataFrame, ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> Path:
    with ledger_file_lock(ledger_file):
        return save_ledger_unlocked(df, ledger_file)


def update_ledger(
    ledger_file: str | Path,
    mutator: Callable[[pd.DataFrame], tuple[pd.DataFrame, T]],
) -> tuple[Path, T]:
    """Run a read-mutate-write ledger update under one exclusive file lock."""
    with ledger_file_lock(ledger_file):
        path = ensure_ledger_unlocked(ledger_file)
        current = load_ledger_unlocked(path)
        updated, result = mutator(current)
        save_ledger_unlocked(updated, path)
        return path, result
