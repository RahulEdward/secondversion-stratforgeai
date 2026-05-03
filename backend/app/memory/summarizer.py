"""Cheap-model session summarizer — distils a chat into durable memory.

Triggered by the orchestrator at session close (or every N messages).
We deliberately use a SMALL/cheap model (subscription's mini variant)
so the user's main model never burns tokens authoring summaries.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .store import write_memory

logger = logging.getLogger(__name__)

# Models we'll try, in preference order. The first one with credentials
# wins; if none are available the summarizer is a silent no-op (memory
# still works manually via the UI).
_PREFERRED_PROVIDERS = ("chatgpt-subscription", "google")
_CHEAP_MODELS = {
    # Subscription: the lightest GPT-5.x variant we have.
    "chatgpt-subscription": "gpt-5.1-codex-mini",
    # Google: cheapest production Gemini.
    "google": "gemini-1.5-flash-latest",
}

_SYSTEM = (
    "You are the StratForge MEMORY DISTILLER. You read a chat session "
    "and emit ONE memory entry that captures durable, project-level "
    "learnings the future-self of the agent will benefit from. "
    "Output STRICT JSON ONLY — no prose outside the JSON. Schema:\n"
    "{\n"
    '  "name": str,           # short slug, e.g. "btc_low_freq_pref"\n'
    '  "title": str,          # human-readable, ≤ 60 chars\n'
    '  "description": str,    # one sentence summary\n'
    '  "type": "user"|"feedback"|"project"|"reference",\n'
    '  "body": str            # markdown body, ≤ 1500 chars\n'
    "}\n"
    "Rules:\n"
    "- Only emit a memory if the session contains durable insight "
    "(strategy choices the user made, datasets they own, what works/"
    "fails on this project, user preferences).\n"
    "- If nothing is durable, return EXACTLY: {\"skip\": true}\n"
    "- Never invent facts. Quote the user when surfacing preferences."
)


async def summarize_session(
    project_id: str,
    session_id: str,
    messages: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Distil ``messages`` into a memory entry. Returns the saved entry's
    metadata (name, title, type), or None if skipped / no provider.

    Always failure-safe: any exception is logged and swallowed so the
    chat hot-path never errors out because of a memory-write hiccup.
    """
    try:
        provider, model = _pick_provider()
    except RuntimeError as exc:
        logger.info("Memory summariser skipped — %s", exc)
        return None

    transcript = _build_transcript(messages)
    if not transcript.strip():
        return None

    payload = await _ask_llm(provider, model, transcript)
    if payload is None:
        return None
    if payload.get("skip"):
        logger.info("Memory summariser: model returned skip for session %s", session_id)
        return None

    try:
        entry = write_memory(
            project_id,
            name=str(payload.get("name") or f"session_{session_id[:8]}"),
            title=str(payload.get("title") or "Session learnings"),
            description=str(payload.get("description") or ""),
            body=str(payload.get("body") or ""),
            type=str(payload.get("type") or "reference"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Memory write failed: %s", exc)
        return None

    return {
        "name": entry.name,
        "title": entry.title,
        "type": entry.type,
        "description": entry.description,
    }


# ── Provider selection ────────────────────────────────────────────────────


def _pick_provider() -> tuple[str, str]:
    from ..providers import get_provider

    for name in _PREFERRED_PROVIDERS:
        p = get_provider(name)
        if p is None:
            continue
        try:
            if p.has_credential():
                return name, _CHEAP_MODELS[name]
        except Exception:
            continue
    raise RuntimeError(
        "no cheap-model provider available (need ChatGPT subscription or Google API key)"
    )


# ── Transcript assembly ───────────────────────────────────────────────────


_MAX_TRANSCRIPT_CHARS = 16_000


def _build_transcript(messages: List[Dict[str, Any]]) -> str:
    """Flatten the session history into a compact transcript string."""
    out: List[str] = []
    for m in messages:
        role = m.get("role", "?")
        blocks = m.get("content", [])
        if isinstance(blocks, str):
            text = blocks
        elif isinstance(blocks, list):
            chunks: List[str] = []
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                btype = b.get("type")
                if btype == "text":
                    chunks.append(str(b.get("text", "")))
                elif btype == "tool_use":
                    inp = json.dumps(b.get("input") or {}, default=str)[:200]
                    chunks.append(f"[tool_use {b.get('name')}({inp})]")
                elif btype == "tool_result":
                    content = b.get("content")
                    if isinstance(content, list):
                        content = " ".join(
                            str(c.get("text", "")) for c in content if isinstance(c, dict)
                        )
                    chunks.append(f"[tool_result {str(content)[:300]}]")
            text = "".join(chunks)
        else:
            text = str(blocks)
        out.append(f"{role.upper()}: {text}")
    raw = "\n\n".join(out)
    if len(raw) > _MAX_TRANSCRIPT_CHARS:
        raw = raw[-_MAX_TRANSCRIPT_CHARS:]  # keep the most recent context
    return raw


# ── LLM call ──────────────────────────────────────────────────────────────


async def _ask_llm(
    provider_name: str, model: str, transcript: str,
) -> Optional[Dict[str, Any]]:
    from ..providers import get_provider

    provider = get_provider(provider_name)
    if provider is None:
        return None

    user_message = (
        "Session transcript follows. Distil into a memory entry per the "
        "schema in the system prompt.\n\n"
        f"```\n{transcript}\n```"
    )

    text_buf: List[str] = []
    try:
        async for chunk in provider.stream_chat(
            messages=[{
                "role": "user",
                "content": [{"type": "text", "text": user_message}],
            }],
            tools=None,
            model=model,
            system=_SYSTEM,
        ):
            if chunk.get("type") == "text":
                text_buf.append(chunk.get("delta", ""))
            elif chunk.get("type") == "error":
                logger.warning("Memory summariser stream error: %s", chunk.get("message"))
                return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Memory summariser stream failed: %s", exc)
        return None

    raw = "".join(text_buf).strip()
    return _extract_json(raw)


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of the model's output."""
    if not raw:
        return None
    # Strip code fences if present.
    if raw.startswith("```"):
        raw = raw.strip("`")
        # remove leading lang tag like "json\n"
        nl = raw.find("\n")
        if nl != -1:
            raw = raw[nl + 1:]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fall back to first {...} block.
        first = raw.find("{")
        last = raw.rfind("}")
        if first != -1 and last > first:
            try:
                return json.loads(raw[first: last + 1])
            except Exception:
                return None
    return None
