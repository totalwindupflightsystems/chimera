"""Freshness check for the load-bearing ``litellm>=1.50.0,<1.100`` pin.

Why this exists (pyproject.toml:30-43, CH-MAINT-007): litellm 1.100.0 replaced
its stderr ``logging.StreamHandler()`` with ``LevelRoutingStreamHandler``,
which routes every record BELOW WARNING to ``sys.stdout`` — fatal for the MCP
stdio transport, whose stdout IS the JSON-RPC wire. On top of that, every
release in the pinned range (verified on 1.99.4) keeps always-on
bare-``print()`` paths gated by the process-global
``litellm.suppress_debug_info`` (False by default): the ANSI ``Provider List``
banner (``litellm_core_utils.get_llm_provider_logic``) and the
``Give Feedback / Get Help`` block (``exception_mapping_utils``).
``chimera.gateway.ensure_litellm_quiet()`` sets that flag before every
completion, so the banners are handled at runtime — the PIN itself only guards
the logging-handler regression. Nothing, until now, checks whether upstream
has since fixed/removed the problem so the cap can be lifted.

What it probes (all OFFLINE, no API calls):

1. ``banner``      — ``litellm.get_llm_provider(model=<unknown>)`` historically
  raised ``BadRequestError`` after printing the ANSI Provider List banner to
  stdout. The probe captures stdout around the call and reports whether the
  banner fired with ``suppress_debug_info`` at its default (False).
2. ``banner_suppressed`` — reruns probe 1 with ``suppress_debug_info = True``:
  the banner must disappear. If it does NOT, ``ensure_litellm_quiet()`` can no
  longer save us — a defect on ANY version.
3. ``feedback``    — ``litellm.utils.exception_type(...)`` with a fake
  connection error historically printed the Give Feedback block to stdout.
4. ``log_routing`` — at fd level (dup2 stdout/stderr to temp files), emits an
  INFO and a DEBUG record on the ``LiteLLM`` logger and reports where they
  landed, plus the handler class names. ``LevelRoutingStreamHandler`` or
  INFO-on-stdout = the regression the <1.100 cap exists for.

Verdicts (key ``verdict`` in the stdout JSON):

- ``SAFE_TO_TEST`` — a litellm >= the cap (1.100.0) was probed and showed NO
  stdout defect on any probe that could answer. Automated evidence says the
  cap can be lifted; confirm with ``scripts/probe_mcp_stdio.py`` (both
  formations) plus a real deliberation before landing the lift.
- ``STAY_PINNED`` — a litellm >= the cap was probed and showed at least one
  stdout defect: the cap is still load-bearing.
- ``INCONCLUSIVE`` — no cap-boundary evidence was produced. Typical causes:
  the probe target is INSIDE the pinned range (the default installed-pin run —
  rerun with ``--scratch`` for boundary evidence), litellm is not importable
  in the target, the version string is unparseable, every probe errored, or
  ``--scratch`` could not build/install (offline, pip failure).

Usage::

    # Default: probe the litellm installed for THIS checkout (repo venv when
    # present, else the running interpreter). Never installs anything.
    .venv/bin/python scripts/litellm_pin_check.py

    # Probe any other interpreter's environment:
    .venv/bin/python scripts/litellm_pin_check.py --target /some/venv/bin/python

    # Cap-boundary evidence: create a TEMPORARY scratch venv, pip-install
    # litellm>=1.100.0 into it, probe THAT, then delete it. Needs network;
    # degrades to INCONCLUSIVE when pip fails. NEVER touches the repo venv.
    .venv/bin/python scripts/litellm_pin_check.py --scratch

Output contract: stdout carries EXACTLY ONE machine-readable JSON line
(``"schema": "litellm-pin-check/1"``, sorted keys); all human-readable
progress goes to stderr. Exit code is 0 for every completed check regardless
of verdict — the verdict, not the exit code, carries the finding. Exit 2 only
on harness error (this script itself crashed).

No cron is registered by this script (mirrors ``model_sync_cron.py``'s
ad-hoc-by-design note); run it manually or wire it into the fleet scheduler
if automated freshness checks are ever wanted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The requirement whose upper bound this check watches (pyproject.toml:43).
PIN_SPEC = "litellm>=1.50.0,<1.100"

#: First release with the ``LevelRoutingStreamHandler`` stdout regression —
#: the boundary the pin's upper bound encodes. A probe target at/above this
#: version is the only thing that can produce SAFE_TO_TEST/STAY_PINNED.
VERSION_CAP = "1.100.0"

#: pip requirement installed into the scratch venv for ``--scratch`` runs.
SCRATCH_REQUIREMENT = "litellm>=1.100.0"

#: Parent-report schema key, so the parser can pin the wire shape.
REPORT_SCHEMA = "litellm-pin-check/1"

#: Child-report schema key (the JSON the probe subprocess prints on stdout).
CHILD_SCHEMA = "litellm-pin-child-report/1"

#: Seconds allowed for one child probe run (a cold litellm import is slow).
CHILD_TIMEOUT_S = 180

#: Seconds allowed for the scratch venv's ``pip install litellm>=1.100.0``
#: (litellm pulls a large dependency tree; offline hosts fail fast instead).
PIP_TIMEOUT_S = 900

#: Where the scratch venv is created (a fresh tempfile dir per run, removed
#: afterwards).
SCRATCH_DIR_PREFIX = "chimera-litellm-pin-scratch-"

_VER_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:.*)?$")

# --- child probe -------------------------------------------------------------

#: The probe program run INSIDE the target interpreter via ``python -c``.
#: Stdlib only; prints one JSON line (CHILD_SCHEMA) to stdout; every step is
#: individually fault-isolated so a litellm whose internals moved still yields
#: a parsable partial report.
CHILD_PROBE_SOURCE = r'''
"""Probe a litellm install for stdout debug output (CH-MAINT-007 child)."""
import importlib.metadata as md
import io
import json
import logging
import os
import pathlib
import re
import sys
import tempfile
from contextlib import redirect_stdout

REPORT = {
    "schema": "litellm-pin-child-report/1",
    "python": sys.version.split()[0],
    "litellm_version": None,
    "litellm_path": None,
    "suppress_flag_default": None,
    "banner": {"fired": None, "error": None},
    "banner_suppressed": {"ok": None, "error": None},
    "feedback": {"fired": None, "error": None},
    "log_routing": {"handler": None, "info_to_stdout": None,
                    "stderr_has_info": None, "error": None},
    "import_error": None,
}

BANNER_RE = re.compile(r"Provider List: https://docs\.litellm\.ai/docs/providers")
FEEDBACK_RE = re.compile(r"Give Feedback / Get Help")
PROBE_MODEL = "chimera-pin-check-unknown-model"


def emit() -> None:
    sys.stdout.write(json.dumps(REPORT, sort_keys=True) + "\n")
    sys.stdout.flush()


try:
    import litellm
except Exception as exc:  # noqa: BLE001 - any import failure is a finding
    REPORT["import_error"] = f"{type(exc).__name__}: {exc}"
    emit()
    raise SystemExit(0)


def resolve_provider_lookup():
    fn = getattr(litellm, "get_llm_provider", None)
    if fn is not None:
        return fn
    from litellm_core_utils.get_llm_provider_logic import (
        get_llm_provider as fn2,
    )
    return fn2


def resolve_exception_type():
    fn = getattr(litellm.utils, "exception_type", None)
    if fn is not None:
        return fn
    from litellm_core_utils import exception_mapping_utils
    return exception_mapping_utils.exception_type


def probe_banner(suppress: bool) -> dict:
    """Capture stdout around a provider-less lookup; report banner presence."""
    out = {"fired": None, "error": None}
    litellm.suppress_debug_info = suppress
    try:
        fn = resolve_provider_lookup()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"resolve: {type(exc).__name__}: {exc}"
        return out
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            fn(model=PROBE_MODEL)
    except TypeError as exc:
        out["error"] = f"signature: {exc}"
        return out
    except Exception:  # noqa: BLE001 - expected: BadRequestError after print
        pass
    out["fired"] = BANNER_RE.search(buf.getvalue()) is not None
    return out


def probe_feedback() -> dict:
    """Capture stdout around a mapped provider error; report print presence."""
    out = {"fired": None, "error": None}
    litellm.suppress_debug_info = False
    try:
        fn = resolve_exception_type()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"resolve: {type(exc).__name__}: {exc}"
        return out
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            fn(
                model=PROBE_MODEL,
                original_exception=ConnectionError("chimera pin probe"),
                custom_llm_provider="openai",
                completion_kwargs={},
            )
    except TypeError as exc:
        out["error"] = f"signature: {exc}"
        return out
    except Exception:  # noqa: BLE001 - expected: mapped error after print
        pass
    out["fired"] = FEEDBACK_RE.search(buf.getvalue()) is not None
    return out


def probe_log_routing(workdir: str) -> dict:
    """Route fd 1/2 to files, emit sub-WARNING records, report where they land."""
    out = {"handler": None, "info_to_stdout": None, "stderr_has_info": None,
           "error": None}
    try:
        logger = logging.getLogger("LiteLLM")
        out["handler"] = ";".join(type(h).__name__ for h in logger.handlers) or None
        out_path = pathlib.Path(workdir) / "probe-stdout.txt"
        err_path = pathlib.Path(workdir) / "probe-stderr.txt"
        out_f = open(out_path, "wb")
        err_f = open(err_path, "wb")
        saved_out, saved_err = os.dup(1), os.dup(2)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(out_f.fileno(), 1)
            os.dup2(err_f.fileno(), 2)
            logger.info("chimera-pin-probe-info")
            logger.debug("chimera-pin-probe-debug")
            for handler in logger.handlers:
                handler.flush()
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            os.dup2(saved_out, 1)
            os.dup2(saved_err, 2)
            os.close(saved_out)
            os.close(saved_err)
            out_f.close()
            err_f.close()
        out_text = out_path.read_text(errors="replace")
        err_text = err_path.read_text(errors="replace")
        out["info_to_stdout"] = "chimera-pin-probe-info" in out_text
        out["stderr_has_info"] = "chimera-pin-probe-info" in err_text
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def main() -> None:
    try:
        REPORT["litellm_version"] = md.version("litellm")
    except Exception:  # noqa: BLE001
        REPORT["litellm_version"] = None
    REPORT["litellm_path"] = str(pathlib.Path(litellm.__file__).parent)
    REPORT["suppress_flag_default"] = bool(
        getattr(litellm, "suppress_debug_info", False)
    )
    REPORT["banner"] = probe_banner(suppress=False)
    REPORT["feedback"] = probe_feedback()
    if REPORT["banner"]["fired"] is not None:
        REPORT["banner_suppressed"] = probe_banner(suppress=True)
        REPORT["banner_suppressed"]["ok"] = (
            REPORT["banner_suppressed"]["fired"] is False
        )
    with tempfile.TemporaryDirectory(prefix="litellm-pin-routing-") as workdir:
        REPORT["log_routing"] = probe_log_routing(workdir)
    emit()


main()
'''


# --- version handling --------------------------------------------------------


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    """Parse ``X[.Y[.Z]]`` into a comparable 3-tuple; None when unparseable.

    Non-numeric tails (``1.100.0rc1``) are dropped after the third numeric
    group — deliberate, so a pre-release sitting ON the cap boundary compares
    as the boundary itself.
    """
    if not text:
        return None
    match = _VER_RE.match(text.strip())
    if match is None:
        return None
    return tuple(int(group) if group else 0 for group in match.groups())


def format_version(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


# --- child invocation --------------------------------------------------------


def _extract_child_json(stdout: str) -> dict | None:
    """Return the child's schema-bearing JSON line, tolerating prefix noise.

    Scanned from the END: anything litellm itself printed to real stdout
    before the report must not win.
    """
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and candidate.get("schema") == CHILD_SCHEMA:
            return candidate
    return None


def _child_env() -> dict[str, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # The child must not inherit pytest's filterwarnings/-p machinery.
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


def _child_report(python_path: str) -> dict:
    """Run the embedded probe under ``python_path``; return its JSON report.

    Raises subprocess./OSError when the interpreter itself cannot be started —
    callers convert that into the appropriate verdict/harness outcome.
    """
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [python_path, "-c", CHILD_PROBE_SOURCE],
        capture_output=True,
        text=True,
        timeout=CHILD_TIMEOUT_S,
        env=_child_env(),
        check=False,
    )
    child = _extract_child_json(proc.stdout)
    if child is None:
        child = {
            "schema": CHILD_SCHEMA,
            "litellm_version": None,
            "import_error": None,
            "spawn": {"returncode": proc.returncode, "stderr_tail": proc.stderr[-400:]},
        }
    return child


# --- verdict derivation ------------------------------------------------------


def _answered(child: dict) -> bool:
    banner = (child.get("banner") or {}).get("fired")
    feedback = (child.get("feedback") or {}).get("fired")
    routing = (child.get("log_routing") or {}).get("info_to_stdout")
    return banner is not None or feedback is not None or routing is not None


def _defects(child: dict) -> list[str]:
    """Human-readable list of observed stdout defects (empty = none seen)."""
    defects: list[str] = []
    banner = (child.get("banner") or {}).get("fired")
    feedback = (child.get("feedback") or {}).get("fired")
    suppressed_ok = (child.get("banner_suppressed") or {}).get("ok")
    routing = child.get("log_routing") or {}
    info_to_stdout = routing.get("info_to_stdout")
    handler = routing.get("handler") or ""

    if banner:
        defects.append("ANSI 'Provider List' banner prints to stdout with suppress_debug_info at its default")
    if feedback:
        defects.append("'Give Feedback / Get Help' block prints to stdout on a mapped provider error")
    if suppressed_ok is False:
        # Flagged on its own, even when the default-banner arm disagreed: the
        # real child only runs the suppressed arm after a fired banner, so this
        # combination means ensure_litellm_quiet() can no longer silence the
        # banner path — a defect on ANY version.
        defects.append(
            "suppress_debug_info=True does NOT silence the banner "
            "(chimera.gateway.ensure_litellm_quiet() would be ineffective)"
        )
    if info_to_stdout or "LevelRoutingStreamHandler" in handler:
        defects.append(
            "sub-WARNING log records are routed to stdout "
            "(the LevelRoutingStreamHandler regression the <1.100 cap guards)"
        )
    return defects


def derive_verdict(child: dict, version_cap: tuple[int, int, int]) -> tuple[str, str]:
    """Map a child report to (verdict, reason). Pure — no I/O, no clock.

    SAFE_TO_TEST / STAY_PINNED require cap-boundary evidence (a probe target
    at/above ``version_cap``); everything else is INCONCLUSIVE with a reason
    saying exactly what is missing.
    """
    import_error = child.get("import_error")
    if child.get("litellm_version") is None:
        detail = import_error or (child.get("spawn") or {}).get("stderr_tail") or "no report"
        return (
            "INCONCLUSIVE",
            f"litellm is not importable/usable in the target environment: {detail}",
        )

    installed = parse_version(child.get("litellm_version"))
    if installed is None:
        return (
            "INCONCLUSIVE",
            f"unparseable litellm version {child.get('litellm_version')!r}",
        )
    if installed < version_cap:
        return (
            "INCONCLUSIVE",
            f"target litellm {child['litellm_version']} is INSIDE the pinned "
            f"range ({PIN_SPEC}); the cap can only be cleared with evidence "
            f"from a >={format_version(version_cap)} install — rerun with --scratch",
        )

    defects = _defects(child)
    if defects:
        return "STAY_PINNED", "; ".join(defects)
    if not _answered(child):
        return (
            "INCONCLUSIVE",
            f"litellm {child['litellm_version']} (>= cap) was probed but every "
            "probe errored — no positive evidence either way",
        )
    return (
        "SAFE_TO_TEST",
        f"litellm {child['litellm_version']} (>= cap) shows no stdout debug "
        "output on any probe; confirm with scripts/probe_mcp_stdio.py before "
        "lifting the pin",
    )


# --- check modes -------------------------------------------------------------


def _default_target_python() -> str:
    """The interpreter that has this checkout's litellm: repo venv first.

    Mirrors ``model_sync_cron._sync_python()``: a scheduler/cron interpreter
    often lacks the project deps, so defaulting to ``sys.executable`` alone
    would probe the wrong environment.
    """
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _scratch_venv_python(parent_dir: Path) -> str:
    """Create a throwaway venv (with pip) under ``parent_dir``; return python."""
    path = parent_dir / "venv"
    builder = venv.EnvBuilder(with_pip=True)
    builder.create(str(path))
    python_path = path / "bin" / "python"
    if not python_path.exists():
        raise RuntimeError(f"scratch venv has no interpreter at {python_path}")
    return str(python_path)


def _pip_install(python_path: str, requirement: str) -> tuple[bool, str]:
    """``pip install`` a requirement; (ok, tail-of-stderr) so callers can say WHY."""
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [python_path, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", requirement],
        capture_output=True,
        text=True,
        timeout=PIP_TIMEOUT_S,
        check=False,
    )
    return proc.returncode == 0, proc.stderr.strip()[-600:]


def run_check(target: str | None, scratch: bool) -> dict:
    """Execute the check and return the full parent report (no printing)."""
    report: dict = {
        "schema": REPORT_SCHEMA,
        "verdict": "INCONCLUSIVE",
        "reason": "",
        "probe_mode": "scratch" if scratch else ("target" if target else "installed"),
        "version_cap": VERSION_CAP,
        "pin_spec": PIN_SPEC,
        "target_python": "",
        "litellm_version": None,
        "detail": None,
        "harness_error": None,
    }

    if scratch:
        scratch_dir = Path(tempfile.mkdtemp(prefix=SCRATCH_DIR_PREFIX))
        try:
            python_path = _scratch_venv_python(scratch_dir)
            report["target_python"] = python_path
            print(
                f"scratch venv ready at {python_path}; "
                f"pip-installing {SCRATCH_REQUIREMENT} (needs network)...",
                file=sys.stderr,
            )
            ok, tail = _pip_install(python_path, SCRATCH_REQUIREMENT)
            if not ok:
                report["reason"] = f"scratch pip install of {SCRATCH_REQUIREMENT} failed (offline?): {tail}"
                return report
            child = _child_report(python_path)
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)
    else:
        python_path = target or _default_target_python()
        report["target_python"] = python_path
        try:
            child = _child_report(python_path)
        except (OSError, subprocess.SubprocessError) as exc:
            report["reason"] = f"could not run probe under {python_path}: {type(exc).__name__}: {exc}"
            return report

    report["detail"] = child
    report["litellm_version"] = child.get("litellm_version")
    verdict, reason = derive_verdict(child, parse_version(VERSION_CAP))
    report["verdict"] = verdict
    report["reason"] = reason
    return report


# --- human summary (stderr) --------------------------------------------------


def _human_summary(report: dict) -> str:
    lines = [
        f"target: {report['target_python']} (mode: {report['probe_mode']})",
        f"litellm: {report.get('litellm_version') or 'not importable'} | "
        f"pin {report['pin_spec']} (cap {report['version_cap']})",
        f"VERDICT: {report['verdict']} — {report['reason']}",
    ]
    child = report.get("detail") or {}
    if child:
        banner = (child.get("banner") or {}).get("fired")
        suppressed = (child.get("banner_suppressed") or {}).get("ok")
        routing = child.get("log_routing") or {}
        if banner is not None:
            lines.append(f"banner print fired (default flag): {banner}")
        if suppressed is not None:
            lines.append(f"banner silenced by suppress_debug_info=True: {suppressed}")
        if routing.get("handler"):
            lines.append(
                f"log routing: handler={routing['handler']} info->stdout={routing.get('info_to_stdout')}"
            )
    lines.append("machine-readable report: the single JSON line on stdout")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Freshness check for the load-bearing litellm<1.100 pin "
            "(CH-MAINT-007). Prints one JSON report line on stdout; progress "
            "on stderr. Exit 0 for every completed check (read the verdict "
            "field); exit 2 only when the harness itself fails."
        )
    )
    parser.add_argument(
        "--target",
        metavar="PYTHON",
        help="probe this interpreter's environment instead of the repo venv",
    )
    parser.add_argument(
        "--scratch",
        action="store_true",
        help=(
            "create a temporary venv, pip-install litellm>=1.100.0 there and "
            "probe it (needs network; the repo venv is never touched)"
        ),
    )
    args = parser.parse_args(argv)

    try:
        report = run_check(args.target, args.scratch)
    except Exception as exc:  # noqa: BLE001 - harness errors must exit 2, loudly
        print(f"HARNESS ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, sort_keys=True))
    print(_human_summary(report), file=sys.stderr)
    if report["harness_error"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
