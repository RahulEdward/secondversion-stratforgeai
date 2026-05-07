"""ChatLLM adapter — bridges Vibe-Trading's AgentLoop to StratForge's providers.

Vibe-Trading's AgentLoop expects a ChatLLM with:
  - .chat(messages, tools, timeout) -> LLMResponse
  - .stream_chat(messages, tools, on_text_chunk, timeout) -> LLMResponse

Where messages are OpenAI format:
  [{"role": "system"|"user"|"assistant"|"tool", "content": str|list, ...}]

And tools are OpenAI function-calling format:
  [{"type": "function", "function": {"name", "description", "parameters"}}]

This module routes those calls to StratForge's configured provider
(Anthropic / OpenAI / Google / Ollama) using the user's stored API key from
keyring. Provider and model are resolved from the active session passed in
via the module-level set_active_session() helper before AgentLoop runs.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Data classes matching Vibe-Trading's original shape ──────────────────

@dataclass
class ToolCallRequest:
    """Tool call request returned by the LLM."""

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """LLM response returned to AgentLoop."""

    content: Optional[str] = None
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    reasoning_content: Optional[str] = None
    finish_reason: str = "stop"

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


# ── Active session context (set before AgentLoop.run) ────────────────────

_active: Dict[str, Optional[str]] = {
    "provider": None,
    "model": None,
}


def set_active_provider(provider: Optional[str], model: Optional[str]) -> None:
    """Record the provider + model to use for subsequent ChatLLM calls."""
    _active["provider"] = provider
    _active["model"] = model


def clear_active_provider() -> None:
    """Clear the active provider after a run finishes."""
    _active["provider"] = None
    _active["model"] = None


# Legacy alias kept in case anything else imports the old names.
set_active = set_active_provider


def get_active() -> tuple[Optional[str], Optional[str]]:
    """Return the currently active (provider, model) pair."""
    return _active["provider"], _active["model"]


# ── Message / tool format converters ─────────────────────────────────────

def _split_system(messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """Pull out the leading system message; return (system_text, rest)."""
    if messages and messages[0].get("role") == "system":
        system = messages[0].get("content", "") or ""
        return str(system), messages[1:]
    return "", list(messages)


def _openai_to_anthropic_messages(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Translate OpenAI-format messages to Anthropic's content-block format.

    OpenAI has:
      {role: 'assistant', content: str|None, tool_calls: [{id, function: {name, arguments}}]}
      {role: 'tool', tool_call_id, content: str}

    Anthropic has:
      {role: 'assistant', content: [{type: 'text', text}, {type: 'tool_use', id, name, input}]}
      {role: 'user', content: [{type: 'tool_result', tool_use_id, content}]}
    """
    out: List[Dict[str, Any]] = []
    pending_tool_results: List[Dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role")

        if role == "tool":
            # Collect tool results — they ride inside the next user turn
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id", ""),
                "content": str(msg.get("content", "")),
            })
            continue

        # If we had pending tool results, flush them as a user turn first
        if pending_tool_results:
            out.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

        if role == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                out.append({"role": "user", "content": content})
            elif isinstance(content, list):
                out.append({"role": "user", "content": content})

        elif role == "assistant":
            blocks: List[Dict[str, Any]] = []
            text = msg.get("content")
            if isinstance(text, str) and text:
                blocks.append({"type": "text", "text": text})
            for tc in msg.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}") or "{}")
                except json.JSONDecodeError:
                    args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": args,
                })
            if blocks:
                out.append({"role": "assistant", "content": blocks})

    # Flush any trailing tool results
    if pending_tool_results:
        out.append({"role": "user", "content": pending_tool_results})

    return out


def _openai_tools_to_anthropic(
    tools: Optional[List[Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    """Convert OpenAI-format tool defs to Anthropic-format."""
    if not tools:
        return None
    out = []
    for t in tools:
        fn = t.get("function", {})
        out.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return out


def _gemini_tools_from_openai(
    tools: Optional[List[Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    """Convert OpenAI-format tool defs to Gemini's function declarations."""
    if not tools:
        return None
    declarations = []
    for t in tools:
        fn = t.get("function", {})
        declarations.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return [{"function_declarations": declarations}]


def _gemini_contents_from_openai(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Translate OpenAI-format messages to Gemini 'contents' format."""
    contents: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            text = content if isinstance(content, str) else json.dumps(content)
            contents.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            parts: List[Dict[str, Any]] = []
            if isinstance(content, str) and content:
                parts.append({"text": content})
            for tc in msg.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}") or "{}")
                except json.JSONDecodeError:
                    args = {}
                parts.append({
                    "function_call": {
                        "name": fn.get("name", ""),
                        "args": args,
                    }
                })
            if parts:
                contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            # Gemini expects function_response as a user turn
            try:
                response_payload = json.loads(msg.get("content", "{}") or "{}")
            except json.JSONDecodeError:
                response_payload = {"output": msg.get("content", "")}
            if not isinstance(response_payload, dict):
                response_payload = {"output": response_payload}
            contents.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": msg.get("name", "tool"),
                        "response": response_payload,
                    }
                }],
            })
    return contents


# ── Backend dispatchers ──────────────────────────────────────────────────

def _call_anthropic(
    provider_name: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    on_text_chunk: Optional[Callable[[str], None]],
    timeout: Optional[int],
) -> LLMResponse:
    """Call Anthropic's Messages API synchronously, with optional streaming."""
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic package not installed") from exc

    # Lazy import so StratForge's secrets module isn't required at module load.
    from app import secrets as _secrets

    api_key = _secrets.get_key(provider_name)
    if not api_key:
        raise RuntimeError(f"No API key for provider '{provider_name}'")

    client = Anthropic(api_key=api_key, timeout=float(timeout or 120))

    system, rest = _split_system(messages)
    ant_messages = _openai_to_anthropic_messages(rest)
    ant_tools = _openai_tools_to_anthropic(tools)

    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "messages": ant_messages,
    }
    if system:
        kwargs["system"] = system
    if ant_tools:
        kwargs["tools"] = ant_tools

    # Stream so we can forward text deltas
    text_parts: List[str] = []
    tool_use_acc: Dict[str, Dict[str, Any]] = {}  # index -> {id, name, json_str}
    stop_reason = "stop"

    with client.messages.stream(**kwargs) as stream:
        for event in stream:
            etype = getattr(event, "type", "")
            if etype == "content_block_start":
                block = getattr(event, "content_block", None)
                if block and getattr(block, "type", "") == "tool_use":
                    idx = getattr(event, "index", 0)
                    tool_use_acc[idx] = {
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "json_str": "",
                    }
            elif etype == "content_block_delta":
                delta = getattr(event, "delta", None)
                dtype = getattr(delta, "type", "")
                if dtype == "text_delta":
                    txt = getattr(delta, "text", "")
                    if txt:
                        text_parts.append(txt)
                        if on_text_chunk:
                            try:
                                on_text_chunk(txt)
                            except Exception:
                                pass
                elif dtype == "input_json_delta":
                    idx = getattr(event, "index", 0)
                    if idx in tool_use_acc:
                        tool_use_acc[idx]["json_str"] += getattr(delta, "partial_json", "") or ""
            elif etype == "message_delta":
                delta = getattr(event, "delta", None)
                sr = getattr(delta, "stop_reason", None)
                if sr:
                    stop_reason = str(sr)

    tool_calls: List[ToolCallRequest] = []
    for acc in tool_use_acc.values():
        try:
            args = json.loads(acc["json_str"]) if acc["json_str"] else {}
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(ToolCallRequest(id=acc["id"], name=acc["name"], arguments=args))

    # Anthropic's stop_reason 'tool_use' maps to 'tool_calls' for consistency
    finish = "tool_calls" if tool_calls else ("stop" if stop_reason in {"end_turn", "stop_sequence"} else stop_reason)

    return LLMResponse(
        content="".join(text_parts),
        tool_calls=tool_calls,
        finish_reason=finish,
    )


def _call_openai(
    provider_name: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    on_text_chunk: Optional[Callable[[str], None]],
    timeout: Optional[int],
) -> LLMResponse:
    """Call OpenAI Chat Completions API with streaming."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package not installed") from exc

    from app import secrets as _secrets

    api_key = _secrets.get_key(provider_name)
    if not api_key:
        raise RuntimeError(f"No API key for provider '{provider_name}'")

    client = OpenAI(api_key=api_key, timeout=float(timeout or 120))

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools

    text_parts: List[str] = []
    tool_calls_acc: Dict[int, Dict[str, Any]] = {}
    finish = "stop"

    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta

        if delta.content:
            text_parts.append(delta.content)
            if on_text_chunk:
                try:
                    on_text_chunk(delta.content)
                except Exception:
                    pass

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                entry = tool_calls_acc.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                if tc.id:
                    entry["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        entry["name"] = tc.function.name
                    if tc.function.arguments:
                        entry["arguments"] += tc.function.arguments

        if choice.finish_reason:
            finish = choice.finish_reason

    tool_calls: List[ToolCallRequest] = []
    for entry in tool_calls_acc.values():
        try:
            args = json.loads(entry["arguments"]) if entry["arguments"] else {}
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(ToolCallRequest(
            id=entry["id"] or f"call_{uuid.uuid4().hex[:8]}",
            name=entry["name"],
            arguments=args,
        ))

    return LLMResponse(
        content="".join(text_parts),
        tool_calls=tool_calls,
        finish_reason=finish,
    )


def _call_google(
    provider_name: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    on_text_chunk: Optional[Callable[[str], None]],
    timeout: Optional[int],
) -> LLMResponse:
    """Call Google Gemini with streaming."""
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("google-generativeai package not installed") from exc

    from app import secrets as _secrets

    api_key = _secrets.get_key(provider_name)
    if not api_key:
        raise RuntimeError(f"No API key for provider '{provider_name}'")

    genai.configure(api_key=api_key)

    system, rest = _split_system(messages)
    gem_contents = _gemini_contents_from_openai(rest)
    gem_tools = _gemini_tools_from_openai(tools)

    gen_model_kwargs: Dict[str, Any] = {"model_name": model}
    if system:
        gen_model_kwargs["system_instruction"] = system
    if gem_tools:
        gen_model_kwargs["tools"] = gem_tools

    gen_model = genai.GenerativeModel(**gen_model_kwargs)

    text_parts: List[str] = []
    tool_calls: List[ToolCallRequest] = []

    response = gen_model.generate_content(gem_contents, stream=True)
    for chunk in response:
        try:
            for candidate in chunk.candidates or []:
                parts = getattr(candidate.content, "parts", []) or []
                for part in parts:
                    if hasattr(part, "text") and part.text:
                        text_parts.append(part.text)
                        if on_text_chunk:
                            try:
                                on_text_chunk(part.text)
                            except Exception:
                                pass
                    fc = getattr(part, "function_call", None)
                    if fc and getattr(fc, "name", None):
                        args = dict(fc.args) if hasattr(fc, "args") and fc.args else {}
                        tool_calls.append(ToolCallRequest(
                            id=f"call_{uuid.uuid4().hex[:8]}",
                            name=fc.name,
                            arguments=args,
                        ))
        except Exception as exc:
            logger.debug("Gemini chunk parse: %s", exc)

    finish = "tool_calls" if tool_calls else "stop"
    return LLMResponse(
        content="".join(text_parts),
        tool_calls=tool_calls,
        finish_reason=finish,
    )


def _call_ollama(
    provider_name: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    on_text_chunk: Optional[Callable[[str], None]],
    timeout: Optional[int],
) -> LLMResponse:
    """Call a local Ollama server via /api/chat with streaming."""
    import httpx

    # Resolve Ollama base URL from StratForge's settings if possible
    try:
        from app.providers.ollama_p import OllamaProvider
        base_url = OllamaProvider().base_url()
    except Exception:
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    text_parts: List[str] = []
    tool_calls: List[ToolCallRequest] = []
    finish = "stop"

    with httpx.Client(timeout=float(timeout or 120)) as client:
        with client.stream("POST", f"{base_url.rstrip('/')}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = data.get("message") or {}
                content = msg.get("content")
                if content:
                    text_parts.append(content)
                    if on_text_chunk:
                        try:
                            on_text_chunk(content)
                        except Exception:
                            pass
                for tc in msg.get("tool_calls", []) or []:
                    fn = tc.get("function", {})
                    tool_calls.append(ToolCallRequest(
                        id=tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                        name=fn.get("name", ""),
                        arguments=fn.get("arguments", {}) or {},
                    ))
                if data.get("done"):
                    if tool_calls:
                        finish = "tool_calls"
                    break

    return LLMResponse(
        content="".join(text_parts),
        tool_calls=tool_calls,
        finish_reason=finish,
    )


# ── Public ChatLLM class ─────────────────────────────────────────────────

class ChatLLM:
    """Drop-in replacement for Vibe-Trading's ChatLLM.

    Instead of using LangChain + ChatOpenAI, this routes to StratForge's
    configured providers (Anthropic / OpenAI / Google / Ollama) using the
    API key stored in the system keyring (`app.secrets`).

    The (provider, model) pair is resolved from the module-level
    set_active() call that the orchestrator makes before spawning AgentLoop.
    An explicit `model_name` argument still takes precedence so swarm
    workers can override on a per-task basis.
    """

    def __init__(
        self,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name

    def _resolve(self, model_name_override: Optional[str] = None) -> tuple[str, str]:
        """Pick the provider + model for this call."""
        active_provider, active_model = get_active()
        provider = self.provider_name or active_provider
        model = (
            model_name_override
            or self.model_name
            or active_model
        )

        if not provider:
            raise RuntimeError(
                "No active provider set. Pick a provider + model in the "
                "StratForge model picker first."
            )
        if not model:
            raise RuntimeError("No model selected for the active session.")
        return provider, model

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
    ) -> LLMResponse:
        """Call the LLM synchronously (no streaming callback)."""
        return self.stream_chat(messages, tools=tools, on_text_chunk=None, timeout=timeout)

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        timeout: Optional[int] = None,
    ) -> LLMResponse:
        """Stream the LLM and forward text deltas; return full aggregated response."""
        provider, model = self._resolve()

        try:
            if provider == "anthropic":
                return _call_anthropic(provider, model, messages, tools, on_text_chunk, timeout)
            if provider == "openai":
                return _call_openai(provider, model, messages, tools, on_text_chunk, timeout)
            if provider == "google":
                return _call_google(provider, model, messages, tools, on_text_chunk, timeout)
            if provider == "ollama":
                return _call_ollama(provider, model, messages, tools, on_text_chunk, timeout)
            # Subscription / CLI providers — fall back to whichever the user has set.
            if provider in {"chatgpt-subscription", "claude-cli"}:
                # These providers have their own async streaming elsewhere.
                # For AgentLoop compatibility, fall back to OpenAI-style
                # completions using whatever tokens the provider stored.
                return _call_openai(provider, model, messages, tools, on_text_chunk, timeout)
            raise RuntimeError(f"Unsupported provider '{provider}' for Vibe-Trading agents.")
        except Exception as exc:
            logger.exception("ChatLLM call failed (provider=%s model=%s)", provider, model)
            raise

    # Async variant kept for parity with Vibe-Trading signature; runs the sync path
    # in a thread so callers in async contexts don't block the event loop.
    async def achat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
    ) -> LLMResponse:
        import asyncio
        return await asyncio.to_thread(self.chat, messages, tools, timeout)
