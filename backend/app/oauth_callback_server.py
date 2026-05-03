"""OpenAI OAuth callback server + token persistence.

Adapted from OpenYak's openai_auth.py — uses asyncio.start_server on port
1455 (the only redirect_uri whitelisted for the Codex CLI client_id) and
saves tokens to a JSON file instead of the OS keyring (avoids the Windows
Credential Manager 2.5 KB blob size limit).
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .openai_oauth import (
    exchange_code,
    extract_account_id,
    extract_email,
    generate_auth_url,
)
from .paths import APP_ROOT

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────

OAUTH_CALLBACK_PORT = 1455
OAUTH_REDIRECT_URI = f"http://localhost:{OAUTH_CALLBACK_PORT}/auth/callback"

# Token file — simple JSON, no keyring. Avoids the Windows CredWrite 2.5KB
# limit that crashes on large OAuth bundles.
_TOKEN_FILE = APP_ROOT / "chatgpt_oauth_tokens.json"

# ── In-memory pending flows ─────────────────────────────────────────────

_pending_flows: Dict[str, Dict[str, Any]] = {}
_callback_server_task: Optional[asyncio.Task] = None


def _gc_pending() -> None:
    cutoff = time.time() - 600
    stale = [k for k, v in _pending_flows.items() if v["created_at"] < cutoff]
    for k in stale:
        _pending_flows.pop(k, None)


# ── Token file I/O ──────────────────────────────────────────────────────

def load_tokens() -> Optional[Dict[str, Any]]:
    """Load saved OAuth tokens from disk. Returns None if not found."""
    if not _TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        if data.get("access_token"):
            return data
        return None
    except Exception:
        return None


def save_tokens(data: Dict[str, Any]) -> None:
    """Save OAuth tokens to disk."""
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("ChatGPT OAuth tokens saved to %s", _TOKEN_FILE)


def clear_tokens() -> None:
    """Delete saved OAuth tokens."""
    if _TOKEN_FILE.exists():
        _TOKEN_FILE.unlink(missing_ok=True)
        logger.info("ChatGPT OAuth tokens cleared")


def has_tokens() -> bool:
    return load_tokens() is not None


def get_email() -> str:
    data = load_tokens()
    return (data or {}).get("email", "")


def get_expires_at_ms() -> int:
    data = load_tokens()
    return int((data or {}).get("expires_at_ms", 0))


def get_account_id() -> str:
    data = load_tokens()
    return (data or {}).get("account_id", "")


# ── OAuth flow completion (shared by callback server + manual paste) ────

async def complete_oauth_flow(code: str, state: str) -> str:
    """Exchange code for tokens, save to disk. Returns email on success."""
    flow = _pending_flows.pop(state, None)
    if not flow:
        raise RuntimeError("Invalid or expired state. Please try again.")

    tokens = await exchange_code(
        code=code,
        redirect_uri=flow["redirect_uri"],
        code_verifier=flow["code_verifier"],
    )

    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    id_token = tokens.get("id_token", "")
    expires_in = tokens.get("expires_in", 3600)
    expires_at_ms = int(time.time() * 1000) + expires_in * 1000

    if not access_token:
        raise RuntimeError("No access token received from OpenAI")

    account_id = extract_account_id(id_token) if id_token else ""
    email = extract_email(id_token) if id_token else ""

    save_tokens({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "expires_at_ms": expires_at_ms,
        "email": email,
    })

    return email


# ── Start login flow ───────────────────────────────────────────────────

async def start_login() -> Dict[str, str]:
    """Start a new OAuth PKCE flow. Returns {auth_url, state}."""
    _gc_pending()

    state = secrets.token_urlsafe(32)
    auth_url, code_verifier = generate_auth_url(OAUTH_REDIRECT_URI, state)

    _pending_flows[state] = {
        "code_verifier": code_verifier,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "created_at": time.time(),
    }

    # Start the one-shot callback listener
    await _start_callback_listener()

    return {"auth_url": auth_url, "state": state}


def get_flow_status(state: str) -> Dict[str, Any]:
    """Check if a pending flow has completed."""
    _gc_pending()
    if state in _pending_flows:
        return {"status": "pending", "error": None}
    # If the flow was popped from _pending_flows, it was completed
    # Check if tokens exist on disk
    if has_tokens():
        return {"status": "complete", "error": None}
    return {"status": "expired", "error": None}


# ── Async callback server (OpenYak style) ──────────────────────────────

async def _start_callback_listener() -> None:
    """Start a one-shot HTTP server on port 1455 for the OAuth callback."""
    global _callback_server_task

    if _callback_server_task and not _callback_server_task.done():
        _callback_server_task.cancel()

    async def _run_server():
        server_ref = [None]

        async def handle_connection(reader, writer):
            try:
                request_line = await asyncio.wait_for(reader.readline(), timeout=5)
                _, path, _ = request_line.decode().split(" ", 2)

                # Read and discard headers
                while True:
                    line = await reader.readline()
                    if line == b"\r\n" or line == b"\n" or not line:
                        break

                parsed = urlparse(path)
                params = parse_qs(parsed.query)

                code = params.get("code", [None])[0]
                state = params.get("state", [None])[0]
                error = params.get("error", [None])[0]

                if error:
                    error_desc = params.get("error_description", [""])[0]
                    html = _error_html(f"Authentication error: {error} — {error_desc}")
                    status = 400
                elif not code or not state:
                    html = _error_html("Missing code or state parameter")
                    status = 400
                else:
                    try:
                        email = await complete_oauth_flow(code, state)
                        html = _success_html(email)
                        status = 200
                    except Exception as e:
                        logger.error("OAuth callback failed: %s", e)
                        html = _error_html(str(e))
                        status = 500

                status_text = {200: "OK", 400: "Bad Request", 500: "Internal Server Error"}.get(status, "Error")
                body = html.encode()
                response = (
                    f"HTTP/1.1 {status} {status_text}\r\n"
                    f"Content-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                ).encode() + body
                writer.write(response)
                await writer.drain()
            except Exception as e:
                logger.error("Callback listener error: %s", e)
            finally:
                writer.close()
                if server_ref[0]:
                    server_ref[0].close()

        try:
            server = await asyncio.start_server(handle_connection, "127.0.0.1", OAUTH_CALLBACK_PORT)
            server_ref[0] = server
            logger.info("OAuth callback listener started on port %d", OAUTH_CALLBACK_PORT)
            async with server:
                await asyncio.wait_for(server.serve_forever(), timeout=600)
        except asyncio.TimeoutError:
            logger.info("OAuth callback listener timed out")
        except asyncio.CancelledError:
            logger.info("OAuth callback listener cancelled")
        except OSError as e:
            logger.warning("Could not start callback listener on port %d: %s", OAUTH_CALLBACK_PORT, e)

    _callback_server_task = asyncio.create_task(_run_server())


# ── HTML responses ──────────────────────────────────────────────────────

def _success_html(email: str) -> str:
    display = f" as <strong>{email}</strong>" if email else ""
    return f"""<!DOCTYPE html>
<html><head><title>StratForge AI — Signed in</title></head>
<body style="font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#0a0a0a;color:#e0e0e0;">
<div style="text-align:center;max-width:400px;padding:2rem;">
<div style="font-size:3rem;margin-bottom:1rem;">&#10003;</div>
<h1 style="font-size:1.25rem;margin-bottom:0.5rem;">Authentication Successful</h1>
<p style="color:#888;font-size:0.875rem;">Signed in{display}. ChatGPT subscription models are now available.</p>
<p style="color:#666;font-size:0.75rem;margin-top:1.5rem;">You can close this tab.</p>
</div></body></html>"""


def _error_html(message: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>StratForge AI — Sign-in failed</title></head>
<body style="font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#0a0a0a;color:#e0e0e0;">
<div style="text-align:center;max-width:400px;padding:2rem;">
<div style="font-size:3rem;margin-bottom:1rem;">&#10007;</div>
<h1 style="font-size:1.25rem;margin-bottom:0.5rem;">Authentication Failed</h1>
<p style="color:#f87171;font-size:0.875rem;">{message}</p>
<p style="color:#666;font-size:0.75rem;margin-top:1.5rem;">Please close this tab and try again.</p>
</div></body></html>"""
