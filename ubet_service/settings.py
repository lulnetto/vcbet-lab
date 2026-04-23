from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServiceSettings:
    project_root: Path
    jobs_dir: Path
    logs_dir: Path
    host: str = "127.0.0.1"
    port: int = 8010

    @classmethod
    def load(cls) -> "ServiceSettings":
        project_root = Path(os.getenv("UBET_PROJECT_ROOT", Path(__file__).resolve().parent.parent)).resolve()
        service_root = project_root / "data" / "service"
        jobs_dir = Path(os.getenv("UBET_SERVICE_JOBS_DIR", service_root / "jobs")).resolve()
        logs_dir = Path(os.getenv("UBET_SERVICE_LOGS_DIR", service_root / "logs")).resolve()
        jobs_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        host = os.getenv("UBET_SERVICE_HOST", "127.0.0.1")
        port = int(os.getenv("UBET_SERVICE_PORT", "8010"))
        return cls(
            project_root=project_root,
            jobs_dir=jobs_dir,
            logs_dir=logs_dir,
            host=host,
            port=port,
        )
