from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from vcbet.paths import PROJECT_ROOT, SERVICE_DIR


@dataclass(frozen=True)
class ServiceSettings:
    project_root: Path
    jobs_dir: Path
    logs_dir: Path
    host: str = "127.0.0.1"
    port: int = 8010

    @classmethod
    def load(cls) -> "ServiceSettings":
        project_root = PROJECT_ROOT
        service_root = SERVICE_DIR
        jobs_dir = Path(os.getenv("VCBET_SERVICE_JOBS_DIR", os.getenv("UBET_SERVICE_JOBS_DIR", service_root / "jobs"))).resolve()
        logs_dir = Path(os.getenv("VCBET_SERVICE_LOGS_DIR", os.getenv("UBET_SERVICE_LOGS_DIR", service_root / "logs"))).resolve()
        jobs_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        host = os.getenv("VCBET_SERVICE_HOST", os.getenv("UBET_SERVICE_HOST", "127.0.0.1"))
        port = int(os.getenv("VCBET_SERVICE_PORT", os.getenv("UBET_SERVICE_PORT", "8010")))
        return cls(
            project_root=project_root,
            jobs_dir=jobs_dir,
            logs_dir=logs_dir,
            host=host,
            port=port,
        )
