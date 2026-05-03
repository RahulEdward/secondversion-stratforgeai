"""End-to-end smoke test — phase by phase, full pipeline.

Run from backend dir:  python _smoke_e2e.py
"""
import asyncio
import json
import sys
import time

from app import storage
from app.tool_exec import run_tool
from app.tools import all_tools, indicator_tools

results = {}


def _line(name, ok, ms, detail):
    flag = "OK  " if ok else "FAIL"
    msg = f"[{flag}] {name:<46s} {ms:6.0f} ms"
    if not ok:
        msg += f"  -> {detail}"
    print(msg, flush=True)


async def step(name, fn):
    t0 = time.perf_counter()
    try:
        out = await fn() if asyncio.iscoroutinefunction(fn) else fn()
        dt = (time.perf_counter() - t0) * 1000
        results[name] = {"ok": True, "ms": round(dt), "detail": out}
        _line(name, True, dt, out)
        return out
    except Exception as e:
        dt = (time.perf_counter() - t0) * 1000
        msg = f"{type(e).__name__}: {e}"
        results[name] = {"ok": False, "ms": round(dt), "error": msg}
        _line(name, False, dt, msg)
        return None


async def main():
    # ── Phase 2 — projects + sessions ────────────────────────────────────
    def s_projects():
        ps = storage.list_projects()
        return f"{len(ps)} projects"

    await step("Phase2.Projects.list", s_projects)

    def s_sessions():
        ps = storage.list_projects()
        total = sum(len(storage.list_sessions(p.id) or []) for p in ps)
        return f"{total} sessions across {len(ps)} projects"

    await step("Phase2.Sessions.list (per project)", s_sessions)

    # ── Phase 3 — datasets + indicators ──────────────────────────────────
    ds_all = []

    def s_datasets():
        ps = storage.list_projects()
        for p in ps:
            for d in storage.list_datasets(p.id) or []:
                ds_all.append((p.id, d))
        return f"{len(ds_all)} datasets across all projects"

    await step("Phase3.Datasets.list", s_datasets)
    if not ds_all:
        print("\n!! NO DATASET — pipeline aborted")
        return
    pid, ds = ds_all[0]
    print(
        f"     using dataset: {ds.id} ({ds.filename}, {ds.rows} rows, "
        f"ohlcv={ds.has_ohlcv}, range {ds.start_date} -> {ds.end_date})"
    )

    await step(
        "Phase3.Tools.indicator_count",
        lambda: f"{len(indicator_tools())} indicator tool schemas",
    )

    async def s_rsi():
        r = await run_tool("compute_rsi", {"dataset_id": ds.id, "period": 14})
        if not r["ok"]:
            raise RuntimeError(r["error"])
        last = r["output"]["tail"][-1]
        return f'rows={r["output"]["rows"]} last_rsi={last.get("rsi_14"):.2f}'

    await step("Phase3.compute_rsi(14)", s_rsi)

    async def s_macd():
        r = await run_tool(
            "compute_macd",
            {"dataset_id": ds.id, "fast": 12, "slow": 26, "signal": 9},
        )
        if not r["ok"]:
            raise RuntimeError(r["error"])
        return f'cols={r["output"]["columns"]}'

    await step("Phase3.compute_macd(12,26,9)", s_macd)

    async def s_bb():
        r = await run_tool(
            "compute_bollinger_bands",
            {"dataset_id": ds.id, "period": 20, "std": 2.0},
        )
        if not r["ok"]:
            raise RuntimeError(r["error"])
        return f'cols={r["output"]["columns"]}'

    await step("Phase3.compute_bollinger_bands(20,2)", s_bb)

    async def s_atr():
        r = await run_tool(
            "compute_atr", {"dataset_id": ds.id, "period": 14}
        )
        if not r["ok"]:
            raise RuntimeError(r["error"])
        return f'cols={r["output"]["columns"]}'

    await step("Phase3.compute_atr(14)", s_atr)

    # ── Phase 4 — providers ──────────────────────────────────────────────
    def s_provs():
        from app.providers import PROVIDER_NAMES

        return list(PROVIDER_NAMES)

    await step("Phase4.Providers.registered", s_provs)

    # ── Phase 6 — tool aggregator ────────────────────────────────────────
    def s_all_tools():
        return f"{len(all_tools())} total tool schemas exposed to LLM"

    await step("Phase6.all_tools.count", s_all_tools)

    def s_critical():
        ts = {t["name"] for t in all_tools()}
        critical = [
            "run_backtest",
            "optimize_strategy",
            "walk_forward",
            "monte_carlo",
            "score_strategy",
            "render_report",
            "save_strategy",
            "load_strategy",
            "list_strategies",
        ]
        missing = [c for c in critical if c not in ts]
        if missing:
            raise RuntimeError(f"missing: {missing}")
        return "all 9 critical Phase 7-9 tools present"

    await step("Phase6.all_tools.has_critical_set", s_critical)

    # ── Build a simple StrategySpec ──────────────────────────────────────
    spec = {
        "name": "rsi_mean_revert_smoke",
        "market": "forex",
        "entries": {
            "all_of": [
                {
                    "indicator": "rsi",
                    "params": {"period": 14},
                    "op": "<",
                    "value": 30,
                }
            ]
        },
        "exits": {
            "any_of": [
                {
                    "indicator": "rsi",
                    "params": {"period": 14},
                    "op": ">",
                    "value": 55,
                }
            ]
        },
        "sizing": {"type": "fixed_pct", "value": 1.0},
    }

    # ── Phase 7.1 — run_backtest ─────────────────────────────────────────
    bt_id = None

    async def s_bt():
        nonlocal bt_id
        r = await run_tool(
            "run_backtest",
            {"dataset_id": ds.id, "strategy_spec": spec, "init_cash": 10000},
        )
        if not r["ok"]:
            raise RuntimeError(r["error"])
        o = r["output"]
        bt_id = o["backtest_id"]
        m = o["metrics"]
        return (
            f'bt={bt_id} sharpe={m.get("sharpe"):.2f} '
            f'trades={m.get("num_trades")} maxdd={m.get("max_drawdown"):.2%}'
        )

    await step("Phase7.run_backtest", s_bt)

    # ── Phase 7.2 — optimize_strategy ────────────────────────────────────
    async def s_opt():
        grid = {
            "entries.all_of.0.value": [25, 30, 35],
            "entries.all_of.0.params.period": [10, 14],
        }
        r = await run_tool(
            "optimize_strategy",
            {
                "dataset_id": ds.id,
                "base_spec": spec,
                "grid": grid,
                "top_n": 3,
                "min_trades": 5,
                "max_combinations": 6,
                "init_cash": 10000,
            },
        )
        if not r["ok"]:
            raise RuntimeError(r["error"])
        o = r["output"]
        top = [(t["point"], round(t["score"], 3)) for t in o["top_n"][:2]]
        return f'opt={o["opt_id"]} combos={o["n_combinations"]} passed={o["n_passed"]} top2={top}'

    await step("Phase7.optimize_strategy(2x3 grid)", s_opt)

    # ── Phase 7.3 — walk_forward ─────────────────────────────────────────
    wf_id = None

    async def s_wf():
        nonlocal wf_id
        r = await run_tool(
            "walk_forward",
            {
                "dataset_id": ds.id,
                "base_spec": spec,
                "n_folds": 3,
                "is_oos_split": 0.7,
                "min_trades": 3,
                "init_cash": 10000,
            },
        )
        if not r["ok"]:
            raise RuntimeError(r["error"])
        o = r["output"]
        wf_id = o["walk_forward_id"]
        return f'wf={wf_id} wfe={o["wfe"]} verdict={o["verdict"]} folds={len(o["folds"])}'

    await step("Phase7.walk_forward(3 folds)", s_wf)

    # ── Phase 7.4 — monte_carlo ──────────────────────────────────────────
    mc_id = None

    async def s_mc():
        nonlocal mc_id
        r = await run_tool(
            "monte_carlo",
            {
                "dataset_id": ds.id,
                "strategy_spec": spec,
                "n_iterations": 500,
                "seed": 42,
                "init_cash": 10000,
            },
        )
        if not r["ok"]:
            raise RuntimeError(r["error"])
        o = r["output"]
        mc_id = o["monte_carlo_id"]
        return f'mc={mc_id} p_positive={o["p_value_positive_mean"]} verdict={o["verdict"]}'

    await step("Phase7.monte_carlo(500 iters)", s_mc)

    # ── Phase 7.5 — score_strategy ───────────────────────────────────────
    async def s_score():
        if not bt_id:
            raise RuntimeError("no backtest_id from earlier step")
        payload = {"backtest_id": bt_id}
        if mc_id:
            payload["monte_carlo_id"] = mc_id
        if wf_id:
            payload["walk_forward_id"] = wf_id
        r = await run_tool("score_strategy", payload)
        if not r["ok"]:
            raise RuntimeError(r["error"])
        o = r["output"]
        return f'grade={o["grade"]} score={o["score"]:.2f} verdict={o["verdict"]} vetos={len(o["vetos"])}'

    await step("Phase7.score_strategy(bt+mc+wf)", s_score)

    # ── Phase 8 — render_report ──────────────────────────────────────────
    rid = None

    async def s_report():
        nonlocal rid
        if not bt_id:
            raise RuntimeError("no backtest_id")
        payload = {"backtest_id": bt_id}
        if mc_id:
            payload["monte_carlo_id"] = mc_id
        if wf_id:
            payload["walk_forward_id"] = wf_id
        r = await run_tool("render_report", payload)
        if not r["ok"]:
            raise RuntimeError(r["error"])
        o = r["output"]
        rid = o["report_id"]
        return f'report={rid} sections={len(o["sections"])} html={o["html_url"]} pdf={o["pdf_url"]}'

    await step("Phase8.render_report", s_report)

    # ── Phase 8b — verify report HTML actually serves ────────────────────
    async def s_report_get():
        if not rid:
            raise RuntimeError("no report_id")
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"http://127.0.0.1:8765/api/reports/{rid}")
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
        size = len(r.content)
        ct = r.headers.get("content-type", "")
        return f"HTTP 200, {size} bytes, content-type={ct}"

    await step("Phase8.GET /api/reports/{id}", s_report_get)

    # ── Phase 9 — strategy library ───────────────────────────────────────
    sid = None

    async def s_save():
        nonlocal sid
        if not bt_id:
            raise RuntimeError("no backtest_id")
        r = await run_tool(
            "save_strategy",
            {"name": f"smoke_test_{int(time.time())}", "backtest_id": bt_id},
        )
        if not r["ok"]:
            raise RuntimeError(r["error"])
        o = r["output"]
        sid = o["strategy_id"]
        return f'strategy={sid} name={o["name"]} grade={o.get("grade")}'

    await step("Phase9.save_strategy", s_save)

    async def s_list():
        r = await run_tool("list_strategies", {})
        if not r["ok"]:
            raise RuntimeError(r["error"])
        return f'{r["output"]["count"]} strategies in library'

    await step("Phase9.list_strategies", s_list)

    async def s_load():
        if not sid:
            raise RuntimeError("no strategy_id")
        r = await run_tool("load_strategy", {"strategy_id": sid})
        if not r["ok"]:
            raise RuntimeError(r["error"])
        keys = list(r["output"]["strategy_spec"].keys())
        return f'loaded "{r["output"]["name"]}" (spec keys: {keys})'

    await step("Phase9.load_strategy", s_load)

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print("=" * 78)
    ok = sum(1 for v in results.values() if v["ok"])
    total = len(results)
    print(f"RESULT: {ok}/{total} passed")
    if ok < total:
        print("\nFailures:")
        for name, v in results.items():
            if not v["ok"]:
                print(f"  - {name}: {v['error']}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
