"""Phase 8 end-to-end smoke — exercise the full report pipeline.

Steps:
    1. Spin up a fresh project + ingest a synthetic "BTC-like" dataset.
    2. Run backtest -> monte_carlo -> walk_forward via the tool dispatcher.
    3. Call `render_report` via the dispatcher to build the HTML.
    4. Hit the PDF export path (Playwright) and confirm a non-trivial PDF.
    5. Re-hit the PDF path to confirm caching short-circuits.
    6. Open the rendered HTML, verify all requested sections are present.

Run from backend dir:
    python -m scripts.phase8_e2e_smoke
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import storage, tool_exec
from app.reports import export_pdf, report_paths, load_report_metadata


def _make_btc_like(n: int = 4000, seed: int = 2026) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base_vol = 0.01
    regime = rng.choice([1.0, 2.5], size=n, p=[0.75, 0.25])
    rets = rng.normal(0.0003, base_vol * regime, size=n)
    price = 30_000 * np.exp(np.cumsum(rets))
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


async def main() -> None:
    t_all = time.perf_counter()

    # 1. Project + dataset
    project = storage.create_project(name="Phase 8 E2E smoke")
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

    # 2. Strategy spec
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

    # 3. Backtest + MC + WF
    bt = await tool_exec.run_tool("run_backtest", {
        "dataset_id": dataset_id, "strategy_spec": spec,
    })
    assert bt["ok"], bt
    bt_id = bt["output"]["backtest_id"]
    print(f"bt={bt_id}")

    mc = await tool_exec.run_tool("monte_carlo", {
        "dataset_id": dataset_id, "strategy_spec": spec,
        "n_iterations": 500, "seed": 7,
    })
    assert mc["ok"], mc
    mc_id = mc["output"]["monte_carlo_id"]
    print(f"mc={mc_id}")

    wf = await tool_exec.run_tool("walk_forward", {
        "dataset_id": dataset_id, "base_spec": spec,
        "n_folds": 3, "is_oos_split": 0.7, "mode": "rolling",
    })
    assert wf["ok"], wf
    wf_id = wf["output"]["walk_forward_id"]
    print(f"wf={wf_id}")

    # 4. render_report (via dispatcher)
    t_render = time.perf_counter()
    rep = await tool_exec.run_tool("render_report", {
        "backtest_id": bt_id,
        "monte_carlo_id": mc_id,
        "walk_forward_id": wf_id,
    })
    assert rep["ok"], rep
    rp_id = rep["output"]["report_id"]
    print(f"report={rp_id} grade={rep['output']['grade']} "
          f"verdict={rep['output']['verdict']} score={rep['output']['score']:.1f}")
    print(f"   render elapsed: {(time.perf_counter() - t_render) * 1000:.0f}ms")

    # Verify metadata sidecar + HTML content
    meta = load_report_metadata(project.id, rp_id)
    assert meta is not None
    print(f"   sections={meta['sections']}")

    paths = report_paths(project.id, rp_id)
    html_text = paths["html"].read_text(encoding="utf-8")
    for marker in ("Backtest Report", "Headline metrics", "Walk-forward",
                   "Monte Carlo", "Verdict", "<script", "plotly"):
        assert marker.lower() in html_text.lower(), f"HTML missing '{marker}'"
    assert len(html_text) > 20_000, f"HTML seems truncated ({len(html_text)} chars)"
    print(f"   html bytes: {len(html_text):,}")

    # 5. PDF export (first call - renders)
    t_pdf = time.perf_counter()
    pdf_path = await export_pdf(project.id, rp_id)
    cold_ms = (time.perf_counter() - t_pdf) * 1000
    pdf_bytes = pdf_path.stat().st_size
    print(f"pdf cold render: {cold_ms:.0f}ms  size={pdf_bytes:,} bytes")
    assert pdf_bytes > 20_000, f"PDF suspiciously small: {pdf_bytes}"

    # 6. PDF export (second call - should short-circuit to cache)
    t_pdf2 = time.perf_counter()
    pdf_path2 = await export_pdf(project.id, rp_id)
    warm_ms = (time.perf_counter() - t_pdf2) * 1000
    print(f"pdf warm render: {warm_ms:.0f}ms  (cache hit)")
    assert pdf_path == pdf_path2
    assert warm_ms < cold_ms / 2, "Cache short-circuit didn't fire"

    # 7. Sanity — render another report with ONLY backtest_id to confirm
    # optional sections degrade gracefully.
    rep2 = await tool_exec.run_tool("render_report", {"backtest_id": bt_id})
    assert rep2["ok"], rep2
    rp2_id = rep2["output"]["report_id"]
    meta2 = load_report_metadata(project.id, rp2_id)
    assert "walkforward" not in meta2["sections"]
    assert "montecarlo" not in meta2["sections"]
    assert "verdict" in meta2["sections"]
    print(f"\nIS-only report: {rp2_id} sections={meta2['sections']}")

    print(f"\nE2E total: {time.perf_counter() - t_all:.1f}s")
    print("PHASE 8 E2E SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
