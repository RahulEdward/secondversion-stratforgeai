"""StratForge AI backend — FastAPI entry point.

Adds ``backend/`` to ``sys.path`` up-front so Vibe-Trading's imports
(``from src.xxx``, ``from backtest.xxx``) resolve without packaging
gymnastics. Must run before any ``from app import …`` statement.
"""
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import uvicorn  # noqa: E402

from app import create_app  # noqa: E402

app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8765,
        reload=True,
        log_level="info",
    )
