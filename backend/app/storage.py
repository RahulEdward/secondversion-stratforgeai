import json
import secrets
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import data as data_module
from .paths import (
    APP_STATE_FILE,
    WORKSPACES_DIR,
    ensure_app_dirs,
    workspace_dir,
)
from .schemas import AppState, Dataset, Project, Session


# Per-project SQLite schema. Sessions + messages + datasets live together.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    provider TEXT,
    model TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant','system','tool')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    rows INTEGER NOT NULL,
    columns TEXT NOT NULL,      -- JSON array
    has_ohlcv INTEGER NOT NULL, -- 0 or 1
    start_date TEXT,
    end_date TEXT,
    size_bytes INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Phase 9 — saved strategies. Each row is a re-runnable StrategySpec
-- snapshot (the same shape `run_backtest` accepts), optionally tagged
-- with the backtest/grade/verdict/score it was scored against.
CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    spec TEXT NOT NULL,                 -- JSON object (StrategySpec)
    source_backtest_id TEXT,
    grade TEXT,
    verdict TEXT,
    score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_strategies_name ON strategies(name);
"""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_project_id() -> str:
    return f"pj_{secrets.token_hex(6)}"


def _new_session_id() -> str:
    return f"ss_{secrets.token_hex(8)}"


def _new_dataset_id() -> str:
    return f"ds_{secrets.token_hex(8)}"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _ensure_sessions_provider_columns(conn: sqlite3.Connection) -> bool:
    """Phase 4 migration — add nullable `provider`/`model` columns to `sessions`."""
    if not _table_exists(conn, "sessions"):
        return False
    changed = False
    if not _column_exists(conn, "sessions", "provider"):
        conn.execute("ALTER TABLE sessions ADD COLUMN provider TEXT")
        changed = True
    if not _column_exists(conn, "sessions", "model"):
        conn.execute("ALTER TABLE sessions ADD COLUMN model TEXT")
        changed = True
    return changed


def _init_project_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        if _table_exists(conn, "chats") and not _table_exists(conn, "sessions"):
            conn.execute("DROP TABLE IF EXISTS messages")
            conn.execute("DROP TABLE IF EXISTS chats")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def _open_project_db(project_id: str) -> sqlite3.Connection:
    db_path = workspace_dir(project_id) / "chats.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Lazy migrate so DBs made in earlier phases pick up new tables.
    migrated = False
    if _table_exists(conn, "chats") and not _table_exists(conn, "sessions"):
        conn.execute("DROP TABLE IF EXISTS messages")
        conn.execute("DROP TABLE IF EXISTS chats")
        migrated = True
    if not _table_exists(conn, "datasets"):
        migrated = True
    if not _table_exists(conn, "strategies"):
        # Phase 9 lazy migration — older project DBs predate the strategy
        # library, so add the table on first open.
        migrated = True
    if migrated:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    if _ensure_sessions_provider_columns(conn):
        conn.commit()
    return conn


def _read_project_json(ws_path: Path) -> Optional[Project]:
    cfg = ws_path / "workspace.json"
    if not cfg.exists():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return Project(**data)
    except Exception:
        return None


def _write_project_json(ws_path: Path, project: Project) -> None:
    cfg = ws_path / "workspace.json"
    cfg.write_text(project.model_dump_json(indent=2), encoding="utf-8")


# ---------- Projects ----------


def list_projects() -> List[Project]:
    ensure_app_dirs()
    projects: List[Project] = []
    for entry in WORKSPACES_DIR.iterdir():
        if not entry.is_dir():
            continue
        project = _read_project_json(entry)
        if project is not None:
            projects.append(project)
    projects.sort(key=lambda p: p.created_at, reverse=True)
    return projects


def create_project(name: str) -> Project:
    ensure_app_dirs()
    project_id = _new_project_id()
    ws_path = workspace_dir(project_id)
    ws_path.mkdir(parents=True, exist_ok=False)
    (ws_path / "data").mkdir()
    (ws_path / "reports").mkdir()
    (ws_path / "memory").mkdir()
    (ws_path / "memory" / "MEMORY.md").write_text("", encoding="utf-8")

    project = Project(id=project_id, name=name, created_at=_iso_now())
    _write_project_json(ws_path, project)
    _init_project_db(ws_path / "chats.db")
    return project


def get_project(project_id: str) -> Optional[Project]:
    return _read_project_json(workspace_dir(project_id))


def rename_project(project_id: str, new_name: str) -> Optional[Project]:
    ws_path = workspace_dir(project_id)
    project = _read_project_json(ws_path)
    if project is None:
        return None
    project = project.model_copy(update={"name": new_name})
    _write_project_json(ws_path, project)
    return project


def delete_project(project_id: str) -> bool:
    ws_path = workspace_dir(project_id)
    if not ws_path.exists():
        return False
    state = load_app_state()
    if state.active_project_id == project_id:
        state.active_project_id = None
        state.active_session_id = None
        save_app_state(state)
    shutil.rmtree(ws_path)
    return True


# ---------- Sessions ----------


def _row_to_session(project_id: str, row: sqlite3.Row) -> Session:
    # `row` keys not guaranteed across legacy DBs; access via column index fallback.
    keys = row.keys() if hasattr(row, "keys") else []
    provider = row["provider"] if "provider" in keys else None
    model = row["model"] if "model" in keys else None
    return Session(
        id=row["id"],
        project_id=project_id,
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        provider=provider,
        model=model,
    )


def list_sessions(project_id: str) -> Optional[List[Session]]:
    if get_project(project_id) is None:
        return None
    conn = _open_project_db(project_id)
    try:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at, provider, model FROM sessions "
            "ORDER BY updated_at DESC, created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_session(project_id, r) for r in rows]


def create_session(project_id: str, title: str) -> Optional[Session]:
    if get_project(project_id) is None:
        return None
    session_id = _new_session_id()
    now = _iso_now()
    conn = _open_project_db(project_id)
    try:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, title, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return Session(
        id=session_id,
        project_id=project_id,
        title=title,
        created_at=now,
        updated_at=now,
    )


def _find_session_project(session_id: str) -> Optional[str]:
    ensure_app_dirs()
    for entry in WORKSPACES_DIR.iterdir():
        if not entry.is_dir():
            continue
        project = _read_project_json(entry)
        if project is None:
            continue
        conn = _open_project_db(project.id)
        try:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ? LIMIT 1", (session_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is not None:
            return project.id
    return None


def get_session(session_id: str) -> Optional[Session]:
    project_id = _find_session_project(session_id)
    if project_id is None:
        return None
    conn = _open_project_db(project_id)
    try:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, provider, model FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_session(project_id, row)


def rename_session(session_id: str, new_title: str) -> Optional[Session]:
    project_id = _find_session_project(session_id)
    if project_id is None:
        return None
    now = _iso_now()
    conn = _open_project_db(project_id)
    try:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (new_title, now, session_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, provider, model FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_session(project_id, row)


def update_session_model(
    session_id: str, provider: str, model: str
) -> Optional[Session]:
    project_id = _find_session_project(session_id)
    if project_id is None:
        return None
    now = _iso_now()
    conn = _open_project_db(project_id)
    try:
        conn.execute(
            "UPDATE sessions SET provider = ?, model = ?, updated_at = ? WHERE id = ?",
            (provider, model, now, session_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, provider, model FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_session(project_id, row)


def delete_session(session_id: str) -> bool:
    project_id = _find_session_project(session_id)
    if project_id is None:
        return False
    conn = _open_project_db(project_id)
    try:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()
    state = load_app_state()
    if state.active_session_id == session_id:
        state.active_session_id = None
        save_app_state(state)
    return True


# ---------- Datasets ----------


def _row_to_dataset(project_id: str, row: sqlite3.Row) -> Dataset:
    return Dataset(
        id=row["id"],
        project_id=project_id,
        filename=row["filename"],
        rows=row["rows"],
        columns=json.loads(row["columns"]),
        has_ohlcv=bool(row["has_ohlcv"]),
        start_date=row["start_date"],
        end_date=row["end_date"],
        size_bytes=row["size_bytes"],
        uploaded_at=row["uploaded_at"],
    )


def list_datasets(project_id: str) -> Optional[List[Dataset]]:
    if get_project(project_id) is None:
        return None
    conn = _open_project_db(project_id)
    try:
        rows = conn.execute(
            "SELECT id, filename, rows, columns, has_ohlcv, start_date, end_date, "
            "size_bytes, uploaded_at FROM datasets ORDER BY uploaded_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_dataset(project_id, r) for r in rows]


def dataset_path(project_id: str, dataset_id: str) -> Path:
    return workspace_dir(project_id) / "data" / f"{dataset_id}.parquet"


def ingest_and_store_dataset(
    project_id: str,
    filename: str,
    source_path: Path,
) -> Optional[Dataset]:
    """Parse + persist. Caller is responsible for cleaning up source_path."""
    if get_project(project_id) is None:
        return None
    dataset_id = _new_dataset_id()
    dest = dataset_path(project_id, dataset_id)
    meta = data_module.ingest_dataset(source_path, dest)
    now = _iso_now()
    conn = _open_project_db(project_id)
    try:
        conn.execute(
            "INSERT INTO datasets (id, filename, rows, columns, has_ohlcv, "
            "start_date, end_date, size_bytes, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                dataset_id,
                filename,
                meta["rows"],
                json.dumps(meta["columns"]),
                1 if meta["has_ohlcv"] else 0,
                meta["start_date"],
                meta["end_date"],
                meta["size_bytes"],
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return Dataset(
        id=dataset_id,
        project_id=project_id,
        filename=filename,
        rows=meta["rows"],  # type: ignore[arg-type]
        columns=meta["columns"],  # type: ignore[arg-type]
        has_ohlcv=bool(meta["has_ohlcv"]),
        start_date=meta["start_date"],  # type: ignore[arg-type]
        end_date=meta["end_date"],  # type: ignore[arg-type]
        size_bytes=meta["size_bytes"],  # type: ignore[arg-type]
        uploaded_at=now,
    )


def _find_dataset_project(dataset_id: str) -> Optional[Tuple[str, sqlite3.Row]]:
    ensure_app_dirs()
    for entry in WORKSPACES_DIR.iterdir():
        if not entry.is_dir():
            continue
        project = _read_project_json(entry)
        if project is None:
            continue
        conn = _open_project_db(project.id)
        try:
            row = conn.execute(
                "SELECT id, filename, rows, columns, has_ohlcv, start_date, "
                "end_date, size_bytes, uploaded_at FROM datasets WHERE id = ?",
                (dataset_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is not None:
            return project.id, row
    return None


def get_dataset(dataset_id: str) -> Optional[Dataset]:
    found = _find_dataset_project(dataset_id)
    if found is None:
        return None
    project_id, row = found
    return _row_to_dataset(project_id, row)


def migrate_normalize_dataset_columns() -> Dict[str, int]:
    """Re-canonicalize stored parquets + DB metadata for older datasets.

    Datasets ingested before MT4/MT5 bracketed-header support landed have
    columns like ``<OPEN>`` persisted both in the parquet on disk and in the
    SQLite ``datasets`` row. This walks every project workspace, reads each
    parquet, runs the latest canonicalizer, and writes the cleaned frame +
    refreshed metadata back. Idempotent — already-clean datasets touch
    nothing on disk.

    Returns ``{"scanned": int, "fixed": int}``.
    """
    import pandas as pd

    ensure_app_dirs()
    scanned = 0
    fixed = 0
    for entry in WORKSPACES_DIR.iterdir():
        if not entry.is_dir():
            continue
        project = _read_project_json(entry)
        if project is None:
            continue
        conn = _open_project_db(project.id)
        try:
            rows = conn.execute(
                "SELECT id, columns, has_ohlcv, rows, start_date, end_date "
                "FROM datasets"
            ).fetchall()
            for row in rows:
                scanned += 1
                ds_path = dataset_path(project.id, row["id"])
                if not ds_path.exists():
                    continue
                try:
                    df = pd.read_parquet(ds_path)
                except Exception:
                    continue
                df_norm, mapping = data_module._canonicalize_columns(df)
                if not mapping:
                    continue  # already clean — skip rewrite
                # Re-apply time parsing in case <DATE>+<TIME> just got merged.
                df_norm = data_module._parse_time_column(df_norm)
                if df_norm.empty:
                    continue
                # Persist the fixed parquet + refreshed metadata.
                df_norm.to_parquet(ds_path, index=False)
                cols = list(df_norm.columns)
                has_ohlcv = data_module._has_ohlcv(df_norm)
                start_date = (
                    df_norm["time"].iloc[0].isoformat()
                    if "time" in df_norm.columns and not df_norm["time"].isna().all()
                    else row["start_date"]
                )
                end_date = (
                    df_norm["time"].iloc[-1].isoformat()
                    if "time" in df_norm.columns and not df_norm["time"].isna().all()
                    else row["end_date"]
                )
                conn.execute(
                    "UPDATE datasets SET columns = ?, has_ohlcv = ?, "
                    "rows = ?, start_date = ?, end_date = ?, "
                    "size_bytes = ? WHERE id = ?",
                    (
                        json.dumps(cols),
                        1 if has_ohlcv else 0,
                        int(len(df_norm)),
                        start_date,
                        end_date,
                        int(ds_path.stat().st_size),
                        row["id"],
                    ),
                )
                fixed += 1
            conn.commit()
        finally:
            conn.close()
    return {"scanned": scanned, "fixed": fixed}


def delete_dataset(dataset_id: str) -> bool:
    found = _find_dataset_project(dataset_id)
    if found is None:
        return False
    project_id, _ = found
    conn = _open_project_db(project_id)
    try:
        conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        conn.commit()
    finally:
        conn.close()
    path = dataset_path(project_id, dataset_id)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    return True


# ---------- Phase 9 — strategy library ----------


from dataclasses import dataclass


class StrategyNameConflict(ValueError):
    """Raised when a strategy name already exists in the target project."""


@dataclass
class SavedStrategy:
    id: str
    project_id: str
    name: str
    description: Optional[str]
    spec: Dict
    source_backtest_id: Optional[str]
    grade: Optional[str]
    verdict: Optional[str]
    score: Optional[float]
    created_at: str
    updated_at: str


def _new_strategy_id() -> str:
    return f"strat_{secrets.token_hex(8)}"


def _row_to_strategy(project_id: str, row: sqlite3.Row) -> SavedStrategy:
    return SavedStrategy(
        id=row["id"],
        project_id=project_id,
        name=row["name"],
        description=row["description"],
        spec=json.loads(row["spec"]) if row["spec"] else {},
        source_backtest_id=row["source_backtest_id"],
        grade=row["grade"],
        verdict=row["verdict"],
        score=(float(row["score"]) if row["score"] is not None else None),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_strategy(
    project_id: str,
    *,
    name: str,
    spec: Dict,
    description: Optional[str] = None,
    source_backtest_id: Optional[str] = None,
    grade: Optional[str] = None,
    verdict: Optional[str] = None,
    score: Optional[float] = None,
) -> Optional[SavedStrategy]:
    """Insert a strategy row. Returns ``None`` if the project doesn't exist;
    raises :class:`StrategyNameConflict` on duplicate name within the project.
    """
    if get_project(project_id) is None:
        return None
    name = name.strip()
    if not name:
        raise ValueError("strategy `name` must be non-empty")

    sid = _new_strategy_id()
    now = _iso_now()
    conn = _open_project_db(project_id)
    try:
        # Conflict check is project-scoped (UNIQUE in SCHEMA covers this DB).
        existing = conn.execute(
            "SELECT id FROM strategies WHERE name = ?", (name,)
        ).fetchone()
        if existing is not None:
            raise StrategyNameConflict(
                f"Strategy name '{name}' already exists in this project"
            )
        conn.execute(
            "INSERT INTO strategies (id, name, description, spec, "
            "source_backtest_id, grade, verdict, score, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sid,
                name,
                description,
                json.dumps(spec),
                source_backtest_id,
                grade,
                verdict,
                score,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return SavedStrategy(
        id=sid,
        project_id=project_id,
        name=name,
        description=description,
        spec=spec,
        source_backtest_id=source_backtest_id,
        grade=grade,
        verdict=verdict,
        score=score,
        created_at=now,
        updated_at=now,
    )


def list_strategies(project_id: str) -> Optional[List[SavedStrategy]]:
    """List all strategies in a project. Returns ``None`` if project missing."""
    if get_project(project_id) is None:
        return None
    conn = _open_project_db(project_id)
    try:
        rows = conn.execute(
            "SELECT id, name, description, spec, source_backtest_id, grade, "
            "verdict, score, created_at, updated_at "
            "FROM strategies ORDER BY datetime(updated_at) DESC"
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_strategy(project_id, r) for r in rows]


def get_strategy(strategy_id: str) -> Optional[SavedStrategy]:
    """Find a strategy by id across all projects."""
    ensure_app_dirs()
    for entry in WORKSPACES_DIR.iterdir():
        if not entry.is_dir():
            continue
        project = _read_project_json(entry)
        if project is None:
            continue
        conn = _open_project_db(project.id)
        try:
            row = conn.execute(
                "SELECT id, name, description, spec, source_backtest_id, "
                "grade, verdict, score, created_at, updated_at "
                "FROM strategies WHERE id = ?",
                (strategy_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is not None:
            return _row_to_strategy(project.id, row)
    return None


def delete_strategy(strategy_id: str) -> bool:
    """Delete a strategy by id (looked up across projects). Returns True if removed."""
    ensure_app_dirs()
    for entry in WORKSPACES_DIR.iterdir():
        if not entry.is_dir():
            continue
        project = _read_project_json(entry)
        if project is None:
            continue
        conn = _open_project_db(project.id)
        try:
            cur = conn.execute(
                "DELETE FROM strategies WHERE id = ?", (strategy_id,)
            )
            conn.commit()
            if cur.rowcount > 0:
                return True
        finally:
            conn.close()
    return False


# ---------- App state ----------


def load_app_state() -> AppState:
    ensure_app_dirs()
    if not APP_STATE_FILE.exists():
        return AppState()
    try:
        data = json.loads(APP_STATE_FILE.read_text(encoding="utf-8"))
        if "active_workspace_id" in data and "active_project_id" not in data:
            data["active_project_id"] = data.pop("active_workspace_id")
        return AppState(**data)
    except Exception:
        return AppState()


def save_app_state(state: AppState) -> None:
    ensure_app_dirs()
    APP_STATE_FILE.write_text(state.model_dump_json(indent=2), encoding="utf-8")


# ---------- Messages (Phase 6) ----------

import json as _json


def list_messages(session_id: str) -> Optional[List[Dict]]:
    """Return all messages for a session, ordered by id. None if session not found."""
    project_id = _find_session_project(session_id)
    if project_id is None:
        return None
    conn = _open_project_db(project_id)
    try:
        rows = conn.execute(
            "SELECT id, session_id, role, content, created_at FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        out = []
        for r in rows:
            try:
                content = _json.loads(r["content"])
            except (_json.JSONDecodeError, TypeError):
                content = [{"type": "text", "text": str(r["content"])}]
            out.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "role": r["role"],
                "content": content,
                "created_at": r["created_at"],
            })
        return out
    finally:
        conn.close()


def add_message(
    session_id: str,
    role: str,
    content: List[Dict],
) -> Optional[Dict]:
    """Persist a message and return it. None if session not found."""
    project_id = _find_session_project(session_id)
    if project_id is None:
        return None
    conn = _open_project_db(project_id)
    now = _iso_now()
    try:
        cur = conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, _json.dumps(content, default=str), now),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
        }
    finally:
        conn.close()
