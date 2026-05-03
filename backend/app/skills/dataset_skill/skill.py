"""Dataset Skill — inspect and validate uploaded datasets.

This is a NEW capability not in the original tool set. It gives the AI
the ability to understand dataset quality before running backtests.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ..base import BaseSkill


class Skill(BaseSkill):

    @property
    def name(self) -> str:
        return "dataset"

    @property
    def description(self) -> str:
        return (
            "Inspect and validate uploaded OHLCV datasets: check row count, "
            "date range, column completeness, missing values, and data quality."
        )

    def tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "inspect_dataset",
                "description": (
                    "Return a summary of the dataset: row count, date range, "
                    "columns, missing values, and basic price statistics. "
                    "Use this BEFORE running backtests to verify data quality."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "dataset_id": {
                            "type": "string",
                            "description": "Dataset ID (ds_...) to inspect.",
                        },
                    },
                    "required": ["dataset_id"],
                },
            },
        ]

    async def execute(
        self, tool_name: str, input_: Dict[str, Any], **kw: Any
    ) -> Dict[str, Any]:
        if tool_name == "inspect_dataset":
            return await asyncio.to_thread(self._inspect, input_)
        return {"ok": False, "error": f"Unknown dataset tool: {tool_name}"}

    def _inspect(self, input_: Dict[str, Any]) -> Dict[str, Any]:
        from ... import storage
        from ...data import load_dataset
        import pandas as pd

        dataset_id = input_.get("dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id:
            return {"ok": False, "error": "Missing required `dataset_id`"}

        found = storage._find_dataset_project(dataset_id)
        if found is None:
            return {"ok": False, "error": f"Dataset {dataset_id} not found"}

        project_id, _ = found
        path = storage.dataset_path(project_id, dataset_id)
        if not path.exists():
            return {"ok": False, "error": f"Dataset file missing: {path}"}

        try:
            df = load_dataset(path)
        except Exception as exc:
            return {"ok": False, "error": f"Failed to load dataset: {exc}"}

        # Build summary
        summary: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "rows": len(df),
            "columns": list(df.columns),
        }

        # Date range
        if "time" in df.columns:
            times = pd.to_datetime(df["time"], errors="coerce")
            valid = times.dropna()
            if len(valid) > 0:
                summary["start_date"] = str(valid.iloc[0])
                summary["end_date"] = str(valid.iloc[-1])

        # OHLCV check
        ohlcv = ["open", "high", "low", "close", "volume"]
        present = [c for c in ohlcv if c in df.columns]
        missing = [c for c in ohlcv if c not in df.columns]
        summary["ohlcv_present"] = present
        summary["ohlcv_missing"] = missing
        summary["has_full_ohlcv"] = len(missing) == 0

        # Missing values
        null_counts = {c: int(df[c].isna().sum()) for c in present}
        summary["null_counts"] = null_counts

        # Price stats (close)
        if "close" in df.columns:
            close = df["close"].dropna()
            if len(close) > 0:
                summary["price_stats"] = {
                    "min": round(float(close.min()), 4),
                    "max": round(float(close.max()), 4),
                    "mean": round(float(close.mean()), 4),
                    "std": round(float(close.std()), 4),
                    "latest": round(float(close.iloc[-1]), 4),
                }

        # Quality verdict
        issues: List[str] = []
        if missing:
            issues.append(f"Missing OHLCV columns: {missing}")
        if any(v > 0 for v in null_counts.values()):
            issues.append(f"Null values detected: {null_counts}")
        if len(df) < 200:
            issues.append(f"Only {len(df)} rows — need 200+ for reliable backtests")

        summary["quality"] = "good" if not issues else "warning"
        summary["issues"] = issues

        return {"ok": True, "output": summary}
