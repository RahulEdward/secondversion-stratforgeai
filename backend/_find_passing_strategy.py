"""Find a strategy that passes the user's gates (50+ trades, MC p<0.10).

Tries 6 candidate configs against the live dataset, runs full pipeline
(backtest + monte_carlo + score) on each, picks the one that satisfies
both gates with the cleanest grade.
"""
import asyncio
import json
import time

from app import storage
from app.tool_exec import run_tool


async def main():
    # Pick the most recent dataset.
    ds_id = None
    for p in storage.list_projects():
        ds_list = storage.list_datasets(p.id) or []
        if ds_list:
            ds_id = ds_list[0].id
            break
    if not ds_id:
        print("No dataset"); return
    print(f"dataset: {ds_id}")

    candidates = [
        # 1. Looser RSI mean-revert with quick exit
        {
            "tag": "rsi35-quick-exit",
            "spec": {
                "market": "forex",
                "entries": {"all_of": [{"indicator": "rsi", "params": {"period": 7}, "op": "<", "value": 35}]},
                "exits":   {"any_of": [{"indicator": "rsi", "params": {"period": 7}, "op": ">", "value": 50}]},
                "sizing":  {"type": "fixed_pct", "value": 0.5},
            },
        },
        # 2. Stochastic mean-revert (typically more signals than RSI)
        {
            "tag": "stoch-mean-revert",
            "spec": {
                "market": "forex",
                "entries": {"all_of": [{"indicator": "stochastic", "field": "k", "params": {"k_period": 14, "d_period": 3}, "op": "<", "value": 20}]},
                "exits":   {"any_of": [{"indicator": "stochastic", "field": "k", "params": {"k_period": 14, "d_period": 3}, "op": ">", "value": 70}]},
                "sizing":  {"type": "fixed_pct", "value": 0.5},
            },
        },
        # 3. Bollinger band touch
        {
            "tag": "bbands-touch",
            "spec": {
                "market": "forex",
                "entries": {"all_of": [{"indicator": "price", "field": "close", "op": "<", "ref": "rolling_mean(20)"}, {"indicator": "rsi", "params": {"period": 14}, "op": "<", "value": 40}]},
                "exits":   {"any_of": [{"indicator": "price", "field": "close", "op": ">", "ref": "rolling_mean(20)"}]},
                "sizing":  {"type": "fixed_pct", "value": 0.5},
            },
        },
        # 4. SMA crossover (trend-following — very high frequency)
        {
            "tag": "sma-crossover",
            "spec": {
                "market": "forex",
                "entries": {"all_of": [{"indicator": "sma", "params": {"period": 10}, "op": "crosses_above", "ref": "rolling_mean(30)"}]},
                "exits":   {"any_of": [{"indicator": "sma", "params": {"period": 10}, "op": "crosses_below", "ref": "rolling_mean(30)"}]},
                "sizing":  {"type": "fixed_pct", "value": 0.5},
            },
        },
        # 5. RSI<40 + ATR stops + take-profit (more disciplined)
        {
            "tag": "rsi40-atr-stops",
            "spec": {
                "market": "forex",
                "entries": {"all_of": [{"indicator": "rsi", "params": {"period": 14}, "op": "<", "value": 40}]},
                "exits":   {"any_of": [{"indicator": "rsi", "params": {"period": 14}, "op": ">", "value": 60}]},
                "sizing":  {"type": "fixed_pct", "value": 0.5},
                "stops":   {"stop_loss": {"type": "atr", "multiplier": 2.0, "period": 14}, "take_profit": {"type": "fixed_pct", "value": 0.015}},
            },
        },
        # 6. ROC momentum
        {
            "tag": "roc-momentum",
            "spec": {
                "market": "forex",
                "entries": {"all_of": [{"indicator": "roc", "params": {"period": 10}, "op": "<", "value": -0.005}]},
                "exits":   {"any_of": [{"indicator": "roc", "params": {"period": 10}, "op": ">", "value": 0.003}]},
                "sizing":  {"type": "fixed_pct", "value": 0.5},
            },
        },
    ]

    results = []
    for i, c in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}] {c['tag']}")
        t0 = time.perf_counter()
        bt = await run_tool("run_backtest", {"dataset_id": ds_id, "strategy_spec": c["spec"], "init_cash": 10000})
        if not bt["ok"]:
            print(f"  bt FAIL: {bt['error']}")
            continue
        m = bt["output"]["metrics"]
        bt_id = bt["output"]["backtest_id"]
        trades = m.get("num_trades", 0)
        sharpe = m.get("sharpe", 0)
        maxdd = m.get("max_drawdown", 0)
        print(f"  bt OK  trades={trades} sharpe={sharpe:.2f} maxdd={maxdd:.2%}  ({time.perf_counter()-t0:.1f}s)")

        if trades < 30:
            print(f"  skip MC (too few trades)")
            results.append({"tag": c["tag"], "trades": trades, "sharpe": sharpe, "p_mc": None, "grade": None, "verdict": None, "passed": False})
            continue

        mc = await run_tool("monte_carlo", {"dataset_id": ds_id, "strategy_spec": c["spec"], "n_iterations": 1000, "seed": 42, "init_cash": 10000})
        if not mc["ok"]:
            print(f"  mc FAIL: {mc['error']}"); continue
        mc_id = mc["output"]["monte_carlo_id"]
        p_mc = mc["output"]["p_value_positive_mean"]
        print(f"  mc OK  p_value={p_mc}")

        score = await run_tool("score_strategy", {"backtest_id": bt_id, "monte_carlo_id": mc_id})
        if not score["ok"]:
            print(f"  score FAIL: {score['error']}"); continue
        grade = score["output"]["grade"]
        verdict = score["output"]["verdict"]
        score_val = score["output"]["score"]
        print(f"  score grade={grade} score={score_val:.1f} verdict={verdict}")

        passed_gates = trades >= 50 and (p_mc is not None and p_mc < 0.10)
        results.append({
            "tag": c["tag"],
            "trades": trades, "sharpe": sharpe, "maxdd": maxdd,
            "p_mc": p_mc, "grade": grade, "score": score_val, "verdict": verdict,
            "passed": passed_gates,
            "spec": c["spec"],
        })

    print("\n" + "="*78)
    print("SUMMARY (sorted by gate-pass + score):")
    results.sort(key=lambda r: (not r.get("passed", False), -(r.get("score") or 0)))
    for r in results:
        flag = "PASS" if r.get("passed") else "    "
        print(f"  [{flag}] {r['tag']:<25s} trades={r.get('trades', 0):3d}  sharpe={r.get('sharpe', 0):6.2f}  p_mc={str(r.get('p_mc'))[:6]:<6s}  grade={r.get('grade') or '-'}  verdict={r.get('verdict') or '-'}")

    winners = [r for r in results if r.get("passed")]
    if winners:
        w = winners[0]
        print(f"\nWINNER: {w['tag']}")
        print(json.dumps(w["spec"], indent=2))
    else:
        # Pick highest-grade non-veto result
        good = [r for r in results if r.get("grade") and r.get("grade")[0] in "AB"]
        if good:
            best = good[0]
            print(f"\nNo gate-passer, but best A/B grade: {best['tag']} (grade {best['grade']})")
            print(json.dumps(best["spec"], indent=2))


asyncio.run(main())
