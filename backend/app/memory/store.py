"""Markdown-with-frontmatter file store for per-project memory entries."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..paths import workspace_dir

# Memory entries supported by the loader. Mirrors the user's existing
# ``MEMORY.md`` taxonomy so familiar reading flow carries over.
ALLOWED_TYPES = ("user", "feedback", "project", "reference")

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n(.*)", re.DOTALL)


@dataclass
class MemoryEntry:
    name: str             # filename without .md (slug)
    title: str            # human-readable, from frontmatter
    description: str      # one-line summary
    type: str             # ALLOWED_TYPES
    body: str             # markdown body (after frontmatter)
    updated_at: str       # ISO8601


# ── Path helpers ──────────────────────────────────────────────────────────


def _memory_dir(project_id: str) -> Path:
    d = workspace_dir(project_id) / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _memory_path(project_id: str, name: str) -> Path:
    return _memory_dir(project_id) / f"{slugify(name)}.md"


def _index_path(project_id: str) -> Path:
    return _memory_dir(project_id) / "MEMORY.md"


def slugify(name: str) -> str:
    s = (name or "").strip().lower().replace(" ", "_")
    s = _SLUG_RE.sub("", s)
    return s[:80] or "untitled"


# ── Frontmatter parser / writer ───────────────────────────────────────────


def _parse(raw: str) -> Dict[str, Any]:
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return {"meta": {}, "body": raw}
    head, body = m.group(1), m.group(2)
    meta: Dict[str, Any] = {}
    for line in head.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return {"meta": meta, "body": body.strip()}


def _serialise(entry: MemoryEntry) -> str:
    head = (
        "---\n"
        f"name: {entry.title}\n"
        f"description: {entry.description}\n"
        f"type: {entry.type}\n"
        f"updated_at: {entry.updated_at}\n"
        "---\n"
    )
    return head + entry.body.rstrip() + "\n"


# ── CRUD ──────────────────────────────────────────────────────────────────


def list_memories(project_id: str) -> List[MemoryEntry]:
    """Return all memory entries for a project, newest-first."""
    d = _memory_dir(project_id)
    out: List[MemoryEntry] = []
    for p in d.glob("*.md"):
        if p.name == "MEMORY.md":
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = _parse(raw)
        meta = parsed["meta"]
        out.append(
            MemoryEntry(
                name=p.stem,
                title=str(meta.get("name") or p.stem),
                description=str(meta.get("description") or ""),
                type=str(meta.get("type") or "reference"),
                body=parsed["body"],
                updated_at=str(
                    meta.get("updated_at")
                    or datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
                ),
            )
        )
    out.sort(key=lambda e: e.updated_at, reverse=True)
    return out


def read_memory(project_id: str, name: str) -> Optional[MemoryEntry]:
    p = _memory_path(project_id, name)
    if not p.exists():
        return None
    raw = p.read_text(encoding="utf-8")
    parsed = _parse(raw)
    meta = parsed["meta"]
    return MemoryEntry(
        name=p.stem,
        title=str(meta.get("name") or p.stem),
        description=str(meta.get("description") or ""),
        type=str(meta.get("type") or "reference"),
        body=parsed["body"],
        updated_at=str(
            meta.get("updated_at")
            or datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
        ),
    )


def write_memory(
    project_id: str,
    *,
    name: str,
    title: str,
    description: str,
    body: str,
    type: str = "reference",
) -> MemoryEntry:
    if type not in ALLOWED_TYPES:
        type = "reference"
    entry = MemoryEntry(
        name=slugify(name),
        title=title.strip() or name,
        description=(description or "").strip(),
        type=type,
        body=body.strip(),
        updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    p = _memory_path(project_id, entry.name)
    p.write_text(_serialise(entry), encoding="utf-8")
    _refresh_index(project_id)
    return entry


def delete_memory(project_id: str, name: str) -> bool:
    p = _memory_path(project_id, name)
    if not p.exists():
        return False
    try:
        p.unlink()
    except OSError:
        return False
    _refresh_index(project_id)
    return True


def _refresh_index(project_id: str) -> None:
    """Regenerate MEMORY.md — one bullet per entry, newest first."""
    entries = list_memories(project_id)
    lines = ["# Project memory\n"]
    if not entries:
        lines.append("_No memory entries yet._\n")
    else:
        for e in entries:
            tag = f"[{e.type}]"
            lines.append(f"- {tag} **[{e.title}]({e.name}.md)** — {e.description}")
    _index_path(project_id).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Loader: assemble memory snippet for the system prompt ────────────────


_MEMORY_SECTION_BUDGET = 4000  # chars — keep system prompt slim


def load_for_prompt(project_id: Optional[str], limit: int = 8) -> str:
    """Format up-to-`limit` memory entries as a markdown block to prepend
    to the system prompt. Empty string if the project has no memory yet.

    Selection: newest first, capped at ``_MEMORY_SECTION_BUDGET`` chars
    so we never blow up the context window.
    """
    if not project_id:
        return ""
    entries = list_memories(project_id)[:limit]
    if not entries:
        return ""

    parts: List[str] = []
    parts.append("\n\n[Project memory]")
    parts.append(
        "Persistent learnings from prior sessions on this project. Use "
        "them as soft context — defer to the user when they conflict."
    )
    used = 0
    for e in entries:
        snippet = (
            f"\n## {e.title} ({e.type})"
            f"\n_{e.description}_\n{e.body.strip()}\n"
        )
        if used + len(snippet) > _MEMORY_SECTION_BUDGET:
            parts.append(f"\n…(+{len(entries) - len([p for p in parts if p.startswith(chr(10) + '##')])} more memory entries — truncated for context budget)")
            break
        parts.append(snippet)
        used += len(snippet)
    return "".join(parts)


# ── Strategy result memory ───────────────────────────────────────────────


def save_strategy_result(
    strategy_name: str,
    spec: Dict[str, Any],
    grade: str,
    metrics: Dict[str, Any],
    market_regime: str,
    *,
    project_id: Optional[str] = None,
) -> None:
    """Save a strategy research result to memory for future reference.

    Called by MasterAgent after research completes. Creates a structured
    memory entry that the Architect can query in future sessions to avoid
    repeating failures and leverage successful patterns.
    """
    if not project_id:
        # Try to find the active project
        from .. import storage as _storage
        projects = _storage.list_projects()
        if not projects:
            return
        project_id = projects[0].id

    verdict = "passed" if grade in {"A+", "A", "A-", "B+", "B", "B-"} else "failed"
    sharpe = metrics.get("sharpe", "?")
    pf = metrics.get("profit_factor", "?")
    n_trades = metrics.get("num_trades", "?")

    # Extract indicator names from spec
    indicators = set()
    for group_key in ("entries", "exits"):
        group = spec.get(group_key, {}) if isinstance(spec, dict) else {}
        for cond_key in ("all_of", "any_of"):
            for cond in group.get(cond_key, []):
                if isinstance(cond, dict) and "indicator" in cond:
                    indicators.add(cond["indicator"])

    body_lines = [
        f"**Strategy:** {strategy_name}",
        f"**Grade:** {grade} ({verdict})",
        f"**Regime:** {market_regime}",
        f"**Indicators:** {', '.join(sorted(indicators)) or 'unknown'}",
        f"**Sharpe:** {sharpe} | **PF:** {pf} | **Trades:** {n_trades}",
    ]

    if verdict == "failed":
        body_lines.append("")
        body_lines.append("**Failure analysis:** This combination of indicators and parameters")
        body_lines.append(f"did not produce a viable strategy under {market_regime} regime.")
        body_lines.append("Avoid re-testing similar configurations without structural changes.")
    else:
        body_lines.append("")
        body_lines.append("**Success factors:** This configuration worked well.")
        body_lines.append("Consider reusing this pattern for similar market conditions.")

    try:
        write_memory(
            project_id,
            name=f"strategy_{slugify(strategy_name)}_{grade.replace('+', 'p').replace('-', 'm')}",
            title=f"{strategy_name} ({grade})",
            description=f"Auto-researched strategy — {verdict}. Sharpe={sharpe}, PF={pf}",
            body="\n".join(body_lines),
            type="reference",
        )
    except Exception:
        pass  # Non-fatal — memory is optional

