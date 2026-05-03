"""Diagnostic WS probe — sends a tiny prompt to the user's most recent
session and dumps every frame the server emits."""
import asyncio
import json
import sys

import httpx
import websockets


async def main():
    async with httpx.AsyncClient() as c:
        ps = (await c.get("http://127.0.0.1:8765/api/projects")).json()
        # Latest project
        if not ps:
            print("no projects"); return
        latest = sorted(ps, key=lambda p: p["created_at"], reverse=True)[0]
        pid = latest["id"]
        ds = (await c.get(f"http://127.0.0.1:8765/api/projects/{pid}/datasets")).json()
        ss = (await c.get(f"http://127.0.0.1:8765/api/projects/{pid}/sessions")).json()
        if not ds or not ss:
            print(f"project {pid} missing dataset or session"); return
        sid = ss[0]["id"]
        did = ds[0]["id"]
        print(f"project={pid} session={sid} dataset={did}")
        print(f"session model={ss[0].get('model')} provider={ss[0].get('provider')}")

    url = f"ws://127.0.0.1:8765/api/sessions/{sid}/stream"
    print(f"connecting {url}")
    try:
        async with websockets.connect(url, max_size=None) as ws:
            await ws.send(json.dumps({
                "text": "Run compute_rsi(period=14) on the active dataset. Then stop, no text.",
                "permission_mode": "accept-edits",
                "dataset_id": did,
            }))
            t0 = asyncio.get_event_loop().time()
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60.0)
                except asyncio.TimeoutError:
                    print("TIMEOUT 60s"); return
                except websockets.exceptions.ConnectionClosed as exc:
                    print(f"CONN CLOSED: code={exc.code} reason={exc.reason!r}")
                    return
                f = json.loads(raw)
                t = asyncio.get_event_loop().time() - t0
                ftype = f.get("type")
                if ftype == "text":
                    print(f"  [{t:5.1f}s] text +{len(f.get('delta',''))} chars")
                elif ftype == "tool_use":
                    print(f"  [{t:5.1f}s] tool_use {f.get('name')} input_keys={list((f.get('input') or {}).keys())}")
                elif ftype == "tool_result":
                    print(f"  [{t:5.1f}s] tool_result ok={f.get('ok')} err={(f.get('error') or '')[:100]}")
                elif ftype == "error":
                    print(f"  [{t:5.1f}s] ERROR: {f.get('message')}")
                    return
                elif ftype == "done":
                    print(f"  [{t:5.1f}s] DONE"); return
                else:
                    print(f"  [{t:5.1f}s] {ftype}")
    except Exception as exc:
        print(f"OUTER EXCEPTION: {type(exc).__name__}: {exc}")


asyncio.run(main())
