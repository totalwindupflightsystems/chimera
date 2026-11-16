"""Probe 4 — attribute the surface difference instead of trusting wall-clock.

Same prompt, same config, same formation name. Prints per-stage model + latency +
tokens from BOTH the in-process trace and the CLI's --json trace, so any gap in
wall time can be charged to a model, not guessed.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout

from chimera import Engine, LiteLLMGateway, load_config

CLI = "/home/kara/chimera-v2/.venv/bin/chimera"
PROMPT = "Reply with exactly: PONG"


def dump_stages(label: str, stages: object, real) -> None:
    for st in stages or []:
        get = st.get if isinstance(st, dict) else (lambda k, d=None: getattr(st, k, d))
        print(
            f"{label} stage={get('stage_id', get('id'))} kind={get('kind')} model={get('model')} "
            f"latency_ms={get('latency_ms')} tokens={get('tokens')} degraded={get('degraded')}",
            file=real,
        )


async def lib_arm() -> None:
    config = load_config()
    engine = Engine(config, LiteLLMGateway(config))
    out = io.StringIO()
    t = time.monotonic()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        result = await engine.deliberate(PROMPT, "simple")
    real = sys.__stdout__
    trace = result.trace
    print(
        f"ARM=lib_simple wall_s={time.monotonic() - t:.3f} "
        f"formation={getattr(trace, 'formation', None)} source={getattr(trace, 'source', None)} "
        f"cost={getattr(trace, 'total_cost', None)} tokens={getattr(trace, 'total_tokens', None)}",
        file=real,
    )
    dump_stages("ARM=lib_simple", getattr(trace, "stages", []), real)


def cli_arm() -> None:
    env = dict(os.environ)
    env.setdefault("CHIMERA_CONFIG", "/home/kara/chimera-v2/chimera.yaml")
    t = time.monotonic()
    proc = subprocess.run([CLI, "--json", PROMPT], capture_output=True, text=True, env=env, timeout=300)
    wall = time.monotonic() - t
    real = sys.__stdout__
    print(
        f"ARM=cli_json rc={proc.returncode} wall_s={wall:.3f} stdout_chars={len(proc.stdout)} "
        f"stderr_chars={len(proc.stderr)}",
        file=real,
    )
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:
        print(f"ARM=cli_json parse_failed={type(exc).__name__} head={proc.stdout[:160]!r}", file=real)
        return
    trace = payload.get("trace") or {}
    print(
        f"ARM=cli_json formation={trace.get('formation')} source={trace.get('source')} "
        f"cost={trace.get('total_cost')} tokens={trace.get('total_tokens')} "
        f"answer={str(payload.get('answer'))[:40]!r}",
        file=real,
    )
    dump_stages("ARM=cli_json", trace.get("stages", []), real)


if __name__ == "__main__":
    asyncio.run(lib_arm())
    cli_arm()
