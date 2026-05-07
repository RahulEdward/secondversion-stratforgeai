"""Chat orchestrator — bridges StratForge sessions to Vibe-Trading's AgentLoop.

Frame shapes yielded to the WebSocket consumer (unchanged from before — the
React UI parses these exact types):

    {"type": "user",        "message": Message}              ← echo of the stored user msg
    {"type": "text",        "delta": "partial token…"}
    {"type": "tool_use",    "id", "name", "input"}
    {"type": "tool_result", "tool_use_id", "ok", "output", "error"}
    {"type": "message",     "message": Message}              ← assistant turn persisted
    {"type": "done"}
    {"type": "error",       "message": "…"}

Under the hood:

1. We take the user message + session context (provider/model/dataset).
2. We point ``src.providers.chat.ChatLLM`` at the StratForge provider
   selected for this session (via ``set_active_provider``).
3. We spin up Vibe-Trading's ``AgentLoop`` in a background thread and
   pipe its events into an ``asyncio.Queue`` that this coroutine drains
   and yields over the WebSocket.
4. The AgentLoop's 27 tools (74 skills, 7 backtest engines, 29 swarms,
   factor/options/pattern/memory/web/doc/…) are ALL available through
   the same registry they ship with.

No more hand-rolled provider streaming loop, no more legacy tool registry,
no more MasterAgent spaghetti — the agent harness is Vibe-Trading's, the
providers are StratForge's, the UI sees the same frame stream as before.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, AsyncIterator, Dict, List, Optional

from . import storage

logger = logging.getLogger(__name__)

_DONE_SENTINEL: Dict[str, Any] = {"type": "__done__"}


# ─── System prompt — injects StratForge's dataset context ────────────────
#
# Vibe-Trading's AgentLoop builds its own system prompt (74 skill summaries
# + 27 tool descriptions). We append our dataset context so the agent can
# use the active dataset without the user re-typing the id every turn.


def _build_dataset_preamble(dataset_id: Optional[str]) -> str:
    """Return a short preamble describing the active dataset, or empty string."""
    if not dataset_id:
        return (
            "\n\n[Active dataset] None. If the user asks for a computation "
            "that needs OHLCV data, tell them to upload a CSV/XLSX via the "
            "sidebar and select it as the active dataset.\n"
        )
    try:
        ds = storage.get_dataset(dataset_id)
    except Exception:  # noqa: BLE001
        ds = None
    if ds is None:
        return f"\n\n[Active dataset] dataset_id={dataset_id} (metadata unavailable).\n"
    range_str = ""
    if ds.start_date and ds.end_date:
        range_str = f"\n  date range: {ds.start_date} → {ds.end_date}"
    return (
        "\n\n[Active dataset]"
        f"\n  dataset_id: {ds.id}"
        f"\n  filename:   {ds.filename}"
        f"\n  rows:       {ds.rows}"
        f"\n  columns:    {', '.join(ds.columns)}"
        + (f"\n  has_ohlcv:  {ds.has_ohlcv}" if hasattr(ds, "has_ohlcv") else "")
        + range_str
        + "\n"
    )


# ─── History conversion: StratForge stored messages → OpenAI-format ──────


def _history_for_agent(session_id: str) -> List[Dict[str, Any]]:
    """Rehydrate past messages into the OpenAI-format shape AgentLoop expects.

    StratForge stores messages as rows with ``role`` + Anthropic-style content
    blocks. AgentLoop's history format is ``[{"role": ..., "content": str}]``
    for plain chat — tool rounds are rebuilt inside the loop itself.
    """
    rows = storage.list_messages(session_id) or []
    out: List[Dict[str, Any]] = []
    for row in rows:
        role = row["role"]
        content = row["content"]
        # Flatten content blocks to plain text for AgentLoop history.
        if isinstance(content, list):
            text_parts: List[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    text_parts.append(str(block.get("text", "")))
                elif btype == "tool_use":
                    name = block.get("name", "")
                    text_parts.append(f"[tool_use: {name}]")
                elif btype == "tool_result":
                    text_parts.append(f"[tool_result: {str(block.get('content', ''))[:200]}]")
            text = "\n".join(p for p in text_parts if p)
        else:
            text = str(content or "")
        # AgentLoop expects plain 'user' / 'assistant'.
        r = "assistant" if role == "assistant" else "user"
        if text:
            out.append({"role": r, "content": text})
    return out


# ─── The background runner that drives Vibe-Trading's AgentLoop ──────────


def _run_agent_in_thread(
    session_id: str,
    project_id: Optional[str],
    user_text: str,
    dataset_id: Optional[str],
    provider_name: str,
    model: str,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
) -> None:
    """Build + run the AgentLoop synchronously, streaming events into ``queue``.

    Runs in a dedicated thread so the async caller can interleave WebSocket
    sends with agent events. We convert AgentLoop's event vocabulary into
    the StratForge WebSocket frame shape.
    """

    def _enqueue(frame: Dict[str, Any]) -> None:
        """Thread-safe async-queue put."""
        asyncio.run_coroutine_threadsafe(queue.put(frame), loop)

    try:
        # Lazy imports — these pull in the whole agent harness, which is
        # expensive to import at module load time.
        from app.agents.loop import AgentLoop
        from app.agent_memory.persistent import PersistentMemory
        from app.agent_llm import ChatLLM, set_active_provider, clear_active_provider
        from app.agent_tools import build_registry

        # Point ChatLLM at the StratForge provider for this session.
        set_active_provider(provider_name, model)

        # Persistent memory (cross-session) — stored under ~/.vibe-trading/memory
        pm = PersistentMemory()

        registry = build_registry(persistent_memory=pm, include_shell_tools=True)
        llm = ChatLLM(provider_name=provider_name, model_name=model)

        def on_event(event_type: str, data: Dict[str, Any]) -> None:
            # AgentLoop event vocabulary:
            #   text_delta   → {delta, iter}
            #   thinking_done→ {iter, content}
            #   tool_call    → {tool, arguments, iter}
            #   tool_result  → {tool, status, elapsed_ms, preview}
            #   compact      → {tokens_before, summary}
            if event_type == "text_delta":
                delta = data.get("delta") or ""
                if delta:
                    _enqueue({"type": "text", "delta": delta})
            elif event_type == "tool_call":
                _enqueue({
                    "type": "tool_use",
                    # AgentLoop doesn't surface the tool_call id here, but the
                    # UI uses this frame purely for rendering; use tool name +
                    # a monotonically increasing token.
                    "id": f"call_{data.get('tool','?')}_{data.get('iter', 0)}",
                    "name": data.get("tool", ""),
                    "input": data.get("arguments") or {},
                })
            elif event_type == "tool_result":
                status = data.get("status", "ok")
                _enqueue({
                    "type": "tool_result",
                    "tool_use_id": f"call_{data.get('tool','?')}_{data.get('iter', 0)}",
                    "ok": status == "ok",
                    "output": data.get("preview", ""),
                    "error": None if status == "ok" else data.get("preview", ""),
                })
            elif event_type == "compact":
                # Inform the UI that context was compressed; surfaced as a
                # low-priority text note so users know why the thread just
                # went quiet for a moment.
                tb = data.get("tokens_before", "?")
                _enqueue({"type": "text", "delta": f"\n_[context compressed — {tb} tokens]_\n"})

        # Build history (past turns) for continuity across messages.
        history = _history_for_agent(session_id)

        agent = AgentLoop(
            registry=registry,
            llm=llm,
            event_callback=on_event,
            max_iterations=50,
            persistent_memory=pm,
        )

        # Inject dataset context into the user message so the agent can call
        # compute_* / backtest tools with the right dataset_id unprompted.
        preamble = _build_dataset_preamble(dataset_id)
        enriched_prompt = f"{preamble}\n\n{user_text}" if preamble else user_text

        result = agent.run(user_message=enriched_prompt, history=history, session_id=session_id)

        # Send the final assistant text as a single "message" frame so the
        # UI replaces the streaming preview with a persisted bubble.
        final_content = (result or {}).get("content") or ""
        if final_content:
            stored = storage.add_message(
                session_id, "assistant",
                [{"type": "text", "text": final_content}],
            )
            if stored is not None:
                _enqueue({"type": "message", "message": stored})

    except Exception as exc:  # noqa: BLE001
        logger.exception("AgentLoop crashed")
        _enqueue({"type": "error", "message": f"Agent engine error: {exc}"})
    finally:
        try:
            from app.agent_llm import clear_active_provider
            clear_active_provider()
        except Exception:
            pass
        _enqueue(_DONE_SENTINEL)


# ─── Public coroutine consumed by routes.py WebSocket handler ────────────


async def run_turn(
    session_id: str,
    user_text: str,
    *,
    permission_mode: str = "accept-edits",
    dataset_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Stream one full assistant turn for ``user_text``.

    Args:
        session_id: StratForge session id.
        user_text: User's new message.
        permission_mode: Kept for API compatibility; currently unused by the
            agent harness (shell/edit tools ignore permission prompts).
        dataset_id: Optional active dataset to inject into the system context.

    Yields:
        WebSocket frames (see module docstring).
    """
    session = storage.get_session(session_id)
    if session is None:
        yield {"type": "error", "message": f"Session {session_id} not found"}
        return

    provider_name = session.provider
    model = session.model
    if not provider_name or not model:
        yield {
            "type": "error",
            "message": "Pick a provider + model in the model picker first.",
        }
        return

    # 1. Persist the user message + echo it.
    user_msg = storage.add_message(
        session_id, "user", [{"type": "text", "text": user_text}]
    )
    if user_msg is not None:
        yield {"type": "user", "message": user_msg}

    # 2. Spin up the agent loop in a background thread and drain its events.
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    thread = threading.Thread(
        target=_run_agent_in_thread,
        args=(
            session_id,
            getattr(session, "project_id", None),
            user_text,
            dataset_id,
            provider_name,
            model,
            loop,
            queue,
        ),
        name=f"agent-{session_id}",
        daemon=True,
    )
    thread.start()

    while True:
        frame = await queue.get()
        if frame is _DONE_SENTINEL:
            break
        yield frame

    yield {"type": "done"}
