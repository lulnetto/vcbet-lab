from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable

from .schemas import JobRecord


class JobStore:
    def __init__(self, jobs_dir: Path):
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _fsync_jobs_dir(self) -> None:
        try:
            dir_fd = os.open(self.jobs_dir, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)

    def _write_text_atomic(self, path: Path, payload: str) -> None:
        tmp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                delete=False,
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                encoding="utf-8",
            ) as tmp:
                tmp_name = tmp.name
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, path)
            self._fsync_jobs_dir()
        finally:
            if tmp_name:
                try:
                    Path(tmp_name).unlink()
                except FileNotFoundError:
                    pass

    def save(self, record: JobRecord) -> None:
        path = self._path_for(record.id)
        payload = record.model_dump_json(indent=2) if hasattr(record, "model_dump_json") else record.json(indent=2)
        self._write_text_atomic(path, payload)

    def load(self, job_id: str) -> JobRecord | None:
        path = self._path_for(job_id)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        return JobRecord.model_validate_json(raw) if hasattr(JobRecord, "model_validate_json") else JobRecord.parse_raw(raw)

    def list_all(self) -> list[JobRecord]:
        records: list[JobRecord] = []
        for path in sorted(self.jobs_dir.glob("*.json"), reverse=True):
            try:
                raw = path.read_text(encoding="utf-8")
                records.append(JobRecord.model_validate_json(raw) if hasattr(JobRecord, "model_validate_json") else JobRecord.parse_raw(raw))
            except Exception:
                continue
        records.sort(key=lambda item: item.created_at, reverse=True)
        return records

    def delete(self, job_id: str) -> bool:
        path = self._path_for(job_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def delete_finished_failed(self) -> int:
        removed = 0
        for record in self.list_all():
            if record.status in {"failed", "cancelled", "interrupted", "blocked"}:
                if self.delete(record.id):
                    removed += 1
        return removed

    def mark_interrupted_runs(self) -> None:
        for record in self.list_all():
            if record.status in {"queued", "running"}:
                record.status = "interrupted"
                if record.finished_at is None:
                    from datetime import datetime
                    record.finished_at = datetime.now()
                if not record.error:
                    record.error = "Serviço reiniciado durante execução anterior."
                for phase in record.phases:
                    if phase.status in {"queued", "running"}:
                        phase.status = "interrupted"
                self.save(record)
