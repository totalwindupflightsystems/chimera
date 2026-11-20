#!/usr/bin/env python3
"""Drive chimera's real gateway retry ladder against the metering stub.

modes: single | concurrent:<N> | exhaust
Every call goes through LiteLLMGateway.complete -> _complete_with_retry.
"""
import asyncio
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["CHIMERA_CONFIG"] = os.path.join(HERE, "fixture.yaml")
os.environ["CHIMERA_LOCAL_FIXTURE_KEY"] = "local-fixture-only"

from chimera.config import load_config  # noqa: E402
from chimera.gateway import LiteLLMGateway  # noqa: E402

mode = sys.argv[1] if len(sys.argv) > 1 else "single"
cfg = load_config(os.environ["CHIMERA_CONFIG"])
gw = LiteLLMGateway(cfg)


async def one(i, results):
    t0 = time.monotonic()
    try:
        r = await gw.complete(model="mock/m1", messages=[{"role": "user", "content": f"ping {i}"}])
        results.append({"i": i, "t0": round(t0, 4), "ok": True, "dt": round(time.monotonic() - t0, 3), "text": r.text})
    except Exception as e:  # noqa: BLE001
        results.append(
            {
                "i": i,
                "t0": round(t0, 4),
                "ok": False,
                "dt": round(time.monotonic() - t0, 3),
                "err": f"{type(e).__name__}: {str(e)[:220]}",
            }
        )


async def main():
    results = []
    if mode == "single" or mode == "exhaust":
        await one(0, results)
    elif mode.startswith("concurrent:"):
        n = int(mode.split(":")[1])
        await asyncio.gather(*(one(i, results) for i in range(n)))
    else:
        raise SystemExit(f"bad mode {mode}")
    for r in sorted(results, key=lambda x: x["i"]):
        print(r)


asyncio.run(main())
