"""Indicator tools — let the agent use StratForge's 68 built-in indicators
directly, and add new ones to the library when the user requests something
that doesn't already exist.

Rationale: Vibe-Trading's default agent writes indicator formulas from
scratch inside signal_engine.py every time. StratForge already ships 68
production-quality indicator implementations under app/indicators/ with a
clean ``compute(df, **params) -> pd.Series|DataFrame`` contract. This
module exposes those to the agent so it:

1. Calls ``list_indicators`` first to see what's available.
2. Calls ``use_indicator`` to import + invoke any of the 68 built-ins —
   agent strategy code becomes ``from app.indicators import compute``.
3. Calls ``add_indicator`` when the user asks for something novel — the
   new ``.py`` file lands in app/indicators/ and is immediately available
   to every future session.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.agents.tools import BaseTool

logger = logging.getLogger(__name__)

INDICATORS_DIR = Path(__file__).resolve().parents[1] / "indicators"


# ── list_indicators ──────────────────────────────────────────────────────

def list_indicators_fn() -> str:
    """Return every installed indicator's name, description, and default params."""
    try:
        from app.indicators import INDICATOR_REGISTRY
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": "error", "error": f"Registry unavailable: {exc}"})

    out = []
    for name in sorted(INDICATOR_REGISTRY.keys()):
        entry = INDICATOR_REGISTRY[name]
        out.append({
            "name": name,
            "description": entry.get("description", ""),
            "default_params": entry.get("params", {}),
        })
    return json.dumps({"status": "ok", "count": len(out), "indicators": out}, ensure_ascii=False)


class ListIndicatorsTool(BaseTool):
    name = "list_indicators"
    description = (
        "List every indicator already installed in the StratForge library. "
        "ALWAYS call this first before writing a strategy — 68+ indicators "
        "(RSI, MACD, EMA, SuperTrend, Ichimoku, Bollinger, ATR, VWAP, and "
        "many more) are ready to use. Only write custom math if you can't "
        "find a match here."
    )
    parameters = {"type": "object", "properties": {}}
    repeatable = False
    is_readonly = True

    def execute(self, **kwargs) -> str:
        return list_indicators_fn()


# ── use_indicator ────────────────────────────────────────────────────────

def use_indicator_fn(name: str, dataset_id: str, params: dict | None = None, tail: int = 500) -> str:
    """Compute an indicator on an uploaded dataset and return the last `tail` rows.

    This is the cheap path the agent uses when it wants to *see* what an
    indicator does on the user's data before wiring it into signal_engine.py.
    """
    try:
        from app.indicators import INDICATOR_REGISTRY, compute
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": "error", "error": f"Registry unavailable: {exc}"})

    if name not in INDICATOR_REGISTRY:
        available = ", ".join(sorted(INDICATOR_REGISTRY.keys())[:20])
        return json.dumps({
            "status": "error",
            "error": (
                f"Indicator '{name}' not found. Known indicators include: "
                f"{available}… Call list_indicators for the full set, "
                f"or add_indicator to write a new one."
            ),
        })

    # Load the dataset via StratForge's storage layer
    try:
        from app import storage
        ds = storage.get_dataset(dataset_id)
        if ds is None:
            return json.dumps({"status": "error", "error": f"Dataset {dataset_id} not found"})
        row = storage._find_dataset_project(dataset_id)
        if row is None:
            return json.dumps({"status": "error", "error": f"Dataset {dataset_id} has no project"})
        project_id = row[0]
        parquet_path = storage.dataset_path(project_id, dataset_id)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": "error", "error": f"Dataset lookup failed: {exc}"})

    if not parquet_path.exists():
        return json.dumps({"status": "error", "error": f"Parquet missing: {parquet_path}"})

    try:
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        # Canonicalize column names (lowercase)
        df.columns = [str(c).lower() for c in df.columns]
        result = compute(df, name, params or {})
        # Return tail as records
        tail_df = result.tail(int(tail))
        return json.dumps({
            "status": "ok",
            "indicator": name,
            "params": params or {},
            "rows": len(result),
            "columns": list(result.columns),
            "sample": tail_df.round(6).to_dict(orient="records")[-10:],  # last 10 only for brevity
            "message": (
                f"Indicator '{name}' computed on {len(result)} bars. "
                f"Use from app.indicators import compute in signal_engine.py "
                f"to access it during backtest."
            ),
        }, ensure_ascii=False)
    except Exception as exc:
        logger.exception("use_indicator failed")
        return json.dumps({"status": "error", "error": f"Compute failed: {exc}"})


class UseIndicatorTool(BaseTool):
    name = "use_indicator"
    description = (
        "Run one of the 68 built-in indicators on an uploaded dataset and "
        "return recent values. Use this to validate that an indicator works "
        "on the user's data before writing your strategy. In signal_engine.py, "
        "import via: `from app.indicators import compute` then call "
        "`compute(df, 'rsi', {'period': 14})`."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Indicator name (e.g. 'rsi', 'ema', 'macd'). Use list_indicators for the full set."},
            "dataset_id": {"type": "string", "description": "StratForge dataset_id"},
            "params": {"type": "object", "description": "Indicator parameters, e.g. {\"period\": 14}. Defaults are used if omitted."},
            "tail": {"type": "integer", "description": "How many recent rows to return. Default 500."},
        },
        "required": ["name", "dataset_id"],
    }
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs) -> str:
        return use_indicator_fn(
            name=kwargs["name"],
            dataset_id=kwargs["dataset_id"],
            params=kwargs.get("params") or {},
            tail=kwargs.get("tail", 500),
        )


# ── add_indicator ────────────────────────────────────────────────────────

_VALID_MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


_INDICATOR_TEMPLATE = '''"""{description}"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = {description_repr}
PARAMS = {params_repr}


def compute(df: pd.DataFrame, {signature}) -> pd.Series:
    """{docstring}"""
{body}
'''


def add_indicator_fn(
    name: str,
    description: str,
    params: dict | None,
    body: str,
    required_columns: list[str] | None = None,
) -> str:
    """Write a new indicator module into app/indicators/ and register it.

    The file must follow the library contract:
        - A DESCRIPTION string
        - A PARAMS dict of default values
        - A compute(df, **params) -> pd.Series function

    `body` is the body of the compute() function (already indented).
    The system appends a `return` at the end if you want, but typically
    pass a complete body ending with `return ...`.
    """
    if not _VALID_MODULE_NAME.match(name):
        return json.dumps({
            "status": "error",
            "error": "Indicator name must be snake_case, start with a letter, no spaces or special chars.",
        })

    target = INDICATORS_DIR / f"{name}.py"
    if target.exists():
        return json.dumps({
            "status": "error",
            "error": f"Indicator '{name}' already exists. Use use_indicator instead, or pick a new name.",
        })

    params = params or {}
    required_columns = required_columns or ["close"]

    # Build function signature from params
    if params:
        sig_parts = [f"{k}: {_type_hint(v)} = {repr(v)}" for k, v in params.items()]
        signature = ", ".join(sig_parts)
    else:
        signature = ""

    # Indent the body to 4 spaces
    indented_body = "\n".join(
        ("    " + line) if line.strip() else line
        for line in body.splitlines()
    )

    # If body doesn't start with require(...), prepend one so required_columns are enforced
    if "require(" not in body:
        req_line = f"    require(df, {required_columns!r}, {name.upper()!r})\n"
        indented_body = req_line + indented_body

    content = _INDICATOR_TEMPLATE.format(
        description=description,
        description_repr=repr(description),
        params_repr=repr(params),
        signature=signature,
        docstring=f"Compute {name} indicator.",
        body=indented_body,
    )

    try:
        target.write_text(content, encoding="utf-8")
    except Exception as exc:
        return json.dumps({"status": "error", "error": f"Write failed: {exc}"})

    # Hot-register into the running process so the current session can use it
    try:
        import importlib
        import app.indicators as _pkg

        module = importlib.import_module(f"app.indicators.{name}")
        if hasattr(module, "compute"):
            _pkg.INDICATOR_REGISTRY[name] = {
                "fn": module.compute,
                "description": getattr(module, "DESCRIPTION", description),
                "params": getattr(module, "PARAMS", params),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Hot-register failed for %s: %s", name, exc)
        return json.dumps({
            "status": "ok",
            "warning": f"File written but hot-import failed ({exc}). Restart the app to use it.",
            "path": str(target),
        })

    return json.dumps({
        "status": "ok",
        "name": name,
        "path": str(target),
        "message": (
            f"Indicator '{name}' registered. Available immediately via "
            f"compute(df, '{name}', params) and in future sessions."
        ),
    })


def _type_hint(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    return "Any"


class AddIndicatorTool(BaseTool):
    name = "add_indicator"
    description = (
        "Add a brand new indicator to StratForge's library so it's available "
        "permanently (not just for this session). Use ONLY when list_indicators "
        "doesn't already have what the user asked for. The new file lives at "
        "app/indicators/<name>.py and is auto-registered. Body must compute "
        "from df columns (open/high/low/close/volume) and end with `return <Series>`."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "snake_case indicator name, e.g. 'awesome_oscillator'"},
            "description": {"type": "string", "description": "One-line description shown in list_indicators"},
            "params": {"type": "object", "description": "Default parameter values, e.g. {\"fast\": 5, \"slow\": 34}"},
            "body": {
                "type": "string",
                "description": (
                    "Python body of the compute() function. Must end with `return <Series>`. "
                    "Example: `high_low = (df['high'] + df['low']) / 2\\nao = high_low.rolling(fast).mean() - high_low.rolling(slow).mean()\\nreturn ao.rename('awesome_oscillator')`"
                ),
            },
            "required_columns": {"type": "array", "items": {"type": "string"}, "description": "Columns required from df (default ['close'])"},
        },
        "required": ["name", "description", "body"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs) -> str:
        return add_indicator_fn(
            name=kwargs["name"],
            description=kwargs["description"],
            params=kwargs.get("params") or {},
            body=kwargs["body"],
            required_columns=kwargs.get("required_columns"),
        )
