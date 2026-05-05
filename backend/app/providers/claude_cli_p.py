"""Claude Code CLI provider — bridges to the `claude` command line tool using its WebSocket protocol.
Allows users to use their Free/Pro/Plus plan by delegating to their local Claude Code CLI session.

Architecture (mirrors the Companion app's cli-launcher + claude-adapter):
  1. Start a local WebSocket server on a random port.
  2. Spawn `claude --sdk-url ws://127.0.0.1:<port>/ws` — the CLI connects *to* our server.
  3. Translate the CLI's NDJSON protocol into StratForge's orchestrator frames.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    import websockets
    import websockets.server
except ImportError:
    websockets = None

from .base import ModelInfo, Provider, ProviderError

logger = logging.getLogger(__name__)

PROVIDER_NAME = "claude-cli"

# How long to wait for the CLI to connect its WebSocket (seconds).
CLI_CONNECT_TIMEOUT = 15
# How long to wait for new messages before declaring the turn done (seconds).
STREAM_IDLE_TIMEOUT = 60


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ClaudeCliSession:
    """Manages a single Claude CLI subprocess + its WebSocket bridge."""

    def __init__(self, session_id: str, cwd: str):
        self.session_id = session_id
        self.cwd = cwd
        self.port = _find_free_port()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.websocket = None
        self.process: Optional[subprocess.Popen] = None
        self.server = None
        self._connected = asyncio.Event()

    async def _ws_handler(self, websocket, path=None):
        """Called when the CLI connects to our WebSocket server."""
        logger.info("[claude-cli] CLI WebSocket connected (session=%s port=%d)", self.session_id, self.port)
        self.websocket = websocket
        self._connected.set()
        try:
            async for raw_message in websocket:
                # Claude CLI sends NDJSON — each line is a separate JSON object.
                for line in raw_message.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        self.queue.put_nowait(msg)
                    except json.JSONDecodeError:
                        logger.warning("[claude-cli] Unparseable NDJSON line: %.100s", line)
        except websockets.exceptions.ConnectionClosed:
            logger.info("[claude-cli] CLI WebSocket closed (session=%s)", self.session_id)
        except Exception as exc:
            logger.error("[claude-cli] WebSocket handler error: %s", exc)
        finally:
            self.websocket = None
            self._connected.clear()
            # Signal end to any waiting consumer
            self.queue.put_nowait({"type": "__ws_closed__"})

    async def start(self):
        """Start the WebSocket server and spawn the Claude CLI."""
        if not websockets:
            raise ProviderError(
                "The 'websockets' library is required. Run: pip install websockets"
            )

        # Start local WS server
        self.server = await websockets.serve(
            self._ws_handler, "127.0.0.1", self.port
        )
        logger.info("[claude-cli] WS server listening on ws://127.0.0.1:%d", self.port)

        # Resolve the `claude` binary
        claude_bin = shutil.which("claude")
        if not claude_bin:
            await self._cleanup_server()
            raise ProviderError(
                "Claude Code CLI not found in PATH. "
                "Install it with: npm install -g @anthropic-ai/claude-code  "
                "Then run: claude login"
            )

        # Build the command — matches the Companion app's cli-launcher.ts
        sdk_url = f"ws://127.0.0.1:{self.port}/ws"
        cmd = [
            claude_bin,
            "--sdk-url", sdk_url,
            "--print",
            "--output-format", "stream-json",
            "--input-format", "stream-json",
            # CRITICAL: without this flag, the CLI does NOT emit stream_event
            # messages with text deltas — streaming will appear blank!
            "--include-partial-messages",
            "--verbose",
            "-p", "",  # headless mode (no interactive prompt)
        ]

        logger.info("[claude-cli] Spawning: %s", " ".join(cmd))

        # On Windows, npm global .cmd scripts need shell=True
        is_win = sys.platform == "win32"
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=is_win,
            )
        except Exception as exc:
            await self._cleanup_server()
            raise ProviderError(f"Failed to spawn Claude CLI: {exc}") from exc

        # Drain stdout/stderr in background so the pipes don't block
        asyncio.get_event_loop().run_in_executor(None, self._drain_pipe, "stdout")
        asyncio.get_event_loop().run_in_executor(None, self._drain_pipe, "stderr")

        # Wait for the CLI to connect
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=CLI_CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            self._kill_process()
            await self._cleanup_server()
            raise ProviderError(
                f"Claude CLI did not connect within {CLI_CONNECT_TIMEOUT}s. "
                "Make sure you are logged in (run: claude login)"
            )

    def _drain_pipe(self, name: str):
        """Read and log subprocess stdout/stderr so the pipe buffers don't fill."""
        pipe = getattr(self.process, name, None)
        if pipe is None:
            return
        try:
            for line_bytes in iter(pipe.readline, b""):
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                if line:
                    logger.debug("[claude-cli:%s] %s", name, line)
        except Exception:
            pass

    def _kill_process(self):
        """Terminate the subprocess."""
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass
        self.process = None

    async def _cleanup_server(self):
        """Shut down the WebSocket server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def stop(self):
        """Full cleanup — process + server."""
        self._kill_process()
        await self._cleanup_server()

    async def send(self, msg: dict):
        """Send a JSON message to the CLI via WebSocket."""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps(msg))
            except Exception as exc:
                logger.error("[claude-cli] Send error: %s", exc)

    def alive(self) -> bool:
        """Check if the CLI process is still running."""
        return self.process is not None and self.process.poll() is None


# ── Session pool ──────────────────────────────────────────────────────────

_active_sessions: Dict[str, ClaudeCliSession] = {}


async def get_or_create_session(session_id: str, cwd: str) -> ClaudeCliSession:
    """Get existing session or create a new one."""
    existing = _active_sessions.get(session_id)
    if existing and existing.alive() and existing.websocket is not None:
        return existing

    # Clean up stale session if any
    if existing:
        await existing.stop()
        _active_sessions.pop(session_id, None)

    sess = ClaudeCliSession(session_id, cwd)
    await sess.start()
    _active_sessions[session_id] = sess
    return sess


# ── Provider ──────────────────────────────────────────────────────────────


class ClaudeCliProvider(Provider):
    name = PROVIDER_NAME
    kind = "local"
    label = "Claude Code (CLI)"
    handles_tool_execution = True

    def cli_installed(self) -> bool:
        """True if the `claude` binary is found on PATH."""
        return bool(shutil.which("claude"))

    def has_credential(self) -> bool:
        """True if Claude CLI auth files exist (user has logged in).
        Mirrors companion's claude-container-auth.ts logic."""
        # Check env vars first
        for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                    "CLAUDE_CODE_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
            if os.environ.get(var):
                return True

        # Check auth files in ~/.claude/
        home = Path.home()
        claude_dir = home / ".claude"
        auth_files = [
            claude_dir / ".credentials.json",
            claude_dir / "auth.json",
            claude_dir / ".auth.json",
            claude_dir / "credentials.json",
        ]
        return any(f.exists() for f in auth_files)

    async def list_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(
                id="claude-sonnet-4-20250514",
                label="Claude Sonnet 4 (CLI)",
                context_window=200_000,
                description="Uses your Claude Code subscription",
            ),
            ModelInfo(
                id="claude-3-5-sonnet-20241022",
                label="Claude 3.5 Sonnet (CLI)",
                context_window=200_000,
                description="Uses your Claude Code subscription",
            ),
            ModelInfo(
                id="claude-3-5-haiku-20241022",
                label="Claude 3.5 Haiku (CLI)",
                context_window=200_000,
                description="Uses your Claude Code subscription",
            ),
        ]

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        system: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        if not session_id:
            yield {"type": "error", "message": "session_id is required for Claude Code CLI"}
            return

        # Acquire / create the CLI session
        try:
            cwd = os.getcwd()
            cli_session = await get_or_create_session(session_id, cwd)
        except ProviderError as exc:
            yield {"type": "error", "message": str(exc)}
            return
        except Exception as exc:
            yield {"type": "error", "message": f"Claude CLI init failed: {exc}"}
            return

        # Drain any stale messages from the queue
        while not cli_session.queue.empty():
            try:
                cli_session.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # ── Build the user message payload ────────────────────────────
        latest_msg = messages[-1] if messages else {"role": "user", "content": ""}
        content = latest_msg.get("content", "")

        # Flatten content blocks to text
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") in ("text", "input_text"):
                        text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = " ".join(text_parts)

        # Prepend system prompt for the first message
        if system and len(messages) <= 1:
            content = f"{system}\n\n{content}"

        # Send user message to CLI (same shape as companion's claude-adapter.ts)
        await cli_session.send({
            "type": "user",
            "message": {"role": "user", "content": content},
            "parent_tool_use_id": None,
            "session_id": "",
        })

        # ── Stream responses ──────────────────────────────────────────
        turn_done = False
        while not turn_done:
            try:
                msg = await asyncio.wait_for(
                    cli_session.queue.get(), timeout=STREAM_IDLE_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.warning("[claude-cli] Stream idle timeout (%ds)", STREAM_IDLE_TIMEOUT)
                break

            mtype = msg.get("type")

            if mtype == "__ws_closed__":
                yield {"type": "error", "message": "Claude CLI disconnected unexpectedly"}
                break

            elif mtype == "system":
                # system.init carries session metadata — we can ignore it.
                # system.status / compact_boundary are informational.
                subtype = msg.get("subtype")
                if subtype == "init":
                    logger.info(
                        "[claude-cli] Session init: model=%s cwd=%s",
                        msg.get("model"), msg.get("cwd"),
                    )

            elif mtype == "stream_event":
                # Text streaming from Claude — this is the main content path.
                event = msg.get("event", {})
                etype = event.get("type")

                if etype == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield {"type": "text", "delta": text}
                elif etype == "text_delta":
                    # Simplified streaming format
                    text = event.get("text", "")
                    if text:
                        yield {"type": "text", "delta": text}

            elif mtype == "control_request":
                req = msg.get("request", {})
                if req.get("subtype") == "can_use_tool":
                    tool_name = req.get("tool_name", "")
                    tool_input = req.get("input", {})
                    request_id = msg.get("request_id", "")

                    # Notify UI about the tool use
                    yield {
                        "type": "tool_use",
                        "id": request_id,
                        "name": tool_name,
                        "input": tool_input,
                    }

                    # Auto-allow the tool so the CLI executes it
                    await cli_session.send({
                        "type": "control_response",
                        "response": {
                            "subtype": "success",
                            "request_id": request_id,
                            "response": {
                                "behavior": "allow",
                                "updatedInput": {},
                            },
                        },
                    })

                    # Yield tool_result so the UI marks the card as complete
                    yield {
                        "type": "tool_result",
                        "tool_use_id": request_id,
                        "ok": True,
                        "output": "(executed by Claude CLI)",
                    }

            elif mtype == "tool_progress":
                # Tool progress events — informational, skip.
                pass

            elif mtype == "tool_use_summary":
                # Summary of tool use — informational, skip.
                pass

            elif mtype == "result":
                # The full result message means the assistant turn is complete.
                result_data = msg.get("result", msg)
                # Extract any final text from result if present
                if isinstance(result_data, dict):
                    result_content = result_data.get("content", [])
                    if isinstance(result_content, list):
                        for block in result_content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                # Don't re-yield if we already streamed it
                                pass
                turn_done = True

            elif mtype == "assistant":
                # Assistant turn completed — the CLI has finished responding.
                # After this, no more content is expected for this turn.
                turn_done = True

            elif mtype == "auth_status":
                # Authentication status — check if login is needed
                auth_status = msg.get("status", "")
                if auth_status in ("unauthenticated", "expired"):
                    yield {
                        "type": "error",
                        "message": "Claude CLI not authenticated. Run 'claude login' in your terminal.",
                    }
                    turn_done = True

            elif mtype == "error":
                yield {"type": "error", "message": msg.get("message", "Unknown CLI error")}
                turn_done = True

            elif mtype == "keep_alive":
                # Keepalive — ignore
                pass

            elif mtype == "user":
                # CLI echoes user messages back — ignore (same as companion)
                pass

            elif mtype == "rate_limit_event":
                # Rate limit info — ignore (same as companion)
                pass

            else:
                # Unknown message types — log for debugging
                logger.debug("[claude-cli] Unhandled message type: %s", mtype)
