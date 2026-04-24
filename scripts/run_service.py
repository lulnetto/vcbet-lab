from __future__ import annotations

import uvicorn

from vcbet.service.api import app
from vcbet.service.settings import ServiceSettings


if __name__ == "__main__":
    settings = ServiceSettings.load()
    uvicorn.run(app, host=settings.host, port=settings.port)
