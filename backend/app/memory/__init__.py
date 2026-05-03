"""Per-project auto-memory subsystem (Phase 9).

Each StratForge project owns a ``memory/`` folder under its workspace:

    %APPDATA%/StratForge/workspaces/<pid>/memory/
        MEMORY.md          ← index (one bullet per file)
        <slug>.md          ← individual memory entries (frontmatter + body)

Three public surfaces:

* :func:`list_memories`, :func:`read_memory`, :func:`write_memory`,
  :func:`delete_memory` — file-level CRUD used by both the HTTP routes
  and the loader.
* :func:`load_for_prompt` — used by the orchestrator each turn to
  prepend relevant entries to the system prompt.
* :func:`summarize_session` — kicked off after a session ends or every
  N messages; captures durable learnings ("user prefers low-frequency
  strategies", "BTC dataset has a Dec gap", etc.) into a new memory file.

Memory entries are written by a CHEAP model (ChatGPT Subscription's
``gpt-5.1-codex-mini`` if available, else skipped) so the user's main
model never burns tokens authoring summaries.
"""
from .store import (
    MemoryEntry,
    delete_memory,
    list_memories,
    load_for_prompt,
    read_memory,
    write_memory,
)
from .summarizer import summarize_session

__all__ = [
    "MemoryEntry",
    "list_memories",
    "read_memory",
    "write_memory",
    "delete_memory",
    "load_for_prompt",
    "summarize_session",
]
