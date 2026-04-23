from __future__ import annotations

import os
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .commands import CommandSpec
from .job_store import JobStore
from .schemas import JobPhase, JobRecord


@dataclass
class ActiveProcess:
    process: subprocess.Popen
    log_path: Path
    resource_key: str | None


class ResourceBusyError(RuntimeError):
    pass


class JobManager:
    def __init__(self, store: JobStore, logs_dir: Path):
        self.store = store
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._active_processes: dict[str, ActiveProcess] = {}
        self._resource_holders: dict[str, str] = {}

    def _new_job_id(self) -> str:
        return f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    def _reserve_resource(self, resource_key: str | None, job_id: str) -> None:
        if not resource_key:
            return
        with self._lock:
            holder = self._resource_holders.get(resource_key)
            if holder and holder != job_id:
                raise ResourceBusyError(f"Recurso ocupado por job em execução: {holder}")
            self._resource_holders[resource_key] = job_id

    def _release_resource(self, resource_key: str | None, job_id: str) -> None:
        if not resource_key:
            return
        with self._lock:
            holder = self._resource_holders.get(resource_key)
            if holder == job_id:
                self._resource_holders.pop(resource_key, None)

    def list_jobs(self) -> list[JobRecord]:
        return self.store.list_all()

    def get_job(self, job_id: str) -> JobRecord | None:
        return self.store.load(job_id)

    def read_log_tail(self, job_id: str, lines: int = 200) -> str:
        record = self.get_job(job_id)
        if not record or not record.log_path:
            return ""
        path = Path(record.log_path)
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(text[-lines:])

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            active = self._active_processes.get(job_id)
        if not active:
            return False
        proc = active.process
        if proc.poll() is None:
            try:
                if os.name == "nt":
                    proc.terminate()
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        return True

    def submit_command_job(self, *, title: str, job_type: str, request: dict, command: CommandSpec, resource_key: str | None) -> JobRecord:
        return self.submit_pipeline_job(
            title=title,
            job_type=job_type,
            request=request,
            commands=[command],
            resource_key=resource_key,
        )

    def submit_pipeline_job(self, *, title: str, job_type: str, request: dict, commands: list[CommandSpec], resource_key: str | None) -> JobRecord:
        job_id = self._new_job_id()
        self._reserve_resource(resource_key, job_id)
        log_path = self.logs_dir / f"{job_id}.log"
        record = JobRecord(
            id=job_id,
            job_type=job_type,
            status="queued",
            title=title,
            created_at=datetime.now(),
            resource_key=resource_key,
            request=request,
            phases=[JobPhase(name=spec.name, command=spec.command) for spec in commands],
            log_path=str(log_path),
            command_preview=" && ".join(" ".join(spec.command) for spec in commands),
        )
        self.store.save(record)
        thread = threading.Thread(target=self._run_pipeline, args=(record.id, commands), daemon=True)
        thread.start()
        return record

    def _run_pipeline(self, job_id: str, commands: list[CommandSpec]) -> None:
        record = self.store.load(job_id)
        if not record:
            return
        record.status = "running"
        record.started_at = datetime.now()
        self.store.save(record)
        log_path = Path(record.log_path) if record.log_path else self.logs_dir / f"{job_id}.log"
        try:
            with log_path.open("a", encoding="utf-8") as log_file:
                for index, spec in enumerate(commands):
                    record = self.store.load(job_id)
                    if not record:
                        return
                    phase = record.phases[index]
                    phase.status = "running"
                    phase.started_at = datetime.now()
                    self.store.save(record)

                    log_file.write(f"\n=== [{datetime.now().isoformat()}] INICIO {spec.name} ===\n")
                    log_file.write("$ " + " ".join(spec.command) + "\n")
                    log_file.flush()

                    proc = subprocess.Popen(
                        spec.command,
                        cwd=spec.cwd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        universal_newlines=True,
                        preexec_fn=os.setsid if os.name != "nt" else None,
                    )
                    with self._lock:
                        self._active_processes[job_id] = ActiveProcess(proc, log_path, record.resource_key)

                    assert proc.stdout is not None
                    for line in proc.stdout:
                        log_file.write(line)
                        log_file.flush()

                    exit_code = proc.wait()
                    with self._lock:
                        self._active_processes.pop(job_id, None)

                    record = self.store.load(job_id)
                    if not record:
                        return
                    phase = record.phases[index]
                    phase.exit_code = exit_code
                    phase.finished_at = datetime.now()

                    if exit_code == 0:
                        phase.status = "success"
                        self.store.save(record)
                        continue

                    if exit_code in {-15, 143}:
                        phase.status = "cancelled"
                        record.status = "cancelled"
                        record.error = f"Execução cancelada no passo {spec.name}."
                    else:
                        phase.status = "failed"
                        record.status = "failed"
                        record.error = f"Falha no passo {spec.name} com exit_code={exit_code}."
                    record.exit_code = exit_code
                    record.finished_at = datetime.now()
                    self.store.save(record)
                    return

                record = self.store.load(job_id)
                if not record:
                    return
                record.status = "success"
                record.exit_code = 0
                record.finished_at = datetime.now()
                for phase in record.phases:
                    if phase.status == "running":
                        phase.status = "success"
                        phase.finished_at = datetime.now()
                        phase.exit_code = 0
                self.store.save(record)
        finally:
            latest = self.store.load(job_id)
            resource_key = latest.resource_key if latest else None
            self._release_resource(resource_key, job_id)
