"""Run-29 evidence arm — writes its own JSON artifact.

One prompt, one config, two surfaces (in-process library vs CLI). Records, per
arm: wall time, answer, cost/tokens when exposed, and the exact stream split with
per-level log line counts. The file it writes is committed as evidence so the
numbers in the dogfood report are reproducible rather than transcribed.

    CHIMERA_CONFIG=/path/chimera.yaml python run_evidence.py <out.json>
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout

from chimera import Engine, LiteLLMGateway, load_config

CLI = "/home/kara/chimera-v2/.venv/bin/chimera"
PROMPT = "Reply with exactly: PONG"


def levels(text: str) -> dict[str, int]:
    counts = {"info": 0, "warning": 0, "debug": 0, "error": 0, "other": 0}
    for line in text.splitlines():
        m = re.search(r"\[(info|warning|debug|error)\s*\]", line)
        counts[m.group(1) if m else "other"] += 1
    return counts


def obs_view(config: object) -> object:
    obs = getattr(config, "observability", None)
    if hasattr(obs, "model_dump"):
        return obs.model_dump()
    return obs if isinstance(obs, dict) else str(obs)


async def lib_arm(prompt: str, formation: str) -> dict[str, object]:
    config = load_config()
    engine = Engine(config, LiteLLMGateway(config))
    out, err = io.StringIO(), io.StringIO()
    t = time.monotonic()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            result = await engine.deliberate(prompt, formation)
        wall = time.monotonic() - t
        trace = result.trace
        stages = []
        for st in getattr(trace, "stages", []) or []:
            get = st.get if isinstance(st, dict) else (lambda k, d=None: getattr(st, k, d))
            stages.append(
                {
                    "stage_id": get("stage_id", get("id")),
                    "kind": get("kind"),
                    "model": get("model"),
                    "latency_ms": get("latency_ms"),
                }
            )
        return {
            "ok": True,
            "wall_s": round(wall, 3),
            "answer": str(result.answer)[:80],
            "formation": getattr(trace, "formation", None),
            "source": getattr(trace, "source", None),
            "cost": getattr(trace, "total_cost", None),
            "tokens": getattr(trace, "total_tokens", None),
            "total_duration_ms": getattr(trace, "total_duration_ms", None),
            "worker_failures": len(getattr(trace, "worker_failures", []) or []),
            "stages": stages,
            "stdout_chars": len(out.getvalue()),
            "stdout_lines": len(out.getvalue().splitlines()),
            "stdout_levels": levels(out.getvalue()),
            "stderr_chars": len(err.getvalue()),
            "stderr_levels": levels(err.getvalue()),
            "stdout_first_line": (out.getvalue().splitlines() or [""])[0][:200],
            "result_top_level_attrs": {
                "total_cost": hasattr(result, "total_cost"),
                "request_id": hasattr(result, "request_id"),
                "trace": hasattr(result, "trace"),
            },
        }
    except Exception as exc:
        return {"ok": False, "wall_s": round(time.monotonic() - t, 3), "exc": type(exc).__name__, "msg": str(exc)[:300]}


def cli_arm(prompt: str, flags: list[str]) -> dict[str, object]:
    env = dict(os.environ)
    env.setdefault("CHIMERA_CONFIG", "/home/kara/chimera-v2/chimera.yaml")
    t = time.monotonic()
    proc = subprocess.run([CLI] + flags + [prompt], capture_output=True, text=True, env=env, timeout=300)
    wall = time.monotonic() - t
    body: dict[str, object] = {
        "rc": proc.returncode,
        "wall_s": round(wall, 3),
        "stdout_chars": len(proc.stdout),
        "stdout_repr": proc.stdout[:120],
        "stdout_levels": levels(proc.stdout),
        "stderr_chars": len(proc.stderr),
        "stderr_levels": levels(proc.stderr),
    }
    if "--json" in flags:
        try:
            payload = json.loads(proc.stdout)
            tr = payload.get("trace") or {}
            body["formation"] = tr.get("formation")
            body["source"] = tr.get("source")
            body["cost"] = tr.get("total_cost")
            body["tokens"] = tr.get("total_tokens")
            body["answer"] = str(payload.get("answer"))[:80]
        except Exception as exc:
            body["parse_error"] = type(exc).__name__
    return body


async def main() -> int:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "run29-evidence.json"
    config = load_config()
    record: dict[str, object] = {
        "tick": "chimera-v2-dogfood-2026-11-16-05-02-33",
        "run": 29,
        "surface": "in-process Python library (README.md:116-134)",
        "prompt": PROMPT,
        "chimeraconfig_observability": obs_view(config),
        "arms": {},
    }
    record["arms"]["lib_auto"] = await lib_arm(PROMPT, "auto")
    record["arms"]["lib_simple"] = await lib_arm(PROMPT, "simple")
    record["arms"]["lib_speed"] = await lib_arm(PROMPT, "speed")
    record["arms"]["cli_quiet"] = cli_arm(PROMPT, ["--quiet"])
    record["arms"]["cli_json"] = cli_arm(PROMPT, ["--json"])
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
    real = sys.__stdout__
    for name, arm in record["arms"].items():
        if isinstance(arm, dict):
            print(
                f"ARM={name} ok={arm.get('ok', arm.get('rc'))} wall_s={arm.get('wall_s')} "
                f"cost={arm.get('cost')} tokens={arm.get('tokens')} "
                f"stdout_chars={arm.get('stdout_chars')} stderr_chars={arm.get('stderr_chars')} "
                f"stdout_levels={json.dumps(arm.get('stdout_levels'))}",
                file=real,
            )
    print(f"WROTE {out_path}", file=real)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
