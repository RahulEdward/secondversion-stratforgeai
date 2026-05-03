"""Ollama binary download + process lifecycle manager.

Mirrors the OpenYak reference implementation: downloads the standalone
Ollama binary from GitHub releases into the app's user-data dir, spawns
``ollama serve`` pointed at an app-owned models dir, and exposes a live
``base_url`` that provider code reads on every request.

Platform support:
  * windows-amd64  (zip, extracted to ``ollama.exe``)
  * darwin-amd64 / darwin-arm64 (single Mach-O binary)
  * linux-amd64

A singleton manager is created at FastAPI startup via :func:`init_manager`
and retrieved everywhere else via :func:`get_manager`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import httpx

from ..paths import OLLAMA_DIR, OLLAMA_MODELS_DIR

logger = logging.getLogger(__name__)

# ── Download sources ──────────────────────────────────────────────────────

_GITHUB_BASE = "https://github.com/ollama/ollama/releases/latest/download"
_DOWNLOAD_URLS: dict[str, str] = {
    "windows-amd64": f"{_GITHUB_BASE}/ollama-windows-amd64.zip",
    "darwin-arm64": f"{_GITHUB_BASE}/ollama-darwin",
    "darwin-amd64": f"{_GITHUB_BASE}/ollama-darwin",
    "linux-amd64": f"{_GITHUB_BASE}/ollama-linux-amd64",
}

_HEALTH_RETRIES = 30
_HEALTH_INTERVAL = 1.0  # seconds
_DEFAULT_PORT = 11434


def _platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = machine
    return f"{system}-{arch}"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _is_port_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


class OllamaManager:
    """Manages the Ollama binary and its ``ollama serve`` process."""

    def __init__(
        self,
        binary_dir: Path = OLLAMA_DIR,
        models_dir: Path = OLLAMA_MODELS_DIR,
    ) -> None:
        self.binary_dir = Path(binary_dir)
        self.models_dir = Path(models_dir)
        self._process: Optional[subprocess.Popen] = None
        self._port: int = _DEFAULT_PORT

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    @property
    def binary_path(self) -> Path:
        name = "ollama.exe" if sys.platform == "win32" else "ollama"
        return self.binary_dir / name

    @property
    def is_binary_installed(self) -> bool:
        return self.binary_path.exists()

    @property
    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    # ── Binary download ───────────────────────────────────────────────────

    async def download_binary(self) -> AsyncIterator[dict[str, Any]]:
        """Download the Ollama binary. Yields progress dicts.

        Progress dicts: ``{"status": str, "completed": int, "total": int}``
        or ``{"status": "error", "message": str}``.
        """
        key = _platform_key()
        url = _DOWNLOAD_URLS.get(key)
        if url is None:
            yield {"status": "error", "message": f"Unsupported platform: {key}"}
            return

        self.binary_dir.mkdir(parents=True, exist_ok=True)

        is_zip = url.endswith(".zip")
        download_path = self.binary_dir / (
            "ollama.zip" if is_zip else self.binary_path.name
        )

        yield {"status": "downloading", "completed": 0, "total": 0}

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=300.0
            ) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", 0))
                    completed = 0
                    with open(download_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 256):
                            f.write(chunk)
                            completed += len(chunk)
                            yield {
                                "status": "downloading",
                                "completed": completed,
                                "total": total,
                            }
        except Exception as exc:  # noqa: BLE001
            yield {"status": "error", "message": str(exc)}
            return

        if is_zip:
            yield {"status": "extracting"}
            try:
                await asyncio.to_thread(self._extract_zip, download_path)
                download_path.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                yield {"status": "error", "message": f"Extraction failed: {exc}"}
                return
        else:
            try:
                self.binary_path.chmod(0o755)
            except OSError:
                pass

        yield {"status": "done"}

    def _extract_zip(self, zip_path: Path) -> None:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(self.binary_dir)

    # ── Process lifecycle ─────────────────────────────────────────────────

    async def start(self) -> str:
        """Start ``ollama serve`` and return the base URL."""
        if self.is_running:
            logger.info("Ollama already running on port %d", self._port)
            return self.base_url

        if not self.is_binary_installed:
            raise RuntimeError("Ollama binary not installed — call setup first")

        # Pick port — prefer the default so existing clients keep working.
        port = self._port if _is_port_free(self._port) else _find_free_port()
        self._port = port

        self.models_dir.mkdir(parents=True, exist_ok=True)

        env = {
            **os.environ,
            "OLLAMA_HOST": f"127.0.0.1:{port}",
            "OLLAMA_MODELS": str(self.models_dir),
        }

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )

        self._process = subprocess.Popen(  # noqa: S603
            [str(self.binary_path), "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        logger.info(
            "Ollama process started (pid=%d, port=%d)", self._process.pid, port
        )

        await self._wait_for_health()
        return self.base_url

    async def stop(self) -> None:
        """Stop the Ollama process (graceful → force on Windows)."""
        if self._process is None:
            return

        logger.info("Stopping Ollama (pid=%d)…", self._process.pid)

        if sys.platform == "win32":
            try:
                subprocess.run(  # noqa: S603,S607
                    ["taskkill", "/PID", str(self._process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("taskkill failed: %s", exc)
        else:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()

        self._process = None
        logger.info("Ollama stopped")

    async def _wait_for_health(self) -> None:
        url = f"{self.base_url}/api/tags"
        async with httpx.AsyncClient(timeout=3.0) as client:
            for attempt in range(_HEALTH_RETRIES):
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        logger.info(
                            "Ollama health check passed (%d/%d)",
                            attempt + 1,
                            _HEALTH_RETRIES,
                        )
                        return
                except httpx.HTTPError:
                    pass

                if self._process and self._process.poll() is not None:
                    raise RuntimeError(
                        f"Ollama process exited with code {self._process.returncode}"
                    )
                await asyncio.sleep(_HEALTH_INTERVAL)

        raise RuntimeError(
            f"Ollama did not become ready after {_HEALTH_RETRIES} attempts"
        )

    # ── Version ───────────────────────────────────────────────────────────

    async def get_version(self) -> Optional[str]:
        if not self.is_running:
            return None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/version")
                if resp.status_code == 200:
                    return resp.json().get("version")
        except Exception:  # noqa: BLE001
            return None
        return None

    # ── Disk usage ────────────────────────────────────────────────────────

    def models_disk_usage_bytes(self) -> int:
        if not self.models_dir.exists():
            return 0
        total = 0
        for p in self.models_dir.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue
        return total

    # ── Uninstall ─────────────────────────────────────────────────────────

    async def uninstall(self, delete_models: bool = False) -> dict[str, Any]:
        if self.is_running:
            await self.stop()

        deleted: dict[str, Any] = {"binary": False, "models": False, "freed_bytes": 0}

        if self.binary_dir.exists():
            freed = 0
            for f in self.binary_dir.rglob("*"):
                try:
                    if f.is_file():
                        freed += f.stat().st_size
                except OSError:
                    continue
            shutil.rmtree(self.binary_dir, ignore_errors=True)
            deleted["binary"] = True
            deleted["freed_bytes"] += freed
            logger.info("Deleted Ollama binary dir: %s", self.binary_dir)

        if delete_models and self.models_dir.exists():
            freed = 0
            for f in self.models_dir.rglob("*"):
                try:
                    if f.is_file():
                        freed += f.stat().st_size
                except OSError:
                    continue
            shutil.rmtree(self.models_dir, ignore_errors=True)
            deleted["models"] = True
            deleted["freed_bytes"] += freed
            logger.info("Deleted Ollama models dir: %s", self.models_dir)

        return deleted

    # ── Status ────────────────────────────────────────────────────────────

    async def status(self) -> dict[str, Any]:
        version = await self.get_version() if self.is_running else None
        return {
            "binary_installed": self.is_binary_installed,
            "running": self.is_running,
            "port": self._port,
            "base_url": self.base_url if self.is_running else None,
            "version": version,
            "models_dir": str(self.models_dir),
            "disk_usage_bytes": self.models_disk_usage_bytes(),
        }


# ── Module-level singleton ────────────────────────────────────────────────

_manager: Optional[OllamaManager] = None


def init_manager() -> OllamaManager:
    """Create (or return existing) singleton manager."""
    global _manager
    if _manager is None:
        _manager = OllamaManager()
    return _manager


def get_manager() -> OllamaManager:
    """Return the singleton, creating it on first access."""
    return init_manager()
