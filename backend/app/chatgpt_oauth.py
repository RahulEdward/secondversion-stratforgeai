"""ChatGPT subscription OAuth (PKCE auth-code flow).

Mirrors the Codex CLI's public OAuth client — same constants the OpenYak
project uses (see https://github.com/openyak/openyak) which are in turn
lifted from the open-source Codex CLI. This is an **unofficial** path: the
client_id is public (documented in the CLI source) but OpenAI does not
publish this as a supported third-party auth mechanism. Tokens may be
revoked at any time and the flow may change without notice.

Flow (PKCE, S256):
  1. Frontend calls POST /api/auth/chatgpt/start
  2. Backend generates code_verifier/challenge under a flow_id
  3. Backend returns { flow_id, authorize_url }
  4. Electron / browser opens authorize_url on auth.openai.com
  5. User approves; OpenAI redirects to /api/auth/chatgpt/callback?code=...
  6. Callback exchanges code+verifier for tokens, decodes the id_token JWT
     to extract chatgpt_account_id + email, saves to keyring, marks the
     flow complete.
  7. Frontend polls /api/auth/chatgpt/status/{flow_id}; once 'complete',
     refreshes the provider list so the ChatGPT-subscription card shows
     as connected.

Token storage mirrors the Claude flow: one blob in the OS keyring under
SUBSCRIPTION_KEY. The blob contains access/refresh/expiry + the extracted
account_id + email so the UI can show "Signed in as foo@bar.com".
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets as pysecrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

from . import secrets

logger = logging.getLogger(__name__)

# ── OpenAI OAuth constants (public Codex CLI client_id) ─────────────────────
AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
SCOPES = "openid profile email offline_access"
AUDIENCE = "https://api.openai.com/v1"

# Backend callback — must match the redirect_uri we send AND what the public
# client_id has registered. The Codex CLI client allows loopback redirects,
# so http://127.0.0.1:8765/... works.
CALLBACK_PATH = "/api/auth/chatgpt/callback"

# Keyring slot for the tokens + account metadata blob.
SUBSCRIPTION_KEY = "chatgpt-subscription"

# In-flight flows expire after this many seconds.
FLOW_TTL_SECONDS = 600


def _b64url(raw: bytes) -> str:
    """URL-safe base64 without padding, per RFC 7636."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _generate_pkce() -> tuple[str, str]:
    """Return (verifier, challenge) for PKCE S256."""
    verifier = _b64url(pysecrets.token_bytes(32))
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = _b64url(digest)
    return verifier, challenge


@dataclass
class Flow:
    """In-memory state for a single in-progress ChatGPT OAuth flow."""

    flow_id: str
    verifier: str
    created_at: float
    status: str = "pending"  # pending | complete | error
    error: Optional[str] = None
    completed_at: Optional[float] = None


class FlowRegistry:
    """Per-process registry of in-flight ChatGPT OAuth flows."""

    def __init__(self) -> None:
        self._flows: Dict[str, Flow] = {}

    def start(self) -> Flow:
        verifier, _ = _generate_pkce()
        flow = Flow(
            flow_id=uuid.uuid4().hex,
            verifier=verifier,
            created_at=time.time(),
        )
        self._flows[flow.flow_id] = flow
        self._gc()
        return flow

    def get(self, flow_id: str) -> Optional[Flow]:
        self._gc()
        return self._flows.get(flow_id)

    def mark_complete(self, flow_id: str) -> None:
        f = self._flows.get(flow_id)
        if f is None:
            return
        f.status = "complete"
        f.completed_at = time.time()

    def mark_error(self, flow_id: str, msg: str) -> None:
        f = self._flows.get(flow_id)
        if f is None:
            return
        f.status = "error"
        f.error = msg
        f.completed_at = time.time()

    def _gc(self) -> None:
        cutoff = time.time() - FLOW_TTL_SECONDS
        expired = [k for k, v in self._flows.items() if v.created_at < cutoff]
        for k in expired:
            self._flows.pop(k, None)


# Module-level registry shared by the routes + callback handler.
flow_registry = FlowRegistry()


def build_authorize_url(verifier: str, state: str, callback_url: str) -> str:
    """Build the full auth.openai.com consent URL with Codex-specific params.

    The three extra params (`id_token_add_organizations`,
    `codex_cli_simplified_flow`, `originator`) are what the real Codex CLI
    sends — OpenAI's auth server expects them for this client_id to return
    a usable id_token with chatgpt_account_id inside.
    """
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "codex",
    }
    from urllib.parse import urlencode

    return f"{AUTH_URL}?{urlencode(params)}"


# ── JWT id_token decoding (unverified) ──────────────────────────────────────


def _decode_jwt_payload(id_token: str) -> Dict[str, Any]:
    """Decode the middle segment of a JWT without verifying the signature.

    We trust the token because we just received it over TLS directly from
    OpenAI's token endpoint. We only need the claims inside to extract
    chatgpt_account_id + email.
    """
    parts = id_token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid JWT: expected at least 2 parts")
    payload_b64 = parts[1]
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def extract_account_id(id_token: str) -> str:
    """Pull chatgpt_account_id out of the id_token JWT.

    Tries the four known locations in priority order — OpenAI's payload
    shape varies by account type (Plus vs Pro vs Team vs Enterprise).
    """
    payload = _decode_jwt_payload(id_token)
    auth_info = payload.get("https://api.openai.com/auth", {})

    # Tier 1: top-level auth claim (most common for ChatGPT Plus/Pro)
    acc = auth_info.get("chatgpt_account_id")
    if acc:
        return acc

    # Tier 2 + 3: inside organizations[0]
    orgs = auth_info.get("organizations", [])
    if orgs:
        acc = orgs[0].get("chatgpt_account_id") or orgs[0].get("id")
        if acc:
            return acc

    # Tier 4: top-level JWT claim
    acc = payload.get("chatgpt_account_id")
    if acc:
        return acc

    raise ValueError("No chatgpt_account_id found in id_token")


def extract_email(id_token: str) -> str:
    """Pull the email out of the id_token JWT (best-effort)."""
    try:
        payload = _decode_jwt_payload(id_token)
        return payload.get("email", "") or ""
    except Exception:
        return ""


# ── Token bundle (keyring-backed) ───────────────────────────────────────────


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float  # epoch seconds
    account_id: str = ""
    email: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "account_id": self.account_id,
            "email": self.email,
            "raw": self.raw,
        })

    @classmethod
    def from_json(cls, blob: str) -> Optional["TokenBundle"]:
        try:
            d = json.loads(blob)
            return cls(
                access_token=d["access_token"],
                refresh_token=d.get("refresh_token"),
                expires_at=float(d.get("expires_at", 0)),
                account_id=d.get("account_id", "") or "",
                email=d.get("email", "") or "",
                raw=d.get("raw", {}),
            )
        except Exception:
            return None

    @property
    def expired(self) -> bool:
        # 5-minute safety margin (OpenYak uses the same)
        return time.time() + 300 >= self.expires_at


def load_tokens() -> Optional[TokenBundle]:
    blob = secrets.get_key(SUBSCRIPTION_KEY)
    if not blob:
        return None
    return TokenBundle.from_json(blob)


def save_tokens(t: TokenBundle) -> None:
    secrets.set_key(SUBSCRIPTION_KEY, t.to_json())


def clear_tokens() -> bool:
    return secrets.delete_key(SUBSCRIPTION_KEY)


# ── Token exchange + refresh ────────────────────────────────────────────────


async def exchange_code(code: str, verifier: str, callback_url: str) -> TokenBundle:
    """Trade an authorization code for access + refresh + id tokens.

    Form-urlencoded POST (OpenAI's token endpoint rejects JSON).
    """
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": callback_url,
        "code_verifier": verifier,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"ChatGPT token exchange failed: {resp.status_code} {resp.text[:300]}"
        )
    body = resp.json()
    expires_in = int(body.get("expires_in", 3600))
    id_token = body.get("id_token", "")
    try:
        account_id = extract_account_id(id_token) if id_token else ""
    except Exception as exc:
        logger.warning("Could not extract chatgpt_account_id: %s", exc)
        account_id = ""
    email = extract_email(id_token) if id_token else ""
    return TokenBundle(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token"),
        expires_at=time.time() + expires_in,
        account_id=account_id,
        email=email,
        raw=body,
    )


async def refresh_tokens(bundle: TokenBundle) -> TokenBundle:
    """Use the refresh_token to mint a new access_token."""
    if not bundle.refresh_token:
        raise RuntimeError("No refresh_token — user must re-authenticate")
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": bundle.refresh_token,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"ChatGPT token refresh failed: {resp.status_code} {resp.text[:300]}"
        )
    body = resp.json()
    expires_in = int(body.get("expires_in", 3600))
    new_bundle = TokenBundle(
        access_token=body["access_token"],
        # Rotate if the response includes a new one; keep previous otherwise.
        refresh_token=body.get("refresh_token") or bundle.refresh_token,
        expires_at=time.time() + expires_in,
        account_id=bundle.account_id,
        email=bundle.email,
        raw=body,
    )
    save_tokens(new_bundle)
    return new_bundle


async def get_valid_access_token() -> Optional[str]:
    """Return a non-expired access token, auto-refreshing if needed.
    Returns None if the user isn't signed in or the refresh failed."""
    bundle = load_tokens()
    if bundle is None:
        return None
    if not bundle.expired:
        return bundle.access_token
    try:
        refreshed = await refresh_tokens(bundle)
        return refreshed.access_token
    except Exception as exc:
        logger.warning("ChatGPT subscription token refresh failed: %s", exc)
        return None
