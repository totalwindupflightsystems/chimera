"""Real consumer of the DOCUMENTED in-process Python API (README.md:116-134).

Nothing here is a test of the test suite: it is the script a user writes after
copying the README's Python block, pointed at their own file, asking the panel a
question with a checkable answer.

Two documented call shapes are exercised because the docs disagree:
  README.md:132        engine.deliberate("Explain quantum computing.")
  docs/EDGE_CASES.md:17 engine.deliberate(p, "auto")

Usage:
    CHIMERA_CONFIG=/path/chimera.yaml python panel_review.py <file-to-review>

Prints one `step=<name> ...` line per milestone with wall-clock seconds so the
journey can be summed, plus the panel's answer.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback

from chimera import Engine, LiteLLMGateway, load_config


def step(name: str, t0: float, **fields: object) -> None:
    parts = [f"step={name}", f"wall_s={time.monotonic() - t0:.3f}"]
    for k, v in fields.items():
        parts.append(f"{k}={v}")
    print(" ".join(parts), flush=True)


def shape(result: object) -> dict[str, object]:
    out: dict[str, object] = {}
    for attr in ("answer", "trace", "total_cost", "request_id", "degraded"):
        out[attr] = hasattr(result, attr)
    answer = getattr(result, "answer", None)
    out["answer_type"] = type(answer).__name__
    out["answer_len"] = len(answer) if isinstance(answer, str) else None
    trace = getattr(result, "trace", None)
    if trace is not None:
        out["trace_type"] = type(trace).__name__
        wf = getattr(trace, "worker_failures", None)
        out["trace_worker_failures"] = wf if isinstance(wf, (int, list, type(None))) else str(wf)
    out["total_cost"] = getattr(result, "total_cost", None)
    return out


async def main() -> int:
    t = time.monotonic()
    if len(sys.argv) < 2:
        print("usage: panel_review.py <file-to-review>", file=sys.stderr)
        return 2
    target = sys.argv[1]
    with open(target, "r", encoding="utf-8") as fh:
        code = fh.read()
    step("read_target", t, path=target, chars=len(code))

    t = time.monotonic()
    try:
        config = load_config()
    except Exception as exc:  # documented failure arm: no config found
        step("load_config", t, ok=False, exc=type(exc).__name__, msg=str(exc)[:300])
        return 1
    step("load_config", t, ok=True, formation=getattr(config, "default_formation", "?"))

    t = time.monotonic()
    try:
        engine = Engine(config, LiteLLMGateway(config))
    except Exception as exc:
        step("engine_init", t, ok=False, exc=type(exc).__name__, msg=str(exc)[:300])
        return 1
    step("engine_init", t, ok=True)

    prompt = (
        "You are reviewing a small Python module for real defects. "
        "Identify the single most serious logic bug, name the method and line, "
        "explain the observable misbehaviour, and give the fix in one sentence. "
        "Then list any lesser issues. Be concrete; do not summarize what the code does.\n\n"
        "```python\n" + code + "\n```\n"
    )

    # Shape 1 — README.md:132, one positional argument.
    t = time.monotonic()
    try:
        result = await engine.deliberate(prompt)
        step("deliberate_readme_form", t, ok=True, **shape(result))
        print("---ANSWER(readme-form)---", flush=True)
        print(getattr(result, "answer", "")[:2000], flush=True)
    except Exception as exc:
        step("deliberate_readme_form", t, ok=False, exc=type(exc).__name__, msg=str(exc)[:400])
        traceback.print_exc()

    # Shape 2 — docs/EDGE_CASES.md:17, with an explicit formation.
    t = time.monotonic()
    try:
        result2 = await engine.deliberate("Reply with exactly: PONG", "auto")
        ans = getattr(result2, "answer", "")
        step("deliberate_edgecase_form", t, ok=True, answer_repr=repr(ans[:60]), **shape(result2))
    except Exception as exc:
        step("deliberate_edgecase_form", t, ok=False, exc=type(exc).__name__, msg=str(exc)[:400])
        traceback.print_exc()

    # A user's second turn on the same engine: does state leak or hold?
    t = time.monotonic()
    try:
        result3 = await engine.deliberate("Reply with exactly: SECOND")
        ans3 = getattr(result3, "answer", "")
        step("deliberate_second_call", t, ok=True, answer_repr=repr(ans3[:60]))
    except Exception as exc:
        step("deliberate_second_call", t, ok=False, exc=type(exc).__name__, msg=str(exc)[:400])

    print("JSON_SHAPE " + json.dumps({"done": True}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
