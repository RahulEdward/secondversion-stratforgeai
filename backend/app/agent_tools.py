"""System tools (Claude Code-style) the LLM can call: shell, file I/O, Python.

Operations default-root at AGENT_WORKSPACE so the agent has its own scratch
folder under ~/StratForge/agent_workspace. Absolute paths are honoured but
the dispatcher caps blast radius:
  - block writes/edits outside AGENT_WORKSPACE unless the caller is in
    bypass permission mode
  - never let shell commands run for more than SHELL_TIMEOUT_SEC

Permission modes (passed in via the orchestrator):
  ask           → every tool returns a "permission_required" stub the UI
                  can convert into an inline prompt. Today we surface this
                  as a tool error so the model can ask the user; a richer
                  flow lands when the chat UI grows confirm chips.
  accept-edits  → file reads + writes + edits + listing are auto-approved;
                  shell + python still respect plan-mode rules (read-only).
  plan          → only non-mutating tools (read_file, list_dir) succeed.
  bypass        → everything allowed, anywhere on disk.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import AGENT_WORKSPACE, resolve_agent_path

# ── Limits & defaults ──────────────────────────────────────────────────

SHELL_TIMEOUT_SEC = 60
PYTHON_TIMEOUT_SEC = 60
MAX_FILE_BYTES = 1_000_000         # 1 MB cap on read_file output
MAX_LIST_ENTRIES = 500             # truncate `list_dir` to keep payload small
MAX_OUTPUT_CHARS = 30_000          # cap stdout/stderr returned to the LLM

# These tools never mutate state — safe in plan mode.
_READ_ONLY_TOOLS = {"read_file", "list_dir"}

# These mutate the agent workspace — blocked in plan mode, allowed in
# accept-edits and bypass.
_EDIT_TOOLS = {"write_file", "edit_file", "create_dir"}

# Heavy tools (shell, python, delete) — plan blocks; accept-edits ALSO
# blocks because the user said "edits OK, but no shell"; only bypass runs.
_HEAVY_TOOLS = {"shell", "run_python", "delete_path"}

# Process management tools — same permission level as heavy tools.
_PROCESS_TOOLS = {"start_process", "stop_process", "list_processes", "get_process_output"}

# UI signal tools — these are lightweight and safe in any mode.
_SIGNAL_TOOLS = {"open_preview"}

# Tool name set the orchestrator can route here.
AGENT_TOOLS: set[str] = (
    _READ_ONLY_TOOLS | _EDIT_TOOLS | _HEAVY_TOOLS | _PROCESS_TOOLS | _SIGNAL_TOOLS
)


# ── Tool schemas (Anthropic-shaped) ────────────────────────────────────

def tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "name": "shell",
            "description": (
                "Run a shell command (cmd.exe on Windows, /bin/sh elsewhere) "
                "in the agent workspace. Returns stdout/stderr/exit code. "
                f"Times out after {SHELL_TIMEOUT_SEC}s. "
                "Use for `git`, `npm`, `pip`, file ops, etc."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Full shell command line."},
                    "cwd": {"type": "string", "description": "Working dir (relative to agent workspace, or absolute)."},
                },
                "required": ["command"],
            },
        },
        {
            "name": "run_python",
            "description": (
                "Run a Python snippet using the system `python`. Captures "
                f"stdout/stderr, exit code; times out after {PYTHON_TIMEOUT_SEC}s."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python source to execute."},
                },
                "required": ["code"],
            },
        },
        {
            "name": "read_file",
            "description": "Read a UTF-8 text file. Returns up to ~1 MB.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to agent workspace, or absolute)."},
                },
                "required": ["path"],
            },
        },
        {
            "name": "write_file",
            "description": "Create or overwrite a UTF-8 text file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "edit_file",
            "description": (
                "Replace `old_string` with `new_string` in a file. The match "
                "must be unique. Use replace_all=true to swap every occurrence."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean", "default": False},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
        {
            "name": "list_dir",
            "description": "List entries in a directory (capped at 500). Returns name + type + size.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Defaults to the agent workspace if omitted."},
                },
            },
        },
        {
            "name": "create_dir",
            "description": "Create a directory (with parents).",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "start_process",
            "description": (
                "Start a long-running process (dev server, build watcher, etc.) "
                "in the background. Returns a process ID. The system auto-detects "
                "when the server is ready and which port it's listening on. "
                "Use this instead of `shell` for commands that run indefinitely."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to run (e.g. 'npm run dev', 'python -m http.server 8080')."},
                    "cwd": {"type": "string", "description": "Working directory (relative to agent workspace, or absolute)."},
                    "label": {"type": "string", "description": "Human-readable label (e.g. 'Frontend Dev Server')."},
                    "wait_ready": {"type": "boolean", "default": True, "description": "Wait up to 30s for the server to signal readiness."},
                },
                "required": ["command"],
            },
        },
        {
            "name": "stop_process",
            "description": "Stop a managed background process by its ID.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "The proc_XXXX ID returned by start_process."},
                },
                "required": ["process_id"],
            },
        },
        {
            "name": "list_processes",
            "description": "List all managed background processes with their status, ports, and uptime.",
            "input_schema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "get_process_output",
            "description": "Get recent stdout/stderr output from a managed process (last N lines).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string"},
                    "last_n": {"type": "integer", "default": 50, "description": "Number of recent lines to return."},
                },
                "required": ["process_id"],
            },
        },
        {
            "name": "open_preview",
            "description": (
                "Signal the desktop app to open the Preview panel to a specific URL. "
                "Use after starting a dev server to show the user the live app."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to open (e.g. 'http://localhost:3000')."},
                    "label": {"type": "string", "description": "Optional label for the preview tab."},
                },
                "required": ["url"],
            },
        },
        {
            "name": "delete_path",
            "description": "Delete a file or empty directory. Refuses to delete non-empty dirs unless recursive=true.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "recursive": {"type": "boolean", "default": False},
                },
                "required": ["path"],
            },
        },
    ]


# ── Permission gating ──────────────────────────────────────────────────

def _gate(tool: str, mode: str) -> Optional[str]:
    """Return an error message if the tool is blocked in this mode, else None."""
    if mode == "bypass":
        return None
    # Signal tools are always allowed — they don't mutate anything.
    if tool in _SIGNAL_TOOLS:
        return None
    # list_processes is read-only.
    if tool == "list_processes":
        return None
    if mode == "plan":
        if tool in _READ_ONLY_TOOLS or tool == "get_process_output":
            return None
        return f"Plan mode is read-only — `{tool}` is blocked. Switch to Accept edits or Bypass."
    if mode == "accept-edits":
        if tool in _READ_ONLY_TOOLS or tool in _EDIT_TOOLS or tool in _PROCESS_TOOLS:
            return None
        return f"Accept-edits mode does not run shell/python. Switch to Bypass to run `{tool}`."
    if mode == "ask":
        if tool in _READ_ONLY_TOOLS or tool in _EDIT_TOOLS or tool in _PROCESS_TOOLS:
            return None
        return f"Ask mode requires confirmation for `{tool}`. Switch to Bypass to allow shell/python."
    return None


def _enforce_workspace(path: Path, *, allow_outside: bool, tool: str) -> Optional[str]:
    """Return an error message if writing outside AGENT_WORKSPACE without bypass."""
    if allow_outside:
        return None
    try:
        path.relative_to(AGENT_WORKSPACE)
    except ValueError:
        return (
            f"`{tool}` refused — path is outside the agent workspace "
            f"({AGENT_WORKSPACE}). Switch to Bypass mode to operate elsewhere."
        )
    return None


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> Tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n…(truncated {len(text) - limit} chars)", True


# ── Dispatcher ─────────────────────────────────────────────────────────

async def run_agent_tool(
    name: str,
    input_: Dict[str, Any],
    *,
    permission_mode: str = "accept-edits",
) -> Dict[str, Any]:
    """Dispatch an agent tool. Always returns {ok, output|error}."""
    blocked = _gate(name, permission_mode)
    if blocked:
        return {"ok": False, "error": blocked}

    try:
        if name == "shell":
            return await _do_shell(input_, permission_mode)
        if name == "run_python":
            return await _do_python(input_, permission_mode)
        if name == "read_file":
            return await asyncio.to_thread(_do_read_file, input_)
        if name == "write_file":
            return await asyncio.to_thread(_do_write_file, input_, permission_mode)
        if name == "edit_file":
            return await asyncio.to_thread(_do_edit_file, input_, permission_mode)
        if name == "list_dir":
            return await asyncio.to_thread(_do_list_dir, input_)
        if name == "create_dir":
            return await asyncio.to_thread(_do_create_dir, input_, permission_mode)
        if name == "delete_path":
            return await asyncio.to_thread(_do_delete_path, input_, permission_mode)
        # Process management tools
        if name == "start_process":
            return await asyncio.to_thread(_do_start_process, input_)
        if name == "stop_process":
            return await asyncio.to_thread(_do_stop_process, input_)
        if name == "list_processes":
            return await asyncio.to_thread(_do_list_processes, input_)
        if name == "get_process_output":
            return await asyncio.to_thread(_do_get_process_output, input_)
        if name == "open_preview":
            return _do_open_preview(input_)
    except Exception as exc:  # noqa: BLE001 — boundary
        return {"ok": False, "error": f"Tool crashed: {exc.__class__.__name__}: {exc}"}
    return {"ok": False, "error": f"Unknown agent tool: {name}"}


# ── Implementations ────────────────────────────────────────────────────

async def _do_shell(input_: Dict[str, Any], mode: str) -> Dict[str, Any]:
    cmd = input_.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return {"ok": False, "error": "Missing required `command`"}
    cwd_raw = input_.get("cwd")
    cwd = resolve_agent_path(cwd_raw) if isinstance(cwd_raw, str) and cwd_raw else AGENT_WORKSPACE
    if not cwd.exists():
        cwd.mkdir(parents=True, exist_ok=True)

    use_shell = True if os.name == "nt" else True  # both platforms: pass through shell
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=SHELL_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            proc.kill()
            return {"ok": False, "error": f"Shell command timed out after {SHELL_TIMEOUT_SEC}s"}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to start shell: {exc}"}

    stdout, t1 = _truncate(stdout_b.decode("utf-8", errors="replace"))
    stderr, t2 = _truncate(stderr_b.decode("utf-8", errors="replace"))
    return {
        "ok": True,
        "output": {
            "command": cmd,
            "cwd": str(cwd),
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": t1 or t2,
        },
    }


async def _do_python(input_: Dict[str, Any], mode: str) -> Dict[str, Any]:
    code = input_.get("code")
    if not isinstance(code, str) or not code.strip():
        return {"ok": False, "error": "Missing required `code`"}
    AGENT_WORKSPACE.mkdir(parents=True, exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", code,
            cwd=str(AGENT_WORKSPACE),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=PYTHON_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            proc.kill()
            return {"ok": False, "error": f"Python timed out after {PYTHON_TIMEOUT_SEC}s"}
    except FileNotFoundError:
        return {"ok": False, "error": "`python` not on PATH"}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to run python: {exc}"}

    stdout, t1 = _truncate(stdout_b.decode("utf-8", errors="replace"))
    stderr, t2 = _truncate(stderr_b.decode("utf-8", errors="replace"))
    return {
        "ok": True,
        "output": {
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": t1 or t2,
        },
    }


def _do_read_file(input_: Dict[str, Any]) -> Dict[str, Any]:
    path_raw = input_.get("path")
    if not isinstance(path_raw, str) or not path_raw:
        return {"ok": False, "error": "Missing required `path`"}
    path = resolve_agent_path(path_raw)
    if not path.exists():
        return {"ok": False, "error": f"File not found: {path}"}
    if not path.is_file():
        return {"ok": False, "error": f"Not a file: {path}"}
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            with path.open("rb") as f:
                raw = f.read(MAX_FILE_BYTES)
            text = raw.decode("utf-8", errors="replace")
            truncated = True
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            truncated = False
    except Exception as exc:
        return {"ok": False, "error": f"Read failed: {exc}"}
    return {
        "ok": True,
        "output": {"path": str(path), "size": size, "content": text, "truncated": truncated},
    }


def _do_write_file(input_: Dict[str, Any], mode: str) -> Dict[str, Any]:
    path_raw = input_.get("path")
    content = input_.get("content")
    if not isinstance(path_raw, str) or not path_raw:
        return {"ok": False, "error": "Missing required `path`"}
    if not isinstance(content, str):
        return {"ok": False, "error": "`content` must be a string"}
    path = resolve_agent_path(path_raw)
    err = _enforce_workspace(path, allow_outside=(mode == "bypass"), tool="write_file")
    if err:
        return {"ok": False, "error": err}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"Write failed: {exc}"}
    return {"ok": True, "output": {"path": str(path), "bytes": len(content.encode("utf-8"))}}


def _do_edit_file(input_: Dict[str, Any], mode: str) -> Dict[str, Any]:
    path_raw = input_.get("path")
    old = input_.get("old_string")
    new = input_.get("new_string")
    replace_all = bool(input_.get("replace_all", False))
    if not isinstance(path_raw, str) or not path_raw:
        return {"ok": False, "error": "Missing required `path`"}
    if not isinstance(old, str) or not isinstance(new, str):
        return {"ok": False, "error": "`old_string` and `new_string` must be strings"}
    path = resolve_agent_path(path_raw)
    err = _enforce_workspace(path, allow_outside=(mode == "bypass"), tool="edit_file")
    if err:
        return {"ok": False, "error": err}
    if not path.exists():
        return {"ok": False, "error": f"File not found: {path}"}
    try:
        original = path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"Read failed: {exc}"}

    occurrences = original.count(old)
    if occurrences == 0:
        return {"ok": False, "error": "`old_string` not found"}
    if not replace_all and occurrences > 1:
        return {
            "ok": False,
            "error": f"`old_string` matches {occurrences} times — make it unique or set replace_all=true",
        }
    updated = original.replace(old, new) if replace_all else original.replace(old, new, 1)
    try:
        path.write_text(updated, encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"Write failed: {exc}"}
    return {
        "ok": True,
        "output": {"path": str(path), "replacements": occurrences if replace_all else 1},
    }


def _do_list_dir(input_: Dict[str, Any]) -> Dict[str, Any]:
    path_raw = input_.get("path")
    path = resolve_agent_path(path_raw) if isinstance(path_raw, str) and path_raw else AGENT_WORKSPACE
    if not path.exists():
        return {"ok": False, "error": f"Directory not found: {path}"}
    if not path.is_dir():
        return {"ok": False, "error": f"Not a directory: {path}"}
    entries: List[Dict[str, Any]] = []
    try:
        for child in sorted(path.iterdir()):
            try:
                st = child.stat()
            except Exception:
                continue
            entries.append({
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "size": st.st_size if child.is_file() else None,
            })
            if len(entries) >= MAX_LIST_ENTRIES:
                break
    except Exception as exc:
        return {"ok": False, "error": f"List failed: {exc}"}
    return {"ok": True, "output": {"path": str(path), "count": len(entries), "entries": entries}}


def _do_create_dir(input_: Dict[str, Any], mode: str) -> Dict[str, Any]:
    path_raw = input_.get("path")
    if not isinstance(path_raw, str) or not path_raw:
        return {"ok": False, "error": "Missing required `path`"}
    path = resolve_agent_path(path_raw)
    err = _enforce_workspace(path, allow_outside=(mode == "bypass"), tool="create_dir")
    if err:
        return {"ok": False, "error": err}
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return {"ok": False, "error": f"Create dir failed: {exc}"}
    return {"ok": True, "output": {"path": str(path)}}


def _do_delete_path(input_: Dict[str, Any], mode: str) -> Dict[str, Any]:
    path_raw = input_.get("path")
    recursive = bool(input_.get("recursive", False))
    if not isinstance(path_raw, str) or not path_raw:
        return {"ok": False, "error": "Missing required `path`"}
    path = resolve_agent_path(path_raw)
    err = _enforce_workspace(path, allow_outside=(mode == "bypass"), tool="delete_path")
    if err:
        return {"ok": False, "error": err}
    if not path.exists():
        return {"ok": False, "error": f"Path not found: {path}"}
    try:
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            if recursive:
                import shutil
                shutil.rmtree(path)
            else:
                if any(path.iterdir()):
                    return {"ok": False, "error": "Directory is not empty — pass recursive=true to wipe."}
                path.rmdir()
    except Exception as exc:
        return {"ok": False, "error": f"Delete failed: {exc}"}
    return {"ok": True, "output": {"path": str(path), "deleted": True}}


# ── Process management tools ───────────────────────────────────────────

def _do_start_process(input_: Dict[str, Any]) -> Dict[str, Any]:
    cmd = input_.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return {"ok": False, "error": "Missing required `command`"}
    cwd_raw = input_.get("cwd")
    cwd = str(resolve_agent_path(cwd_raw)) if isinstance(cwd_raw, str) and cwd_raw else None
    label = input_.get("label")
    wait = input_.get("wait_ready", True)

    from .process_manager import get_manager
    mgr = get_manager()

    if wait:
        mp = mgr.start_and_wait(cmd, cwd=cwd, label=label, timeout=30)
    else:
        mp = mgr.start(cmd, cwd=cwd, label=label)

    result = mp.to_dict()
    # Include a few initial output lines for context.
    result["recent_output"] = mp.get_output(last_n=20)

    # If a port was detected, include a preview hint.
    if mp.detected_port:
        result["preview_url"] = f"http://localhost:{mp.detected_port}"

    return {"ok": True, "output": result}


def _do_stop_process(input_: Dict[str, Any]) -> Dict[str, Any]:
    proc_id = input_.get("process_id")
    if not isinstance(proc_id, str) or not proc_id:
        return {"ok": False, "error": "Missing required `process_id`"}

    from .process_manager import get_manager
    mgr = get_manager()

    if not mgr.stop(proc_id):
        return {"ok": False, "error": f"Process {proc_id} not found"}
    return {"ok": True, "output": {"process_id": proc_id, "stopped": True}}


def _do_list_processes(input_: Dict[str, Any]) -> Dict[str, Any]:
    from .process_manager import get_manager
    mgr = get_manager()
    mgr.cleanup_dead()  # remove finished processes
    procs = mgr.list_all()
    return {
        "ok": True,
        "output": {
            "count": len(procs),
            "processes": [p.to_dict() for p in procs],
        },
    }


def _do_get_process_output(input_: Dict[str, Any]) -> Dict[str, Any]:
    proc_id = input_.get("process_id")
    if not isinstance(proc_id, str) or not proc_id:
        return {"ok": False, "error": "Missing required `process_id`"}
    last_n = int(input_.get("last_n", 50))

    from .process_manager import get_manager
    mgr = get_manager()

    mp = mgr.get(proc_id)
    if mp is None:
        return {"ok": False, "error": f"Process {proc_id} not found"}

    return {
        "ok": True,
        "output": {
            "process_id": proc_id,
            "alive": mp.alive,
            "ready": mp.ready,
            "lines": mp.get_output(last_n=last_n),
        },
    }


def _do_open_preview(input_: Dict[str, Any]) -> Dict[str, Any]:
    """Signal tool — returns a payload the UI intercepts to open preview."""
    url = input_.get("url")
    if not isinstance(url, str) or not url.strip():
        return {"ok": False, "error": "Missing required `url`"}
    label = input_.get("label", "")
    return {
        "ok": True,
        "output": {
            "action": "open_preview",
            "url": url.strip(),
            "label": label,
        },
    }


# Silence unused warnings for shlex (kept for future cmd parsing).
_ = shlex
_ = subprocess
