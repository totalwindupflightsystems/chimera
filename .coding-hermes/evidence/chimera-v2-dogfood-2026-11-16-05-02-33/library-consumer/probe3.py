"""Probe 3 — completes the preset comparison (speed arm) and contrasts the CLI's
documented machine-output contract with the in-process API's actual stream use.

The CLI contract is explicit in README.md:105-108: under --quiet / --json the
answer goes to stdout and every warning moves to stderr, so a caller can consume
stdout safely. The library has no such statement — this measures whether it holds
the same line.
"""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout

from chimera import Engine, LiteLLMGateway, load_config

CLI = "/home/kara/chimera-v2/.venv/bin/chimera"
PROMPT = "Reply with exactly: PONG"


async def speed_arm() -> None:
    config = load_config()
    engine = Engine(config, LiteLLMGateway(config))
    out, err = io.StringIO(), io.StringIO()
    t = time.monotonic()
    with redirect_stdout(out), redirect_stderr(err):
        result = await engine.deliberate(PROMPT, "speed")
    wall = time.monotonic() - t
    real = sys.__stdout__
    trace = result.trace
    print(
        f"CASE=speed_preset ok=True wall_s={wall:.3f} answer={result.answer[:30]!r} "
        f"cost={getattr(trace, 'total_cost', None)} tokens={getattr(trace, 'total_tokens', None)} "
        f"stdout_chars={len(out.getvalue())} stderr_chars={len(err.getvalue())}",
        file=real,
    )


def cli_arm() -> None:
    env = dict(os.environ)
    env.setdefault("CHIMERA_CONFIG", "/home/kara/chimera-v2/chimera.yaml")
    t = time.monotonic()
    proc = subprocess.run(
        [CLI, "--quiet", PROMPT],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    wall = time.monotonic() - t
    print(
        f"CASE=cli_quiet rc={proc.returncode} wall_s={wall:.3f} "
        f"stdout_chars={len(proc.stdout)} stderr_chars={len(proc.stderr)} "
        f"stdout_repr={proc.stdout[:80]!r}",
        file=sys.__stdout__,
    )
    logish = [
        ln
        for ln in proc.stdout.splitlines()
        if "[" in ln and ("info" in ln or "warning" in ln or "debug" in ln)
    ]
    print(f"CASE=cli_quiet stdout_logish_lines={len(logish)}", file=sys.__stdout__)


if __name__ == "__main__":
    asyncio.run(speed_arm())
    cli_arm()
