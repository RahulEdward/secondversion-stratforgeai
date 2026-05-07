"""StratForge AI backend — FastAPI entry point.

Vibe-Trading's agent harness, skills, swarm, and backtest engine are all
vendored under backend/app/ (agents/, skills/, swarm/, agent_tools/,
agent_memory/, shadow_account/, backtest_engine/), so the standard
``from app.xxx`` imports work out of the box.
"""
import sys
from pathlib import Path

# Ensure the backend/ directory is on sys.path so ``from app import ...``
# works whether main.py is run directly or the package is imported from
# elsewhere (scripts/, tests, pytest).
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
