"""Probe 2 — the things a LIBRARY consumer actually depends on:
  (a) does `import chimera` + a call keep the consumer's stdout clean?
  (b) what does the returned result actually carry (cost? request_id? usage?)
  (c) can a Python caller pick a cheaper formation (is the cost knob reachable)?

Captures the engine's stdout/stderr in-process so the answer is measured, not eyeballed.
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from contextlib import redirect_stderr, redirect_stdout

from chimera import Engine, LiteLLMGateway, load_config


def fields(obj: object) -> str:
    names = [n for n in dir(obj) if not n.startswith("_")]
    return ",".join(names)


async def run_case(label: str, formation: str | None) -> None:
    config = load_config()
    engine = Engine(config, LiteLLMGateway(config))
    out, err = io.StringIO(), io.StringIO()
    t = time.monotonic()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            if formation is None:
                result = await engine.deliberate("Reply with exactly: PONG")
            else:
                result = await engine.deliberate("Reply with exactly: PONG", formation)
        wall = time.monotonic() - t
        ans = getattr(result, "answer", "")
        real_out = sys.__stdout__
        print(f"CASE={label} ok=True wall_s={wall:.3f} answer={ans[:40]!r}", file=real_out)
        print(
            f"CASE={label} stdout_chars={len(out.getvalue())} stderr_chars={len(err.getvalue())}",
            file=real_out,
        )
        first = (out.getvalue().splitlines() or [""])[0][:160]
        print(f"CASE={label} stdout_first_line={first!r}", file=real_out)
        print(f"CASE={label} result_fields={fields(result)}", file=real_out)
        for attr in ("answer", "trace", "total_cost", "request_id", "degraded", "cost"):
            present = hasattr(result, attr)
            val = getattr(result, attr, "<absent>")
            shown = val if isinstance(val, (int, float, str, type(None))) else type(val).__name__
            print(f"CASE={label} has_{attr}={present} value={str(shown)[:80]}", file=real_out)
        trace = getattr(result, "trace", None)
        if trace is not None:
            print(f"CASE={label} trace_fields={fields(trace)}", file=real_out)
            for attr in ("total_cost", "cost_provenance", "total_tokens", "stages", "worker_failures"):
                if hasattr(trace, attr):
                    val = getattr(trace, attr)
                    shown = val if isinstance(val, (int, float, str, type(None))) else type(val).__name__
                    print(f"CASE={label} trace.{attr}={str(shown)[:80]}", file=real_out)
    except Exception as exc:
        real_out = sys.__stdout__
        print(
            f"CASE={label} ok=False wall_s={time.monotonic() - t:.3f} exc={type(exc).__name__} msg={str(exc)[:300]!r}",
            file=real_out,
        )
        print(f"CASE={label} stdout_chars={len(out.getvalue())} stderr_chars={len(err.getvalue())}", file=real_out)


async def main() -> int:
    # (a)+(b) documented README shape (no formation argument)
    await run_case("readme_default", None)
    # (c) documented EDGE_CASES shape with a shipped cheap preset
    await run_case("simple_preset", "simple")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
