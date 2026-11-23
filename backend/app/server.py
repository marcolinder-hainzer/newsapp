"""Einstiegspunkt für uvicorn: `uvicorn app.server:app`."""

import logging
import os

from .main import create_app

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

app = create_app()
