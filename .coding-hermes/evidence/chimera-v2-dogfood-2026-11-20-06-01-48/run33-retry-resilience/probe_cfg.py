#!/usr/bin/env python3
"""Same probe, but reads the config path from argv[2] so retry variants can be driven."""
import asyncio
import os
import sys
import time

cfg_path = sys.argv[2]
os.environ["CHIMERA_CONFIG"] = cfg_path
os.environ["CHIMERA_LOCAL_FIXTURE_KEY"] = "local-fixture-only"

from chimera.config import load_config  # noqa: E402
from chimera.gateway import LiteLLMGateway  # noqa: E402

cfg = load_config(cfg_path)
gw = LiteLLMGateway(cfg)


async def main():
    t0 = time.monotonic()
    try:
        r = await gw.complete(model="mock/m1", messages=[{"role": "user", "content": "ping"}])
        print({"ok": True, "dt": round(time.monotonic() - t0, 3), "text": r.text})
    except Exception as e:  # noqa: BLE001
        print({"ok": False, "dt": round(time.monotonic() - t0, 3), "err": f"{type(e).__name__}: {str(e)[:160]}"})


asyncio.run(main())
