"""Probe 5 — the decisive arm.

The loaded config (chimera.yaml) says:
    observability.log_level: warning
    observability.use_stdout: false      # documented: false = stderr

So a consumer's stdout should be silent and warnings-only. Measure what the
IN-PROCESS call actually does, and count lines per level, so the claim is
arithmetic rather than an impression.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout

from chimera import Engine, LiteLLMGateway, load_config


async def main() -> int:
    real = sys.__stdout__
    config = load_config()
    obs = getattr(config, "observability", None)
    if hasattr(obs, "model_dump"):
        obs_view = obs.model_dump()
    elif isinstance(obs, dict):
        obs_view = obs
    else:
        obs_view = str(obs)
    print(f"PROBE config_observability={json.dumps(obs_view, default=str)}", file=real)

    engine = Engine(config, LiteLLMGateway(config))
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        result = await engine.deliberate("Reply with exactly: PONG", "speed")
    stdout_text, stderr_text = out.getvalue(), err.getvalue()

    def levels(text: str) -> dict[str, int]:
        counts = {"info": 0, "warning": 0, "debug": 0, "error": 0, "other": 0}
        for line in text.splitlines():
            m = re.search(r"\[(info|warning|debug|error)\s*\]", line)
            counts[m.group(1) if m else "other"] += 1
        return counts

    print(
        f"PROBE answer={result.answer[:20]!r} "
        f"stdout_chars={len(stdout_text)} stdout_lines={len(stdout_text.splitlines())} "
        f"stderr_chars={len(stderr_text)}",
        file=real,
    )
    print(f"PROBE stdout_levels={json.dumps(levels(stdout_text))}", file=real)
    print(f"PROBE stderr_levels={json.dumps(levels(stderr_text))}", file=real)
    first = (stdout_text.splitlines() or [""])[0][:150]
    print(f"PROBE stdout_first={first!r}", file=real)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
