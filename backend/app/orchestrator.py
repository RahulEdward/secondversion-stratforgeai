"""The chat loop — turns a user message into a streamed assistant turn,
optionally spinning through tool calls until the LLM stops.

Frame shapes yielded to the WebSocket consumer:

    {"type": "user",        "message": Message}            ← echo of the stored user msg
    {"type": "text",        "delta": "partial token…"}
    {"type": "tool_use",    "id": "…", "name": "…", "input": {…}}
    {"type": "tool_result", "tool_use_id": "…", "ok": bool, "output": …, "error": …}
    {"type": "message",     "message": Message}            ← assistant turn persisted
    {"type": "done"}
    {"type": "error",       "message": "…"}

Everything downstream (routes.py, UI) only needs to understand these frames.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

from . import storage
from .providers import get_provider
from .providers.base import ProviderError
from .skills import registry as _skills
# Legacy fallback — used only if skills registry fails to load.
from .tool_exec import run_tool as _legacy_run_tool
from .tools import all_tools as _legacy_all_tools


# Upper bound on tool-call rounds to prevent runaway loops from a misbehaving LLM.
MAX_TOOL_ROUNDS = 25

# Distil a memory entry every N total messages in a session (Phase 9).
MEMORY_EVERY_N = 10

_BASE_SYSTEM_PROMPT = (
    "You are the StratForge AI assistant inside a desktop trading-strategy "
    "workbench. You help the user design, test, and iterate on algorithmic "
    "trading strategies on real historical OHLCV data.\n"
    "\n"
    "## Tool-use rules — these are NON-NEGOTIABLE.\n"
    "\n"
    "1. **NEVER fabricate or hand-write numbers.** Sharpe, CAGR, drawdown, "
    "trade counts, win-rate, profit factor, equity values, indicator "
    "values, percentile bands — ALL must come from a tool call's "
    "`tool_result`. If you don't have a result, call the tool. Do not "
    "type out a markdown table of OHLC bars from memory.\n"
    "2. **NEVER write HTML reports inline.** Use `render_report` — it "
    "produces a real HTML+PDF artifact in the artifacts panel and "
    "returns a `report_id`. Do not paste a copy-paste-able HTML block.\n"
    "3. **Always pass `dataset_id`** from the active dataset shown "
    "below in every tool call. Never ask the user for the id.\n"
    "4. **Always pass `strategy_spec` (or `base_spec`)** when calling "
    "`run_backtest`, `optimize_strategy`, `walk_forward`, "
    "`monte_carlo`. The schema is concrete — see the tool's "
    "`input_schema` for the StrategySpec shape (entries/exits as "
    "CondGroup, sizing, stops, etc.). A minimal valid example:\n"
    "   ```json\n"
    "   {\n"
    "     \"market\": \"forex\",\n"
    "     \"entries\": {\"all_of\": [{\"indicator\": \"rsi\", "
    "\"params\": {\"period\": 14}, \"op\": \"<\", \"value\": 30}]},\n"
    "     \"exits\":   {\"any_of\": [{\"indicator\": \"rsi\", "
    "\"params\": {\"period\": 14}, \"op\": \">\", \"value\": 55}]}\n"
    "   }\n"
    "   ```\n"
    "5. **If a previous tool call failed in this session, retry it "
    "with corrected args.** Do not give up and start hand-typing data — "
    "the user wants real, reproducible numbers from the live engine.\n"
    "6. The full pipeline is: indicators (compute_*) → `run_backtest` "
    "→ `optimize_strategy` → `walk_forward` → `monte_carlo` → "
    "`score_strategy` → `render_report`. Run them in that order when "
    "the user asks for the \"full pipeline\".\n"
    "7. **CRITICAL — Sequential dependencies, never parallel.** "
    "`score_strategy` and `render_report` consume IDs (`backtest_id`, "
    "`monte_carlo_id`, `walk_forward_id`, `optimization_id`) emitted by "
    "earlier tools. **NEVER invent these IDs**, and **NEVER call "
    "`score_strategy` / `render_report` in the same turn as the tools "
    "that produce the IDs they need.** Always wait one turn for the "
    "tool_result, then copy the exact id string from the result into "
    "the next tool call. Indicators (compute_*) can run in parallel, "
    "but scoring/reporting must be sequential.\n"
    "8. **NEVER claim you cannot access, validate, or inspect the "
    "dataset.** You have FULL access to all data via tool calls. "
    "The tools (`compute_*`, `run_backtest`, `run_full_pipeline`, etc.) "
    "load the dataset directly from disk using `dataset_id` — they "
    "handle ALL data reading, validation, indicator computation, and "
    "strategy compilation internally. You do NOT need row-level access "
    "yourself. NEVER say 'validation failed due to lack of accessible "
    "row-level data' or similar — just CALL the tool. If you want to "
    "verify the dataset, call any `compute_*` indicator on it. If you "
    "want to test a strategy, call `run_backtest` or "
    "`run_full_pipeline`. The tools will return errors if the data is "
    "invalid — trust the tool_result, do not pre-validate.\n"
    "\n"
    "Keep prose concise — the user is a technical trader, not a beginner.\n"
    "\n"
    "## STRATEGY RESEARCH PROTOCOL — Auto-Iterate Until Passing\n"
    "\n"
    "When the user asks you to BUILD, FIND, or RESEARCH a strategy "
    "(e.g. 'build a profitable intraday strategy', 'find me a strategy "
    "that works', 'create a winning setup'), follow this autonomous "
    "research loop:\n"
    "\n"
    "### Phase 1 — Data Reconnaissance (1 tool round)\n"
    "Compute 4-5 key indicators (RSI, ATR, ADX, Bollinger, EMA) in "
    "parallel to understand the dataset: trending vs mean-reverting, "
    "volatility regime, data length. This tells you which strategy "
    "family to start with.\n"
    "\n"
    "### Phase 2 — Multi-Variant Strategy Design\n"
    "Design 2-3 STRUCTURALLY DIFFERENT strategy variants. Don't just "
    "tweak numbers — use genuinely different logic:\n"
    "  - Variant A: Trend-following (e.g. EMA crossover + ADX filter)\n"
    "  - Variant B: Mean-reversion (e.g. Bollinger bounce + RSI)\n"
    "  - Variant C: Momentum/breakout (e.g. Donchian channel + ATR)\n"
    "Each variant MUST include:\n"
    "  - At least 2 entry conditions (signal + confirmation)\n"
    "  - At least 1 exit condition\n"
    "  - ATR or fixed stops (stop_loss + take_profit)\n"
    "  - Realistic fees_override and slippage_override\n"
    "Make conditions LOOSE enough to generate trades on the dataset. "
    "Avoid requiring RSI < 30 AND another strict condition — use "
    "thresholds like RSI < 45 or > 55 for initial variants.\n"
    "\n"
    "### Phase 3 — Pipeline Execution\n"
    "Run `run_full_pipeline` for each variant with:\n"
    "  - optimize: true + optimize_grid (sweep 2-3 key params)\n"
    "  - walk_forward: true, wf_n_folds: 3-4\n"
    "  - monte_carlo: true, mc_n_iterations: 1000\n"
    "  - render: false (save report rendering for the winner)\n"
    "\n"
    "### Phase 4 — Verdict Analysis & Iteration\n"
    "After each pipeline result, read the `score.verdict` and "
    "`score.vetos` carefully:\n"
    "\n"
    "IF verdict == 'adopt' → STOP. This strategy passes. Go to Phase 5.\n"
    "\n"
    "IF verdict == 'iterate' or 'reject' → Analyze the SPECIFIC vetos:\n"
    "  - 'min_trades': conditions too strict → loosen thresholds or "
    "    use different indicators that fire more frequently\n"
    "  - 'max_drawdown': risk too high → tighten stops, add trailing, "
    "    reduce position size\n"
    "  - 'profit_factor' ≤ 1.0: no edge → try a completely different "
    "    strategy family (don't just tweak params)\n"
    "  - 'mc_survival' low: edge is noise → add regime filters "
    "    (e.g. ADX > 20 for trend strategies)\n"
    "  - 'overfitting' (WFE < 0.5): too curve-fit → simplify the "
    "    strategy (fewer conditions, wider param ranges)\n"
    "\n"
    "Design an IMPROVED variant based on the failure analysis and run "
    "the pipeline again. NEVER just re-run the same strategy — each "
    "iteration must have meaningful structural changes.\n"
    "\n"
    "### Phase 5 — Finalize Best Result\n"
    "Once a strategy passes (verdict = 'adopt') OR you have completed "
    "5 pipeline iterations (whichever comes first):\n"
    "  1. Pick the best result by grade (highest score)\n"
    "  2. Run `run_full_pipeline` one final time with render: true\n"
    "  3. Call `save_strategy` with a descriptive name\n"
    "  4. Present the user with: grade, key metrics table, vetos "
    "     (if any), and the report URL\n"
    "\n"
    "### Iteration Limits\n"
    "  - Maximum 5 pipeline iterations per research request\n"
    "  - If no variant reaches 'adopt' after 5 tries, save the BEST "
    "    one anyway and explain what's limiting it\n"
    "  - Between iterations, briefly tell the user what failed and "
    "    what you're changing (1-2 sentences, not verbose)\n"
    "\n"
    "### Acceptance Criteria (Default)\n"
    "A strategy is considered PASSING when:\n"
    "  - Grade ≥ B- (score ≥ 65)\n"
    "  - No hard vetos (num_trades ≥ 100, max_dd > -50%, PF > 1.0)\n"
    "  - If walk-forward ran: WFE ≥ 0.5\n"
    "  - If Monte Carlo ran: survival_rate ≥ 70%\n"
    "The user may specify stricter criteria — honor those instead.\n"
    "\n"
    "REMEMBER: You have up to 25 tool rounds available. Use them. "
    "The user expects you to keep trying, not give up after one failure.\n"
    "\n"
    "## RUNTIME ENVIRONMENT — Process Management\n"
    "\n"
    "You have a built-in Runtime Environment for running applications:\n"
    "\n"
    "### Available Tools:\n"
    "- `start_process` — Start long-running processes (dev servers, builds). "
    "Returns a process_id. Auto-detects server readiness and port number. "
    "Use this INSTEAD of `shell` for commands that run indefinitely "
    "(e.g. `npm run dev`, `python -m http.server`).\n"
    "- `stop_process` — Kill a managed process by process_id.\n"
    "- `list_processes` — Show all running processes with ports and status.\n"
    "- `get_process_output` — Read recent stdout/stderr from a process.\n"
    "- `open_preview` — Signal the UI to open the Preview panel to a URL. "
    "Use after starting a dev server to show the user the live app.\n"
    "\n"
    "### App Building Workflow:\n"
    "When the user asks you to BUILD an application:\n"
    "1. Use `write_file` to create project files\n"
    "2. Use `shell` to install dependencies (npm install, pip install)\n"
    "3. Use `start_process` to run dev servers\n"
    "4. Use `open_preview` to show the live app to the user\n"
    "5. If the process logs show errors, read them with `get_process_output`, "
    "fix the code with `edit_file`, and restart with `stop_process` + `start_process`\n"
    "\n"
    "### Smart Rules:\n"
    "- Always use `list_processes` before starting a new server to avoid port conflicts\n"
    "- Use `start_process` with `wait_ready: true` for dev servers\n"
    "- After `start_process` succeeds and detects a port, call `open_preview` "
    "with the detected URL so the user sees the app immediately\n"
    "- If a process crashes, read its output, fix the issue, and restart\n"
    "- Never leave orphaned processes — stop what you started when done\n"
    "\n"
    "CRITICAL PERMISSION NOTE: `start_process`, `stop_process`, and `open_preview` "
    "are explicitly ALLOWED in this environment regardless of the user's permission mode. "
    "Do NOT tell the user to switch to Bypass mode to run dev servers. You already have permission!\n"
)


def _append_memory(prompt: str, project_id: Optional[str]) -> str:
    """Append the project's memory snippet to the prompt (Phase 9)."""
    try:
        from . import memory as _mem

        snippet = _mem.load_for_prompt(project_id)
        return prompt + snippet if snippet else prompt
    except Exception:  # noqa: BLE001 — memory must never break chat
        return prompt


def _build_system_prompt(
    dataset_id: Optional[str],
    project_id: Optional[str] = None,
) -> str:
    """Augment the system prompt with the live active-dataset context AND
    project-level memory entries.

    Without this the LLM has to ask the user for `dataset_id` on every turn
    — the desktop app already knows it, so we inject filename / rows / date
    range / columns so tool calls can be made unprompted. Memory entries
    (Phase 9) carry durable learnings across sessions.
    """
    if not dataset_id:
        return _append_memory(
            _BASE_SYSTEM_PROMPT
            + "\n\n[Context] No active dataset. If the user asks for a "
            "computation that needs one, tell them to upload a CSV/XLSX "
            "from the sidebar and select it as the active dataset.",
            project_id,
        )
    ds = storage.get_dataset(dataset_id)
    if ds is None:
        return _append_memory(
            _BASE_SYSTEM_PROMPT
            + f"\n\n[Context] dataset_id={dataset_id} (metadata unavailable; "
            "use the id verbatim in tool calls).",
            project_id,
        )
    range_str = ""
    if ds.start_date and ds.end_date:
        range_str = f"\n  date range: {ds.start_date} → {ds.end_date}"
    base = (
        _BASE_SYSTEM_PROMPT
        + "\n\n[Active dataset]"
        + f"\n  dataset_id: {ds.id}"
        + f"\n  filename:   {ds.filename}"
        + f"\n  rows:       {ds.rows}"
        + f"\n  columns:    {', '.join(ds.columns)}"
        + (f"\n  has_ohlcv:  {ds.has_ohlcv}" if hasattr(ds, "has_ohlcv") else "")
        + range_str
        + "\n\nUse this exact `dataset_id` value in every indicator / "
        "backtest / optimize / validate tool call without asking the user."
    )
    return _append_memory(base, project_id)


def _history_for_llm(session_id: str) -> List[Dict[str, Any]]:
    """Load stored messages into the shape every provider's stream_chat expects:
    ``[{role, content: [blocks]}]``."""
    rows = storage.list_messages(session_id) or []
    out: List[Dict[str, Any]] = []
    for row in rows:
        # Role `tool` doesn't exist in Anthropic — tool results ride inside
        # a `user` turn as tool_result blocks. We stored them as role='tool'
        # for clarity; merge them into the previous user turn on load.
        if row["role"] == "tool":
            # Tool results are emitted as a user-role turn with tool_result blocks.
            out.append({"role": "user", "content": row["content"]})
        else:
            out.append({"role": row["role"], "content": row["content"]})
    return out


async def run_turn(
    session_id: str,
    user_text: str,
    *,
    permission_mode: str = "accept-edits",
    dataset_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Full turn: persist user msg → stream assistant reply → resolve tool
    calls → stream follow-up → persist final assistant msg → done."""
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

    try:
        provider = get_provider(provider_name)
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": f"Provider `{provider_name}` unavailable: {exc}"}
        return

    # 1. Persist the user message.
    user_msg = storage.add_message(
        session_id, "user", [{"type": "text", "text": user_text}]
    )
    if user_msg is not None:
        yield {"type": "user", "message": user_msg}

    # ── Multi-agent research mode ──────────────────────────────────
    # If the user asks to build/find/research a strategy, hand off to
    # the MasterAgent for autonomous iteration instead of the regular
    # single-agent tool-calling loop.
    if _is_research_request(user_text) and dataset_id:
        from .agents import MasterAgent

        master = MasterAgent()
        full_text = ""
        try:
            async for frame in master.run_research(
                user_request=user_text,
                dataset_id=dataset_id,
                provider=provider,
                model=model,
            ):
                if frame.get("type") == "text":
                    full_text += frame.get("delta", "")
                yield frame
        except Exception as exc:  # noqa: BLE001
            err_msg = f"\n\n❌ Research loop crashed: {exc}"
            full_text += err_msg
            yield {"type": "text", "delta": err_msg}

        # Persist the entire research output as one assistant message
        if full_text:
            final = storage.add_message(
                session_id, "assistant",
                [{"type": "text", "text": full_text}],
            )
            if final is not None:
                yield {"type": "message", "message": final}
        yield {"type": "done"}
        return

    # ── Regular single-agent mode ──────────────────────────────────
    messages = _history_for_llm(session_id)
    # Dynamically load tools from all registered skills.
    try:
        tools = _skills.all_tools()
    except Exception:
        tools = _legacy_all_tools()  # fallback
    project_id = getattr(session, "project_id", None)
    system_prompt = _build_system_prompt(dataset_id, project_id)

    # 2. Tool-calling loop.
    assistant_blocks: List[Dict[str, Any]] = []
    rounds = 0
    while True:
        rounds += 1
        if rounds > MAX_TOOL_ROUNDS:
            yield {
                "type": "error",
                "message": f"Gave up after {MAX_TOOL_ROUNDS} tool rounds.",
            }
            break

        assistant_blocks = []
        pending_tool_uses: List[Dict[str, Any]] = []

        try:
            async for chunk in provider.stream_chat(
                messages=messages,
                tools=tools,
                model=model,
                system=system_prompt,
                session_id=session_id,
            ):
                ctype = chunk.get("type")
                if ctype == "text":
                    delta = chunk.get("delta", "")
                    if delta:
                        yield {"type": "text", "delta": delta}
                    # Merge into last text block or start a new one.
                    if assistant_blocks and assistant_blocks[-1].get("type") == "text":
                        assistant_blocks[-1]["text"] += delta
                    else:
                        assistant_blocks.append({"type": "text", "text": delta})
                elif ctype == "tool_use":
                    block = {
                        "type": "tool_use",
                        "id": chunk["id"],
                        "name": chunk["name"],
                        "input": chunk.get("input", {}),
                    }
                    assistant_blocks.append(block)
                    if not getattr(provider, "handles_tool_execution", False):
                        pending_tool_uses.append(block)
                    yield {
                        "type": "tool_use",
                        "id": block["id"],
                        "name": block["name"],
                        "input": block["input"],
                    }
                elif ctype == "tool_result":
                    yield chunk
                elif ctype == "error":
                    yield {"type": "error", "message": chunk.get("message", "Provider error")}
                    return
        except ProviderError as exc:
            yield {"type": "error", "message": str(exc)}
            return
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "message": f"Stream crashed: {exc}"}
            return

        # 3. If no tool calls, the assistant turn is complete.
        if not pending_tool_uses:
            break

        # 4. Append the assistant turn (with tool_use blocks) to history.
        messages.append({"role": "assistant", "content": assistant_blocks})
        # Persist partial assistant turn so history survives a reconnect,
        # AND yield a `message` frame so the UI moves the tool cards out
        # of the transient streaming pane into a permanent assistant
        # bubble. Without this, turns that have only tool_use blocks (no
        # text) appear as ghosts: cards flash during streaming and then
        # vanish on `done`, even though the message is in the DB.
        persisted_partial = storage.add_message(
            session_id, "assistant", assistant_blocks
        )
        if persisted_partial is not None:
            yield {"type": "message", "message": persisted_partial}

        # 5. Run every tool_use in parallel; stream back tool_results.
        tool_result_blocks: List[Dict[str, Any]] = []
        for tu in pending_tool_uses:
            # Route through the skills registry (with timeout).
            try:
                result = await _skills.execute(
                    tu["name"], tu["input"],
                    permission_mode=permission_mode,
                )
            except Exception:
                result = await _legacy_run_tool(
                    tu["name"], tu["input"],
                    permission_mode=permission_mode,
                )
            block: Dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": tu["id"],
            }
            if result.get("ok"):
                block["content"] = _jsonable_text(result["output"])
                yield {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "ok": True,
                    "output": result["output"],
                }
            else:
                block["content"] = f"Error: {result.get('error', 'unknown')}"
                block["is_error"] = True
                yield {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "ok": False,
                    "error": result.get("error", "unknown"),
                }
            tool_result_blocks.append(block)

        # 6. Push tool_results as a user-role turn and persist.
        messages.append({"role": "user", "content": tool_result_blocks})
        storage.add_message(session_id, "tool", tool_result_blocks)
        # Loop back — the LLM now sees the tool output.

    # 7. Persist the final assistant turn (if any content) and emit.
    if assistant_blocks:
        final = storage.add_message(session_id, "assistant", assistant_blocks)
        if final is not None:
            yield {"type": "message", "message": final}

    # 8. Phase 9 memory: distil session every ``MEMORY_EVERY_N`` messages.
    # Fire-and-forget — the chat hot-path never blocks on memory writes.
    if project_id:
        try:
            full_msgs = _history_for_llm(session_id)
            if len(full_msgs) and len(full_msgs) % MEMORY_EVERY_N == 0:
                import asyncio as _asyncio
                from . import memory as _mem

                _asyncio.create_task(
                    _mem.summarize_session(project_id, session_id, full_msgs)
                )
        except Exception:  # noqa: BLE001
            pass

    yield {"type": "done"}


def _jsonable_text(payload: Any) -> str:
    """Serialize a tool payload for inclusion in a tool_result content block.
    Providers expect either a string or a list of blocks — we keep it simple
    with a JSON string (token-cheap, trivial to round-trip)."""
    import json

    try:
        return json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload)


# ─── Multi-agent trigger detection ──────────────────────────────────────

# Keywords that signal the user wants autonomous strategy research.
# Matched case-insensitively against the user message.
_RESEARCH_KEYWORDS = [
    "build me a",
    "build a",
    "create a",
    "find me a",
    "find a",
    "research a",
    "design a",
    "develop a",
    "make a",
    "generate a",
    "auto research",
    "auto-research",
    "keep trying",
    "keep iterating",
    "don't stop",
    "profitable strategy",
    "winning strategy",
    "strategy that works",
    "strategy banao",
    "strategy bana",
    "strategy dhundo",
    "strategy find karo",
    "strategy build karo",
]


def _is_research_request(user_text: str) -> bool:
    """Return True if the message looks like a strategy research request.

    We check for keyword patterns that indicate the user wants the
    autonomous multi-agent loop rather than a single tool call.
    """
    lower = user_text.lower().strip()
    return any(kw in lower for kw in _RESEARCH_KEYWORDS)

