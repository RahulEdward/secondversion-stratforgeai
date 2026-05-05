"""ChatGPT subscription provider — uses OAuth Bearer tokens from Codex-style flow.

Reads tokens from the JSON file managed by oauth_callback_server (not keyring).
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .. import oauth_callback_server
from ..openai_oauth import is_token_expired, refresh_access_token
from .base import ModelInfo, Provider, ProviderError

logger = logging.getLogger(__name__)

WHAM_BASE_URL = "https://chatgpt.com/backend-api/codex"

PROVIDER_NAME = "chatgpt-subscription"

_SUBSCRIPTION_MODELS: List[ModelInfo] = [
    ModelInfo(id="gpt-5.4", label="GPT-5.4", context_window=1_050_000, description="Subscription"),
    ModelInfo(id="gpt-5.3-codex", label="GPT-5.3 Codex", context_window=1_047_576, description="Subscription"),
    ModelInfo(id="gpt-5.2", label="GPT-5.2", context_window=1_047_576, description="Subscription"),
    ModelInfo(id="gpt-5.2-code", label="GPT-5.2 Code", context_window=1_047_576, description="Subscription"),
    ModelInfo(id="gpt-5.1-codex", label="GPT-5.1 Codex", context_window=1_047_576, description="Subscription"),
    ModelInfo(id="gpt-5.1-codex-max", label="GPT-5.1 Codex Max", context_window=1_047_576, description="Subscription"),
    ModelInfo(id="gpt-5.1-codex-mini", label="GPT-5.1 Codex Mini", context_window=200_000, description="Subscription"),
]


class ChatGPTSubscriptionProvider(Provider):
    name = PROVIDER_NAME
    kind = "subscription"
    label = "ChatGPT Subscription"

    def has_credential(self) -> bool:
        return oauth_callback_server.has_tokens()

    def account_email(self) -> str:
        return oauth_callback_server.get_email()

    async def current_token(self) -> Optional[str]:
        """Return a valid access token, refreshing if needed."""
        data = oauth_callback_server.load_tokens()
        if not data:
            return None
        expires_at_ms = int(data.get("expires_at_ms", 0))
        if not is_token_expired(expires_at_ms):
            return data["access_token"]
        # Try refresh
        refresh_token = data.get("refresh_token", "")
        if not refresh_token:
            return None
        try:
            import time
            new_tokens = await refresh_access_token(refresh_token)
            new_expires_at_ms = int(time.time() * 1000) + int(new_tokens.get("expires_in", 3600)) * 1000
            data["access_token"] = new_tokens["access_token"]
            data["refresh_token"] = new_tokens.get("refresh_token", refresh_token)
            data["expires_at_ms"] = new_expires_at_ms
            oauth_callback_server.save_tokens(data)
            return data["access_token"]
        except Exception:
            return None

    async def list_models(self) -> List[ModelInfo]:
        token = await self.current_token()
        if not token:
            raise ProviderError("Not signed in to ChatGPT — open Settings → Providers to connect.")
        return list(_SUBSCRIPTION_MODELS)

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        system: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        access_token = await self.current_token()
        if not access_token:
            yield {"type": "error", "message": "Not signed in to ChatGPT. Open Settings → Providers to connect."}
            return

        account_id = oauth_callback_server.get_account_id()
        raw_model = (model or "gpt-5.2").removeprefix(f"{PROVIDER_NAME}/")

        # Convert orchestrator messages (Anthropic-shaped content blocks) into
        # the OpenAI Responses API ``input`` array, preserving tool_use /
        # tool_result so the model sees the running tool conversation.
        input_items: List[Dict[str, Any]] = _to_responses_input(messages)

        # Anthropic-shaped tool defs → Responses API ``tools`` array.
        api_tools: List[Dict[str, Any]] = _to_responses_tools(tools or [])

        body: Dict[str, Any] = {
            "model": raw_model,
            "store": False,
            "stream": True,
            "input": input_items,
        }
        if system:
            body["instructions"] = system
        if api_tools:
            body["tools"] = api_tools
            # Let the model decide when to call tools; never force a specific one.
            body["tool_choice"] = "auto"
            body["parallel_tool_calls"] = True

        headers = {
            "Authorization": f"Bearer {access_token}",
            "ChatGPT-Account-Id": account_id,
            "Content-Type": "application/json",
            "OpenAI-Beta": "responses=experimental",
        }

        # Track in-flight function calls keyed by call_id. The Responses API
        # streams arguments in deltas — we accumulate them and emit one
        # ``tool_use`` frame to the orchestrator when the call is complete.
        pending: Dict[str, Dict[str, str]] = {}

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    f"{WHAM_BASE_URL}/responses",
                    json=body,
                    headers=headers,
                ) as resp:
                    if resp.status_code == 401:
                        yield {"type": "error", "message": "ChatGPT session expired. Re-connect in Settings → Providers."}
                        return
                    if resp.status_code != 200:
                        text = (await resp.aread()).decode("utf-8", errors="replace")
                        yield {"type": "error", "message": f"ChatGPT API error {resp.status_code}: {text[:300]}"}
                        return

                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        etype = event.get("type", "")

                        if etype == "response.output_text.delta":
                            delta = event.get("delta", "")
                            if delta:
                                yield {"type": "text", "delta": delta}

                        elif etype == "response.output_item.added":
                            item = event.get("item") or {}
                            if item.get("type") == "function_call":
                                cid = item.get("call_id") or item.get("id") or ""
                                if cid:
                                    pending[cid] = {
                                        "name": item.get("name", ""),
                                        "args": item.get("arguments") or "",
                                    }

                        elif etype == "response.function_call_arguments.delta":
                            cid = event.get("item_id") or event.get("call_id") or ""
                            delta = event.get("delta", "")
                            if cid and delta:
                                bucket = pending.setdefault(cid, {"name": "", "args": ""})
                                bucket["args"] = (bucket.get("args") or "") + delta

                        elif etype == "response.function_call_arguments.done":
                            cid = event.get("item_id") or event.get("call_id") or ""
                            bucket = pending.get(cid, {})
                            args_str = event.get("arguments") or bucket.get("args") or ""
                            name = bucket.get("name", "")
                            try:
                                input_dict = json.loads(args_str) if args_str else {}
                            except json.JSONDecodeError:
                                input_dict = {"_raw_arguments": args_str}
                            if name:
                                yield {
                                    "type": "tool_use",
                                    "id": cid,
                                    "name": name,
                                    "input": input_dict,
                                }
                            pending.pop(cid, None)

                        elif etype == "response.output_item.done":
                            # Fallback: some streams skip the dedicated
                            # ``…arguments.done`` event and emit the full
                            # function_call here. Flush any still-pending
                            # buckets we have buffered.
                            item = event.get("item") or {}
                            if item.get("type") == "function_call":
                                cid = item.get("call_id") or item.get("id") or ""
                                if cid in pending:
                                    bucket = pending[cid]
                                    args_str = item.get("arguments") or bucket.get("args") or ""
                                    name = item.get("name") or bucket.get("name", "")
                                    try:
                                        input_dict = (
                                            json.loads(args_str) if args_str else {}
                                        )
                                    except json.JSONDecodeError:
                                        input_dict = {"_raw_arguments": args_str}
                                    if name:
                                        yield {
                                            "type": "tool_use",
                                            "id": cid,
                                            "name": name,
                                            "input": input_dict,
                                        }
                                    pending.pop(cid, None)

                        elif etype == "response.error":
                            err = event.get("error", {})
                            msg = err.get("message") if isinstance(err, dict) else str(err)
                            yield {"type": "error", "message": f"ChatGPT error: {msg}"}
                            return

                        elif etype == "response.completed":
                            return
        except httpx.HTTPError as exc:
            yield {"type": "error", "message": f"ChatGPT network error: {exc}"}


# ── Shape converters ──────────────────────────────────────────────────────


def _to_responses_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Anthropic-shaped tool defs to OpenAI Responses API shape.

    Anthropic: ``{name, description, input_schema}``
    Responses: ``{type: "function", name, description, parameters, strict}``
    """
    out: List[Dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        if not name:
            continue
        out.append(
            {
                "type": "function",
                "name": name,
                "description": t.get("description", "") or "",
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
                "strict": False,
            }
        )
    return out


def _tool_result_text(content: Any) -> str:
    """Flatten an Anthropic tool_result content payload to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(str(c.get("text", "")))
                else:
                    parts.append(json.dumps(c, default=str, ensure_ascii=False))
            else:
                parts.append(str(c))
        return "".join(parts)
    return str(content)


def _to_responses_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert orchestrator history (Anthropic content blocks) to the
    Responses API ``input`` array. Preserves tool_use / tool_result so the
    model sees the full running conversation, not just the user text."""
    out: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        blocks = m.get("content", [])
        if isinstance(blocks, str):
            blocks = [{"type": "text", "text": blocks}]
        if not isinstance(blocks, list):
            continue

        # Group consecutive text blocks per message to keep one bubble per turn.
        text_parts: List[str] = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            btype = b.get("type")
            if btype == "text":
                text_parts.append(str(b.get("text", "")))
            elif btype == "tool_use" and role == "assistant":
                # Flush buffered text first so order is preserved.
                if text_parts:
                    out.append(
                        {
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "".join(text_parts)}],
                        }
                    )
                    text_parts = []
                out.append(
                    {
                        "type": "function_call",
                        "call_id": str(b.get("id", "")),
                        "name": str(b.get("name", "")),
                        "arguments": json.dumps(b.get("input", {}), ensure_ascii=False),
                    }
                )
            elif btype == "tool_result":
                if text_parts:
                    out.append(
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": "".join(text_parts)}],
                        }
                    )
                    text_parts = []
                out.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(b.get("tool_use_id", "")),
                        "output": _tool_result_text(b.get("content", "")),
                    }
                )

        # Trailing buffered text.
        if text_parts and role in ("user", "assistant"):
            content_type = "input_text" if role == "user" else "output_text"
            out.append(
                {
                    "role": role,
                    "content": [{"type": content_type, "text": "".join(text_parts)}],
                }
            )
    return out
