__version__ = "0.1.0"

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .paths import ensure_app_dirs
from .routes import router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    ensure_app_dirs()

    # One-shot migration: rewrite any pre-existing parquet datasets whose
    # column names predate MT4/MT5 bracket-header normalization (``<OPEN>``
    # etc.). Idempotent on already-clean files; runs once per process and
    # never blocks startup beyond a few ms per dataset.
    try:
        from . import storage

        result = storage.migrate_normalize_dataset_columns()
        if result.get("fixed"):
            logger.info(
                "Dataset migration: scanned=%d fixed=%d",
                result["scanned"],
                result["fixed"],
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Dataset column migration failed: %s", exc)

    app = FastAPI(title="StratForge AI Backend", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")

    @app.on_event("shutdown")
    def _cleanup_processes():
        """Kill all managed background processes on server shutdown."""
        try:
            from .process_manager import get_manager
            count = get_manager().stop_all()
            if count:
                logger.info("Process manager: stopped %d managed process(es)", count)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Process cleanup failed: %s", exc)

    return app
