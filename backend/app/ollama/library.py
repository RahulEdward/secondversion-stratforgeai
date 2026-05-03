"""Ollama model library — scrapes the official search page.

Fetches ``https://ollama.com/search?q=...`` and parses the server-rendered
HTML to extract model metadata (name, description, sizes, pull count,
capabilities). Results are cached for 30 minutes per query. When the remote
fetch fails we fall back to a small curated list so the UI always has
something to render.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, List, Tuple

import httpx

logger = logging.getLogger(__name__)

CATEGORIES: List[str] = ["chat", "code", "reasoning", "vision", "embedding"]

_OLLAMA_SEARCH_URL = "https://ollama.com/search"
_CACHE_TTL = 1800  # 30 minutes

# Per-(query, page) cache.
_cache: dict[str, Any] = {}


# ── HTML parsing ──────────────────────────────────────────────────────────

_BLOCK_SPLIT = re.compile(r"x-test-search-response-title>")
_RE_TITLE = re.compile(r"^([^<]+)")
_RE_DESC = re.compile(
    r'text-neutral-800 text-md">\s*(.+?)\s*</p>', re.DOTALL
)
_RE_SIZE = re.compile(r"x-test-size[^>]*>([^<]+)")
_RE_PULLS = re.compile(r"x-test-pull-count[^>]*>([^<]+)")
_RE_CAPABILITY = re.compile(r"x-test-capability[^>]*>([^<]+)")
_RE_UPDATED = re.compile(r"x-test-updated[^>]*>([^<]+)")


def _parse_pull_count(s: str) -> int:
    s = s.strip()
    multiplier = 1
    if s.endswith("M"):
        multiplier = 1_000_000
        s = s[:-1]
    elif s.endswith("K"):
        multiplier = 1_000
        s = s[:-1]
    try:
        return int(float(s) * multiplier)
    except ValueError:
        return 0


def _format_pulls(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _infer_category(name: str, capabilities: List[str]) -> str:
    lower = name.lower()
    cap_set = {c.lower() for c in capabilities}
    if "embedding" in cap_set or "embed" in lower:
        return "embedding"
    if (
        "vision" in cap_set
        or "-vl" in lower
        or "llava" in lower
        or "moondream" in lower
    ):
        return "vision"
    if (
        "coder" in lower
        or "code" in lower
        or "codestral" in lower
        or "devstral" in lower
    ):
        return "code"
    if "thinking" in cap_set or "deepseek-r1" in lower or "qwq" in lower:
        return "reasoning"
    return "chat"


def _infer_provider(name: str) -> str:
    """Cheap vendor classifier from the model name prefix."""
    lower = name.lower()
    if lower.startswith("llama") or "meta" in lower:
        return "Meta"
    if lower.startswith("qwen"):
        return "Alibaba"
    if lower.startswith("gemma"):
        return "Google"
    if lower.startswith("mistral") or lower.startswith("mixtral"):
        return "Mistral"
    if lower.startswith("phi"):
        return "Microsoft"
    if lower.startswith("deepseek"):
        return "DeepSeek"
    if lower.startswith("granite"):
        return "IBM"
    if lower.startswith("yi"):
        return "01.AI"
    return "Community"


def _parse_block(html: str) -> dict[str, Any] | None:
    """Parse a single model block from the search HTML."""
    title_match = _RE_TITLE.search(html)
    if not title_match:
        return None
    name = title_match.group(1).strip()
    if not name or len(name) > 80:
        return None

    desc_match = _RE_DESC.search(html)
    desc = desc_match.group(1).strip() if desc_match else ""
    # Collapse internal whitespace.
    desc = re.sub(r"\s+", " ", desc)

    sizes = [m.strip() for m in _RE_SIZE.findall(html)]
    pulls_raw = _RE_PULLS.search(html)
    pulls = _parse_pull_count(pulls_raw.group(1)) if pulls_raw else 0
    capabilities = [c.strip() for c in _RE_CAPABILITY.findall(html)]

    return {
        "name": name,
        "desc": desc,
        "sizes": sizes,
        "pulls": pulls,
        "pulls_formatted": _format_pulls(pulls),
        "capabilities": capabilities,
        "category": _infer_category(name, capabilities),
        "provider": _infer_provider(name),
    }


def _parse_search_html(html: str) -> List[dict[str, Any]]:
    # Split on the "title start" marker so each chunk (except the first) is one
    # model block. Drop the first fragment — it's the page header.
    chunks = _BLOCK_SPLIT.split(html)[1:]
    results: List[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        parsed = _parse_block(chunk)
        if parsed is None:
            continue
        if parsed["name"] in seen:
            continue
        seen.add(parsed["name"])
        results.append(parsed)
    return results


# ── Local fallback catalog ────────────────────────────────────────────────

_FALLBACK_MODELS: List[dict[str, Any]] = [
    {
        "name": "llama3.2",
        "desc": "Meta's Llama 3.2 — compact multilingual chat models.",
        "sizes": ["1b", "3b"],
        "pulls": 10_000_000,
        "capabilities": ["tools"],
    },
    {
        "name": "llama3.1",
        "desc": "Meta's Llama 3.1 — larger general-purpose chat models.",
        "sizes": ["8b", "70b"],
        "pulls": 25_000_000,
        "capabilities": ["tools"],
    },
    {
        "name": "qwen2.5",
        "desc": "Alibaba Qwen 2.5 — strong multilingual chat and code.",
        "sizes": ["0.5b", "1.5b", "3b", "7b", "14b", "32b", "72b"],
        "pulls": 8_000_000,
        "capabilities": ["tools"],
    },
    {
        "name": "qwen2.5-coder",
        "desc": "Qwen 2.5 fine-tuned for code generation.",
        "sizes": ["1.5b", "7b", "14b", "32b"],
        "pulls": 5_000_000,
        "capabilities": ["tools"],
    },
    {
        "name": "gemma3",
        "desc": "Google Gemma 3 — lightweight general-purpose models.",
        "sizes": ["1b", "4b", "12b", "27b"],
        "pulls": 4_000_000,
        "capabilities": [],
    },
    {
        "name": "deepseek-r1",
        "desc": "DeepSeek R1 — reasoning-focused, chain-of-thought capable.",
        "sizes": ["1.5b", "7b", "8b", "14b", "32b", "70b"],
        "pulls": 6_000_000,
        "capabilities": ["thinking"],
    },
    {
        "name": "phi4",
        "desc": "Microsoft Phi-4 — small but capable reasoning model.",
        "sizes": ["14b"],
        "pulls": 2_000_000,
        "capabilities": [],
    },
    {
        "name": "mistral",
        "desc": "Mistral 7B — efficient general-purpose chat model.",
        "sizes": ["7b"],
        "pulls": 9_000_000,
        "capabilities": ["tools"],
    },
    {
        "name": "nomic-embed-text",
        "desc": "High-quality open-source text embedding model.",
        "sizes": ["137m"],
        "pulls": 3_500_000,
        "capabilities": ["embedding"],
    },
    {
        "name": "llava",
        "desc": "Llama + vision — multimodal image+text model.",
        "sizes": ["7b", "13b", "34b"],
        "pulls": 4_500_000,
        "capabilities": ["vision"],
    },
]


def _normalize_fallback() -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for entry in _FALLBACK_MODELS:
        caps = entry.get("capabilities", [])
        name = entry["name"]
        out.append(
            {
                **entry,
                "pulls_formatted": _format_pulls(entry.get("pulls", 0)),
                "category": _infer_category(name, caps),
                "provider": _infer_provider(name),
            }
        )
    return out


# ── Public API ────────────────────────────────────────────────────────────


async def get_library(
    query: str | None = None,
    page: int = 1,
    force_refresh: bool = False,
) -> Tuple[List[dict[str, Any]], bool]:
    """Return (models, has_more) for the given query + page.

    ``has_more`` is a heuristic based on result count — when the remote page
    returned a full set we assume another page may exist.
    """
    q = (query or "").strip().lower()
    cache_key = f"{q}::{page}"
    now = time.time()

    if not force_refresh:
        cached = _cache.get(cache_key)
        if cached and (now - cached["t"]) < _CACHE_TTL:
            return cached["models"], cached["has_more"]

    params: dict[str, str] = {}
    if q:
        params["q"] = q
    if page > 1:
        params["p"] = str(page)

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                _OLLAMA_SEARCH_URL,
                params=params,
                headers={
                    "User-Agent": (
                        "StratForgeAI/0.1 (+https://github.com/) ollama-library-scraper"
                    )
                },
            )
            resp.raise_for_status()
            models = _parse_search_html(resp.text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ollama library fetch failed, using fallback: %s", exc)
        if page > 1:
            # No fallback pagination.
            return [], False
        models = _normalize_fallback()

    has_more = len(models) >= 25  # ollama.com returns ~25/page
    _cache[cache_key] = {"t": now, "models": models, "has_more": has_more}
    return models, has_more
