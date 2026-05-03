"""Phase 7 end-to-end smoke — exercise the full tool-dispatcher chain
the way the LLM would invoke it.

Steps:
    1. Create a project + ingest a realistic synthetic "BTC-like" dataset
       (drift + GARCH-ish vol clusters) via the real storage path.
    2. Call `run_backtest` through the tool dispatcher.
    3. Call `monte_carlo` through the tool dispatcher.
    4. Call `walk_forward` through the tool dispatcher (no grid).
    5. Call `score_strategy` through the tool dispatcher with all three IDs.
    6. Print every stage's compact output so we can visually verify the
       whole chain produces coherent numbers.

Run via `python -m scripts.phase7_e2e_smoke` from the backend dir.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Allow `python scripts/phase7_e2e_smoke.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import storage, tool_exec


def _make_btc_like(n: int = 4000, seed: int = 2026) -> pd.DataFrame:
    """Geometric-Brownian-motion-ish series with modest drift + vol clusters."""
    rng = np.random.default_rng(seed)
    base_vol = 0.01
    # 2-state vol regime switching to create the kind of clustering BTC shows
    regime = rng.choice([1.0, 2.5], size=n, p=[0.75, 0.25])
    rets = rng.normal(0.0003, base_vol * regime, size=n)
    price = 30_000 * np.exp(np.cumsum(rets))  # BTC-ish starting point
    idx = pd.date_range("2023-01-01", periods=n, freq="1h")
    close = pd.Series(price, index=idx)
    return pd.DataFrame({
        "time": idx,
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * (1 + np.abs(rng.normal(0, 0.002, size=n))),
        "low": close * (1 - np.abs(rng.normal(0, 0.002, size=n))),
        "close": close,
        "volume": rng.integers(1_000, 100_000, size=n).astype(float),
    })


def _dump(title: str, obj) -> None:
    print(f"\n-- {title} --")
    print(json.dumps(obj, indent=2, default=str)[:1400])


async def main() -> None:
    t_all = time.perf_counter()

    # 1. Project + dataset.
    project = storage.create_project(name="Phase 7 E2E smoke")
    print(f"project={project.id}")
    df = _make_btc_like()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    df.to_csv(tmp_path, index=False)
    ds = storage.ingest_and_store_dataset(project.id, "smoke_btc.csv", tmp_path)
    try:
        tmp_path.unlink(missing_ok=True)
    except Exception:
        pass
    if ds is None:
        raise RuntimeError("ingest failed")
    dataset_id = ds.id
    print(f"dataset={dataset_id} rows={ds.rows}")

    # 2. Strategy spec — simple RSI mean-reversion with stops.
    spec = {
        "name": "rsi_meanrev_btc",
        "market": "crypto",
        "entries": {"all_of": [
            {"indicator": "rsi", "params": {"period": 14}, "op": "<", "value": 30},
        ]},
        "exits": {"all_of": [
            {"indicator": "rsi", "params": {"period": 14}, "op": ">", "value": 70},
        ]},
        "sizing": {"type": "fixed_pct", "value": 0.1},
        "stops": {
            "stop_loss": {"type": "fixed_pct", "value": 0.03},
            "take_profit": {"type": "fixed_pct", "value": 0.06},
        },
    }

    # 3. run_backtest
    bt_resp = await tool_exec.run_tool("run_backtest", {
        "dataset_id": dataset_id, "strategy_spec": spec,
    })
    assert bt_resp["ok"], bt_resp
    bt_id = bt_resp["output"]["backtest_id"]
    _dump("run_backtest", bt_resp["output"])

    # 4. monte_carlo
    mc_resp = await tool_exec.run_tool("monte_carlo", {
        "dataset_id": dataset_id, "strategy_spec": spec,
        "n_iterations": 1000, "seed": 7,
    })
    assert mc_resp["ok"], mc_resp
    mc_id = mc_resp["output"]["monte_carlo_id"]
    _dump("monte_carlo", mc_resp["output"])

    # 5. walk_forward (no grid — stability test)
    wf_resp = await tool_exec.run_tool("walk_forward", {
        "dataset_id": dataset_id, "base_spec": spec,
        "n_folds": 3, "is_oos_split": 0.7, "mode": "rolling",
    })
    assert wf_resp["ok"], wf_resp
    wf_id = wf_resp["output"]["walk_forward_id"]
    _dump("walk_forward", wf_resp["output"])

    # 6. score_strategy with all three IDs
    sc_resp = await tool_exec.run_tool("score_strategy", {
        "backtest_id": bt_id,
        "monte_carlo_id": mc_id,
        "walk_forward_id": wf_id,
    })
    assert sc_resp["ok"], sc_resp
    _dump("score_strategy", sc_resp["output"])

    # Final sanity: also try score_strategy with just the bt_id (IS-only cap).
    sc2 = await tool_exec.run_tool("score_strategy", {"backtest_id": bt_id})
    assert sc2["ok"], sc2
    print(f"\nIS-only score: {sc2['output']['score']:.1f} "
          f"grade={sc2['output']['grade']} verdict={sc2['output']['verdict']}")
    print(f"Full score:    {sc_resp['output']['score']:.1f} "
          f"grade={sc_resp['output']['grade']} verdict={sc_resp['output']['verdict']}")

    print(f"\nE2E total: {time.perf_counter() - t_all:.1f}s")
    print("PHASE 7 E2E SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
