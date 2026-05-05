"""Process Manager — tracks long-running child processes (dev servers, builds).

Singleton ``ProcessManager`` is imported lazily by the agent tools that need
it.  Each managed process gets:
  - a short id (``proc_<hex>``)
  - its command line and cwd
  - stdout/stderr captured into a fixed-size ring buffer
  - automatic "ready" detection via regex patterns (``listening on port …``)
  - port-in-use detection (so the AI can resolve conflicts)

All public methods are synchronous — async callers should wrap in
``asyncio.to_thread`` when appropriate.
"""
from __future__ import annotations

import asyncio
import collections
import os
import re
import secrets
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from .paths import AGENT_WORKSPACE

# ── Constants ──────────────────────────────────────────────────────────

OUTPUT_RING_SIZE = 500          # lines kept per process
READY_TIMEOUT_SEC = 30          # how long ``start_and_wait`` waits for ready
POLL_INTERVAL_SEC = 0.25        # how often we check for readiness

# Patterns that signal "dev server is ready".  Checked case-insensitively
# against every stdout/stderr line.  First match wins.
_READY_PATTERNS = [
    re.compile(r"ready\s+(?:on|in|at|—)\s+", re.I),
    re.compile(r"listening\s+(?:on\s+)?(?:port\s+)?\d+", re.I),
    re.compile(r"started\s+server\s+on", re.I),
    re.compile(r"local:\s+https?://", re.I),
    re.compile(r"➜\s+Local:", re.I),
    re.compile(r"compiled\s+(?:successfully|client)", re.I),
    re.compile(r"webpack\s+compiled", re.I),
    re.compile(r"vite\s+v\d.*?ready", re.I),
    re.compile(r"running\s+on\s+https?://", re.I),
    re.compile(r"Application startup complete", re.I),
    re.compile(r"Serving HTTP on", re.I),
]

# Regex to extract a port number from a line.
_PORT_RE = re.compile(r"(?:port\s+|localhost:|127\.0\.0\.1:|0\.0\.0\.0:)(\d{2,5})", re.I)


# ── Data classes ───────────────────────────────────────────────────────

@dataclass
class ManagedProcess:
    id: str
    command: str
    cwd: str
    proc: subprocess.Popen
    started_at: float = field(default_factory=time.time)
    ready: bool = False
    ready_at: Optional[float] = None
    detected_port: Optional[int] = None
    label: Optional[str] = None
    _output: Deque[str] = field(default_factory=lambda: collections.deque(maxlen=OUTPUT_RING_SIZE))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _reader_thread: Optional[threading.Thread] = None
    _ready_event: threading.Event = field(default_factory=threading.Event)

    # ── Output helpers ──────────────────────────────────────────────

    def _push_line(self, line: str) -> None:
        with self._lock:
            self._output.append(line)
        # Check readiness patterns on every line.
        if not self.ready:
            for pat in _READY_PATTERNS:
                if pat.search(line):
                    self.ready = True
                    self.ready_at = time.time()
                    self._ready_event.set()
                    break
        # Try to detect the port.
        if self.detected_port is None:
            pm = _PORT_RE.search(line)
            if pm:
                try:
                    self.detected_port = int(pm.group(1))
                except ValueError:
                    pass

    def get_output(self, last_n: int = 100) -> List[str]:
        with self._lock:
            lines = list(self._output)
        return lines[-last_n:]

    def get_full_output(self) -> str:
        return "\n".join(self.get_output(OUTPUT_RING_SIZE))

    # ── Status ──────────────────────────────────────────────────────

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    @property
    def exit_code(self) -> Optional[int]:
        return self.proc.poll()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "cwd": self.cwd,
            "pid": self.proc.pid,
            "alive": self.alive,
            "exit_code": self.exit_code,
            "ready": self.ready,
            "detected_port": self.detected_port,
            "label": self.label,
            "started_at": self.started_at,
            "uptime_sec": round(time.time() - self.started_at, 1),
        }

    def wait_ready(self, timeout: float = READY_TIMEOUT_SEC) -> bool:
        """Block until the process signals readiness or timeout."""
        return self._ready_event.wait(timeout=timeout)


# ── Reader thread ──────────────────────────────────────────────────────


def _reader_target(mp: ManagedProcess) -> None:
    """Background thread that reads merged stdout+stderr line by line."""
    stream = mp.proc.stdout  # redirected via PIPE + stderr=STDOUT
    if stream is None:
        return
    try:
        for raw_line in iter(stream.readline, b""):
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            mp._push_line(line)
    except Exception:
        pass


# ── Singleton manager ──────────────────────────────────────────────────


class ProcessManager:
    """Thread-safe singleton that tracks managed processes."""

    _instance: Optional["ProcessManager"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "ProcessManager":
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._processes: Dict[str, ManagedProcess] = {}
                cls._instance._lock = threading.Lock()
            return cls._instance

    # ── Core API ────────────────────────────────────────────────────

    def start(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        label: Optional[str] = None,
        env_extra: Optional[Dict[str, str]] = None,
    ) -> ManagedProcess:
        """Start a long-running process and begin capturing output."""
        resolved_cwd = Path(cwd) if cwd else AGENT_WORKSPACE
        if not resolved_cwd.exists():
            resolved_cwd.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["FORCE_COLOR"] = "1"
        if env_extra:
            env.update(env_extra)

        proc_id = f"proc_{secrets.token_hex(4)}"

        # Merge stderr into stdout so the reader thread sees everything.
        popen_kwargs: Dict[str, Any] = dict(
            args=command,
            cwd=str(resolved_cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            env=env,
        )
        # On Windows, create a new process group so we can kill the tree.
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(**popen_kwargs)

        mp = ManagedProcess(
            id=proc_id,
            command=command,
            cwd=str(resolved_cwd),
            proc=proc,
            label=label,
        )

        # Start the reader thread.
        t = threading.Thread(target=_reader_target, args=(mp,), daemon=True)
        t.start()
        mp._reader_thread = t

        with self._lock:
            self._processes[proc_id] = mp

        return mp

    def start_and_wait(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        label: Optional[str] = None,
        env_extra: Optional[Dict[str, str]] = None,
        timeout: float = READY_TIMEOUT_SEC,
    ) -> ManagedProcess:
        """Start a process, block until it's ready (or timeout)."""
        mp = self.start(command, cwd=cwd, label=label, env_extra=env_extra)
        mp.wait_ready(timeout=timeout)
        return mp

    def stop(self, proc_id: str) -> bool:
        """Kill a managed process. Returns True if found."""
        with self._lock:
            mp = self._processes.get(proc_id)
        if mp is None:
            return False
        self._kill(mp)
        return True

    def restart(self, proc_id: str) -> Optional[ManagedProcess]:
        """Kill and restart a process with the same command/cwd."""
        with self._lock:
            old = self._processes.get(proc_id)
        if old is None:
            return None
        cmd, cwd, label = old.command, old.cwd, old.label
        self._kill(old)
        with self._lock:
            del self._processes[proc_id]
        return self.start(cmd, cwd=cwd, label=label)

    def get(self, proc_id: str) -> Optional[ManagedProcess]:
        with self._lock:
            return self._processes.get(proc_id)

    def list_all(self) -> List[ManagedProcess]:
        with self._lock:
            return list(self._processes.values())

    def cleanup_dead(self) -> int:
        """Remove finished processes from tracking. Returns count removed."""
        removed = 0
        with self._lock:
            dead_ids = [pid for pid, mp in self._processes.items() if not mp.alive]
            for pid in dead_ids:
                del self._processes[pid]
                removed += 1
        return removed

    def stop_all(self) -> int:
        """Kill every managed process. Called on app shutdown."""
        with self._lock:
            procs = list(self._processes.values())
        count = 0
        for mp in procs:
            if mp.alive:
                self._kill(mp)
                count += 1
        with self._lock:
            self._processes.clear()
        return count

    def find_by_port(self, port: int) -> Optional[ManagedProcess]:
        """Find a process that detected the given port."""
        with self._lock:
            for mp in self._processes.values():
                if mp.detected_port == port and mp.alive:
                    return mp
        return None

    # ── Internals ───────────────────────────────────────────────────

    def _kill(self, mp: ManagedProcess) -> None:
        """Best-effort kill the process tree."""
        if not mp.alive:
            return
        try:
            if os.name == "nt":
                # On Windows, kill the entire process group.
                subprocess.call(
                    ["taskkill", "/F", "/T", "/PID", str(mp.proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.killpg(os.getpgid(mp.proc.pid), signal.SIGTERM)
                try:
                    mp.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(mp.proc.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError, PermissionError):
            pass
        try:
            mp.proc.kill()
        except Exception:
            pass


# ── Module-level accessor ──────────────────────────────────────────────

def get_manager() -> ProcessManager:
    """Return the global ProcessManager singleton."""
    return ProcessManager()
