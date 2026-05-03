"""Probe the live WebSocket — send one prompt, capture every frame.

Bypasses the frontend entirely so we can see exactly what GPT-5.4 emits:
text-only or tool_use frames. If tool_use frames appear, the model IS
calling tools and the UI is just rendering them oddly. If only text
frames appear, there's a real provider/wire bug to chase.
"""
import asyncio
import json
import sys
import time

import httpx
import websockets


BACKEND = "http://127.0.0.1:8765"
WS_BASE = "ws://127.0.0.1:8765"


async def main():
    # 1. Pick the most recent dataset (used by the active session).
    async with httpx.AsyncClient() as c:
        ps = (await c.get(f"{BACKEND}/api/projects")).json()
        # Find a project that has a dataset AND a gpt-5.4 session.
        target_pid = None
        target_did = None
        target_sid = None
        for p in ps:
            ds = (await c.get(f"{BACKEND}/api/projects/{p['id']}/datasets")).json()
            ss = (await c.get(f"{BACKEND}/api/projects/{p['id']}/sessions")).json()
            if not ds or not ss:
                continue
            for s in ss:
                if s.get("provider") == "chatgpt-subscription" and s.get("model") == "gpt-5.4":
                    target_pid = p["id"]
                    target_did = ds[0]["id"]
                    target_sid = s["id"]
                    break
            if target_sid:
                break
        if target_sid is None:
            # Fallback: create a fresh session on the first project with a dataset.
            for p in ps:
                ds = (await c.get(f"{BACKEND}/api/projects/{p['id']}/datasets")).json()
                if ds:
                    target_pid = p["id"]
                    target_did = ds[0]["id"]
                    new = (await c.post(
                        f"{BACKEND}/api/projects/{p['id']}/sessions",
                        json={"title": "ws_probe"},
                    )).json()
                    target_sid = new["id"]
                    await c.patch(
                        f"{BACKEND}/api/sessions/{target_sid}/model",
                        json={"provider": "chatgpt-subscription", "model": "gpt-5.4"},
                    )
                    break

    if target_sid is None:
        print("No project with a dataset found — aborting.")
        sys.exit(1)

    print(f"target session: {target_sid}")
    print(f"target dataset: {target_did}")
    print()

    # 2. Open WS, send a tightly-scoped prompt, capture frames.
    prompt = (
        "Run compute_rsi(period=14) on the active dataset, then call "
        "run_backtest with this minimal strategy_spec: "
        '{"market":"forex","entries":{"all_of":[{"indicator":"rsi","params":{"period":14},"op":"<","value":30}]},'
        '"exits":{"any_of":[{"indicator":"rsi","params":{"period":14},"op":">","value":55}]}}. '
        "Then stop. Do not write tables — only call the tools."
    )

    url = f"{WS_BASE}/api/sessions/{target_sid}/stream"
    frame_counts = {"text": 0, "tool_use": 0, "tool_result": 0, "user": 0, "message": 0, "done": 0, "error": 0}
    text_total = 0
    tool_calls = []

    print(f"connecting to {url}")
    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(json.dumps({
            "text": prompt,
            "permission_mode": "accept-edits",
            "dataset_id": target_did,
        }))

        t_start = time.perf_counter()
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=120.0)
                f = json.loads(raw)
                ftype = f.get("type", "?")
                frame_counts[ftype] = frame_counts.get(ftype, 0) + 1
                if ftype == "text":
                    text_total += len(f.get("delta", ""))
                elif ftype == "tool_use":
                    tool_calls.append({
                        "name": f.get("name"),
                        "input_keys": list((f.get("input") or {}).keys()),
                        "input_preview": json.dumps(f.get("input"))[:200],
                    })
                    print(f"  [{time.perf_counter()-t_start:5.1f}s] TOOL_USE -> {f.get('name')} keys={list((f.get('input') or {}).keys())}")
                elif ftype == "tool_result":
                    print(f"  [{time.perf_counter()-t_start:5.1f}s] tool_result ok={f.get('ok')} err={f.get('error', '')[:80]}")
                elif ftype == "error":
                    print(f"  [{time.perf_counter()-t_start:5.1f}s] ERROR: {f.get('message')}")
                elif ftype == "done":
                    print(f"  [{time.perf_counter()-t_start:5.1f}s] DONE")
                    break
        except asyncio.TimeoutError:
            print("  TIMEOUT after 120s")

    print()
    print("=" * 70)
    print(f"FRAME COUNTS: {frame_counts}")
    print(f"TEXT bytes streamed: {text_total}")
    print(f"TOOL CALLS issued by model: {len(tool_calls)}")
    for tc in tool_calls:
        print(f"  - {tc['name']}: {tc['input_preview']}")
    print()
    if not tool_calls:
        print("VERDICT: GPT-5.4 produced ZERO tool_use frames — provider/wire bug.")
    else:
        print("VERDICT: GPT-5.4 IS calling tools. UI rendering may be the issue.")


asyncio.run(main())
