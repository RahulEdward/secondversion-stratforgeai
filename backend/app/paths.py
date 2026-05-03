from pathlib import Path

HOME = Path.home()
APP_ROOT = HOME / "StratForge"
WORKSPACES_DIR = APP_ROOT / "workspaces"
AGENT_WORKSPACE = APP_ROOT / "agent_workspace"
APP_STATE_FILE = APP_ROOT / "app.json"


def ensure_app_dirs() -> None:
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_WORKSPACE.mkdir(parents=True, exist_ok=True)


def workspace_dir(ws_id: str) -> Path:
    return WORKSPACES_DIR / ws_id


def resolve_agent_path(rel_or_abs: str) -> Path:
    """Resolve a path the agent supplied. Relative paths root at AGENT_WORKSPACE.
    Absolute paths are kept as-is (caller may further restrict)."""
    p = Path(rel_or_abs)
    if not p.is_absolute():
        p = AGENT_WORKSPACE / p
    return p.resolve()
