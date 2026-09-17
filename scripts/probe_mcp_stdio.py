#!/usr/bin/env python3
"""Raw stdio MCP stdout-purity probe / gate (DF-CHIMERA-0906-2, DF-CHIMERA-0911-1,
DF-CHIMERA-0917-5, DF-CHIMERA-V2-9).

Spawns the real chimera MCP entry point over stdio and drives
initialize -> notifications/initialized -> tools/list -> tools/call
chimera_deliberate. FAILS (exit 1) if ANY stdout line is not a valid JSON-RPC
2.0 message — provider-discovery / structlog / SDK lines must never reach
stdout ahead of the initialize response.

Depth call: a REAL ``chimera_deliberate`` tools/call (small deterministic
arithmetic prompt). A handshake/catalog probe (``chimera_models``) never
triggers the lazy LiteLLM import, so the published 0.2.3 wheel passed a
models-only probe while still polluting stdout on a real deliberation call.
This probe must NEVER regress to a shallow call — tests/test_probe_mcp_stdio.py
pins the request contract.

Formation is selectable (DF-CHIMERA-0911-1): the leak is formation-dependent
(``simple`` was clean while ``speed``'s OpenRouter leg made LiteLLM print an
ANSI "Provider List" banner to stdout), so a release gate must be able to
drive a non-default formation without editing the script:

    python3 scripts/probe_mcp_stdio.py .venv/bin/chimera-mcp
    python3 scripts/probe_mcp_stdio.py --formation=speed .venv/bin/chimera-mcp
    CHIMERA_PROBE_FORMATION=speed python3 scripts/probe_mcp_stdio.py .venv/bin/chimera-mcp

Version reporting (DF-CHIMERA-V2-9): the probe always prints the initialize
handshake's ``SERVER_VERSION=<serverInfo.version>``, and ``--expected-version=X``
turns that into a gate — a build whose handshake advertises anything else (the
pre-0.2.6 bug advertised the mcp SDK's own version, 1.28.1, because ``FastMCP``
takes no version kwarg) prints ``SERVER_VERSION_MISMATCH=expected:X actual:Y``
and exits 1.

The probe PROVISIONS ITS OWN CONFIG by default (DF-CHIMERA-0917-5). The live
repo-root ``chimera.yaml`` is untracked by design (DF-CHIMERA-0916B-4), so a
fresh CI checkout has NO config: ``load_config()`` falls back to empty
defaults, ``formations == {}`` and every ``chimera_deliberate`` call answers
``unknown_formation`` in ~1s with zero provider calls — a gate that *looks*
like it ran while testing nothing. So, with neither ``--config`` nor ``--cwd``,
the probe creates a temp dir, generates a config there with the child's own
sibling CLI (``<bin-dir>/chimera config init``, which resolves the shipped
template via ``chimera.config.find_example_config_path()`` — never a
hand-written YAML template that would duplicate the config schema), spawns the
child with that dir as cwd and ``CHIMERA_CONFIG`` pointed at the generated file,
and prints ``CONFIG_SOURCE=generated`` / ``CONFIG_PATH=<path>``.

Child command resolution (QA-CHIMERA-V2-17): the child's executable token is
resolved against the INVOKING cwd BEFORE the config is provisioned and before
the child is spawned — the generated-config default runs the child in its own
temp dir (``PROBE_CWD``), so a relative token used to be resolved against that
temp dir and died as a raw ``FileNotFoundError`` traceback inside
``subprocess.Popen`` (the module's own usage examples below spell it
relatively). The rule, applied by :func:`resolve_child_command`:

* an ABSOLUTE token is used exactly as given;
* a RELATIVE token containing a path separator is resolved against the
  invoking cwd and absolutized;
* a relative path that does not exist there is a NAMED usage error naming the
  token and the base dir (exit 2, never a traceback);
* a bare command name (no separator, e.g. ``chimera mcp``) is left untouched
  so ``PATH`` lookup still happens.

Only the executable token is ever rewritten — the rest of the child argv is
the child's own. What is spawned is what ``CHILD_CMD`` prints.

Options owned by the probe (each a SINGLE ``--opt=VALUE`` token, stripped from
the child command exactly like ``--formation``; a bare ``--opt VALUE`` pair is
a usage error, exit 2, because the next token could equally be the child's own
argv):

    --formation=NAME   formation to drive (env: CHIMERA_PROBE_FORMATION)
    --config=PATH      use this config file (exported to the child as
                       CHIMERA_CONFIG); cwd defaults to the file's directory
    --cwd=PATH         run the child in this directory and let it discover the
                       directory's own chimera.yaml (CHIMERA_CONFIG is cleared
                       for the child so the walk-up is honest)
    --expected-version=VER
                       compare the handshake's serverInfo.version with VER; on
                       a mismatch print
                       SERVER_VERSION_MISMATCH=expected:VER actual:<actual> and
                       exit 1 (SERVER_VERSION= is always printed)

Formation satisfiability (DF-CHIMERA-0917-5): the generated ``speed`` formation
uses ``openrouter/qwen/qwen3-coder``, which needs ``OPENROUTER_API_KEY``. The
release gate must not depend on repo secrets that may not exist, so before
driving a formation the probe inspects every model the formation references
(workers, aggregator, audit, DAG stage models) and remaps any whose provider
credential does not resolve to a credentialed model (default
``deepseek/deepseek-v4-flash``), PRINTING each substitution:

    FORMATION_MODEL_REMAP=openrouter/qwen/qwen3-coder -> deepseek/deepseek-v4-flash (OPENROUTER_API_KEY unset)

The remap is applied ONLY to a config the probe generated itself — an
operator-supplied ``--config``/``--cwd`` config is used exactly as given (the
probe never rewrites a file it did not create) — and it is never silent: the
substitutions are reported on stdout and counted in ``MODEL_REMAPS_TOTAL``.
When the key IS set no remap happens, so the OpenRouter leg (the 0.2.3
stdout-leak leg) keeps being exercised and the gate's coverage is not weakened.

The request/validation/provisioning contract lives in importable pure functions
(``build_messages``, ``parse_owned_options``, ``usage_error``,
``resolve_child_command``, ``plan_config_provision``,
``formation_model_references``,
``remap_uncredentialed_models``, ``provider_credential_resolved``,
``is_jsonrpc_line``, ``collect_responses``, ``extract_tool_text``,
``check_depth_result``, ``check_handshake``, ``server_info_version``,
``server_version_mismatch``) so the offline regression suite can
verify it without spawning chimera or touching the network; only
``provision_config`` and ``main``/``drive_stdio`` do subprocess I/O.

Usage:
    python3 scripts/probe_mcp_stdio.py .venv/bin/chimera-mcp
    python3 scripts/probe_mcp_stdio.py chimera mcp
    python3 scripts/probe_mcp_stdio.py --config=/srv/chimera.yaml .venv/bin/chimera-mcp
    python3 scripts/probe_mcp_stdio.py --cwd=/tmp/site-cfg .venv/bin/chimera-mcp
    python3 scripts/probe_mcp_stdio.py --expected-version=0.2.6 .venv/bin/chimera-mcp

Exit codes: 0 = stdout pure (all JSON-RPC, responses 1/2/3 in order, 3
tools, chimera_deliberate returns JSON with a non-empty answer);
1 = pollution or malformed response, or a handshake version that differs from
--expected-version; 2 = usage/setup error (bad probe option, unreadable
--config, unprovisionable config).
"""

from __future__ import annotations

import copy
import json
import os
import re
import select
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEPTH_TOOL = "chimera_deliberate"
DEPTH_PROMPT = "What is 17 * 23? Show the computation."
DEPTH_FORMATION = "simple"
DEPTH_ARGUMENTS: dict = {"prompt": DEPTH_PROMPT, "formation": DEPTH_FORMATION}
DEPTH_MARKER = "391"
DEPTH_MARKER_NOTE = "17 * 23 = 391"

#: Probe-owned formation selector. The option is a single ``--formation=NAME``
#: token; both the option and its value are removed from the child command.
PROBE_FORMATION_ENV = "CHIMERA_PROBE_FORMATION"
PROBE_FORMATION_OPTION = "--formation="
#: Probe-owned config/cwd selectors (DF-CHIMERA-0917-5), same single-token rule.
PROBE_CONFIG_OPTION = "--config="
PROBE_CWD_OPTION = "--cwd="
#: Probe-owned expected-version selector (DF-CHIMERA-V2-9): the initialize
#: handshake must advertise the PACKAGE version, so the release gate can pin it.
PROBE_EXPECTED_VERSION_OPTION = "--expected-version="
#: Every option the probe owns; the bare ``--opt VALUE`` spelling of any of
#: these is a usage error (the value could equally be the child's argv).
OWNED_BARE_OPTIONS = ("--formation", "--config", "--cwd", "--expected-version")
#: How each owned option must be spelled, for the usage message.
VALUE_OPTION_LABELS = {
    "--formation": "--formation=NAME",
    "--config": "--config=PATH",
    "--cwd": "--cwd=PATH",
    "--expected-version": "--expected-version=VER",
}
#: Evidence marker for a handshake that carries no ``serverInfo.version``.
MISSING_VERSION = "(missing)"


#: Name of the config the probe generates in its own temp directory.
GENERATED_CONFIG_NAME = "chimera.yaml"
PROBE_CONFIG_DIR_PREFIX = "chimera-probe-cfg-"

#: Remap target for models whose provider has no resolved credential — the same
#: model the shipped template already uses as its default worker/aggregator, so
#: a single-provider (DEEPSEEK_API_KEY only) environment can still drive the
#: formation for real.
DEFAULT_REMAP_MODEL = "deepseek/deepseek-v4-flash"

TOOL_INVENTORY = {"chimera_deliberate", "chimera_formations", "chimera_models"}
EXPECTED_ORDER = [1, 2, 3]

# A real deliberation spans dispatcher -> worker(s) -> aggregator LLM calls
# (network-bound), so the read deadline is minutes, not seconds.
READ_DEADLINE_S = 300
DRAIN_DEADLINE_S = 30


class ProbeSetupError(RuntimeError):
    """The probe could not prepare what it needs before spawning the child."""


# --------------------------------------------------------------------------- #
# Probe-owned options (single-token, stripped from the child command)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ProbeOptions:
    """Parsed probe-owned options (never part of the child command)."""

    formation: str
    config: str | None = None
    cwd: str | None = None
    expected_version: str | None = None


def usage_error(argv: Sequence[str]) -> str | None:
    """The usage error for misuse of a probe-owned option, or ``None``.

    Only the single-token spelling is accepted: ``--opt VALUE`` leaves the
    value ambiguous (it could be the child server's own argv), so it is a
    usage error rather than a guess.  An empty value (``--config=``) is
    equally unusable — the probe owns the config it needs.
    """
    for arg in argv:
        for opt in OWNED_BARE_OPTIONS:
            if arg == opt:
                return (
                    "usage error: pass each probe option as a single token "
                    f"({', '.join(VALUE_OPTION_LABELS[o] for o in OWNED_BARE_OPTIONS)}); "
                    f"a bare '{opt} VALUE' pair is ambiguous with the child command "
                    f"(the next token could be the server's own argv). "
                    f"Alternatively set {PROBE_FORMATION_ENV}."
                )
    for arg in argv:
        if arg in (PROBE_CONFIG_OPTION, PROBE_CWD_OPTION):
            return f"usage error: {arg.rstrip('=')} needs a path (empty value given)."
        if arg == PROBE_EXPECTED_VERSION_OPTION:
            return (
                "usage error: --expected-version needs a version "
                "(empty value given), e.g. --expected-version=0.2.6."
            )
    return None


def parse_owned_options(
    argv: Sequence[str], env: Mapping[str, str] | None = None
) -> tuple[ProbeOptions, list[str]]:
    """Split every probe-owned option out of ``argv``.

    Returns ``(options, child_cmd)``: the parsed options and the child command
    with every probe-owned token removed. The env var
    ``CHIMERA_PROBE_FORMATION`` is honored when no ``--formation`` option is
    given; ``--formation=`` with an empty value keeps the env/default formation
    (backward compatible). ``--expected-version=`` is optional — without it the
    probe only PRINTS the handshake version and compares nothing.
    """
    environ: Mapping[str, str] = os.environ if env is None else env
    formation = (environ.get(PROBE_FORMATION_ENV) or "").strip() or DEPTH_FORMATION
    config: str | None = None
    cwd: str | None = None
    expected_version: str | None = None
    cmd: list[str] = []
    for arg in argv:
        if arg.startswith(PROBE_FORMATION_OPTION):
            value = arg[len(PROBE_FORMATION_OPTION) :].strip()
            formation = value or formation
            continue
        if arg.startswith(PROBE_CONFIG_OPTION):
            value = arg[len(PROBE_CONFIG_OPTION) :].strip()
            config = value or config
            continue
        if arg.startswith(PROBE_CWD_OPTION):
            value = arg[len(PROBE_CWD_OPTION) :].strip()
            cwd = value or cwd
            continue
        if arg.startswith(PROBE_EXPECTED_VERSION_OPTION):
            value = arg[len(PROBE_EXPECTED_VERSION_OPTION) :].strip()
            expected_version = value or expected_version
            continue
        cmd.append(arg)
    return (
        ProbeOptions(
            formation=formation,
            config=config,
            cwd=cwd,
            expected_version=expected_version,
        ),
        cmd,
    )


def parse_formation(
    argv: list[str], env: dict[str, str] | None = None
) -> tuple[str, list[str]]:
    """Backward-compatible single-option view of :func:`parse_owned_options`."""
    options, cmd = parse_owned_options(argv, env)
    return options.formation, cmd


# --------------------------------------------------------------------------- #
# Config provisioning (DF-CHIMERA-0917-5)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ProvisionPlan:
    """Where the child's config comes from, decided without touching the disk."""

    source: str  # "generated" | "explicit" | "cwd"
    cwd: str
    config_path: str | None  # None → the child discovers its own config (cwd mode)
    generate: bool


class ProvisionResult(NamedTuple):
    """The config actually handed to the child, plus the remaps applied."""

    config_path: str | None
    cwd: str
    source: str
    remaps: tuple[Remap, ...]


def plan_config_provision(
    options: ProbeOptions, *, temp_dir: str | None = None
) -> ProvisionPlan:
    """Decide where the child's config/cwd come from (pure).

    * ``--config=PATH`` → that file, ``CHIMERA_CONFIG=PATH``, cwd = ``--cwd``
      or the file's directory.
    * ``--cwd=PATH`` (no ``--config``) → run in ``PATH`` and let the child walk
      up to the directory's own ``chimera.yaml`` (``CHIMERA_CONFIG`` cleared).
    * neither → the probe GENERATES a config in ``temp_dir`` (a fresh
      ``tempfile.mkdtemp`` when ``temp_dir`` is None) and points the child at
      it. This is the deterministic default: a fresh checkout with no
      untracked ``chimera.yaml`` is enough.
    """
    if options.config:
        path = os.path.abspath(os.path.expanduser(options.config))
        cwd = (
            os.path.abspath(os.path.expanduser(options.cwd))
            if options.cwd
            else os.path.dirname(path)
        )
        return ProvisionPlan(source="explicit", cwd=cwd, config_path=path, generate=False)
    if options.cwd:
        cwd = os.path.abspath(os.path.expanduser(options.cwd))
        return ProvisionPlan(source="cwd", cwd=cwd, config_path=None, generate=False)
    directory = (
        os.path.abspath(temp_dir)
        if temp_dir
        else tempfile.mkdtemp(prefix=PROBE_CONFIG_DIR_PREFIX)
    )
    return ProvisionPlan(
        source="generated",
        cwd=directory,
        config_path=os.path.join(directory, GENERATED_CONFIG_NAME),
        generate=True,
    )


# --------------------------------------------------------------------------- #
# Child command resolution (QA-CHIMERA-V2-17)
# --------------------------------------------------------------------------- #
#
# ``main`` resolves the executable token against the INVOKING cwd before any
# plan is made, so both the provisioning step (which runs the child's sibling
# CLI in the generated config dir) and the spawn see the same absolute token.


def _has_path_separator(token: str) -> bool:
    """True when *token* names a path rather than a bare PATH-lookup command."""
    return os.sep in token or (os.altsep is not None and os.altsep in token)


def resolve_child_command(
    cmd: Sequence[str],
    *,
    base_dir: str,
    exists: Callable[[str], bool] = os.path.isfile,
) -> tuple[list[str], str | None]:
    """Resolve the child's executable token against the INVOKING cwd (pure).

    Returns ``(resolved_cmd, usage_error)``: the command to spawn and, when the
    token names a path that is not there, a named usage message instead of an
    exception. ``main`` prints that message and exits 2 — a missing child is a
    usage error, never a traceback from ``subprocess.Popen``.

    Why this is needed (QA-CHIMERA-V2-17): with neither ``--config`` nor
    ``--cwd`` the probe generates a config in a fresh temp dir and spawns the
    child with THAT dir as cwd (``PROBE_CWD``), so a relative token was
    resolved against the temp dir — ``FileNotFoundError: '.venv/bin/chimera-mcp'``
    at the spawn, and the same unresolvable bin dir broke the provisioning step
    that runs the child's sibling CLI there. Resolving once, before both, is
    what keeps the two steps consistent.

    Arms:

    * empty ``cmd`` → returned unchanged (``main`` supplies its own default).
    * ``cmd[0]`` absolute (after ``~`` expansion, a no-op for ordinary paths)
      → returned as given; ``CHILD_CMD`` still prints the operator's path.
    * ``cmd[0]`` relative and ``base_dir/cmd[0]`` exists → absolutized; the
      rest of the argv is never rewritten.
    * ``cmd[0]`` relative, containing a path separator, with no such file →
      named usage error, no exception raised.
    * ``cmd[0]`` relative without a separator (the bare ``chimera mcp``
      form) → left untouched so ``PATH`` lookup still happens; it is never
      joined onto *base_dir*.

    ``exists`` is injectable so the resolution rule can be tested without
    touching the filesystem.
    """
    if not cmd:
        return list(cmd), None
    token = os.path.expanduser(cmd[0])
    if os.path.isabs(token):
        return [token, *cmd[1:]], None
    if not _has_path_separator(token):
        return [token, *cmd[1:]], None
    candidate = os.path.normpath(os.path.abspath(os.path.join(base_dir, token)))
    if exists(candidate):
        return [candidate, *cmd[1:]], None
    return (
        list(cmd),
        f"child command not found: {cmd[0]} (resolved against {base_dir}); "
        f"pass an absolute path",
    )


def _child_bin_dir(child_cmd: Sequence[str]) -> str:
    """The bin directory that owns the child entry point ('' when argv-less)."""
    if not child_cmd:
        return ""
    return os.path.dirname(os.path.abspath(child_cmd[0]))


def resolve_child_python(
    child_cmd: Sequence[str], *, fallback: str | None = None
) -> str:
    """The interpreter that owns the child entry point.

    ``<bin-dir>/python`` next to ``chimera-mcp`` is the interpreter the child
    itself runs under — the one guaranteed to have chimera's dependencies
    (notably PyYAML, which the probe's own interpreter may lack in CI).
    """
    bin_dir = _child_bin_dir(child_cmd)
    for name in ("python", "python3"):
        candidate = os.path.join(bin_dir, name) if bin_dir else ""
        if candidate and os.path.isfile(candidate):
            return candidate
    return fallback or sys.executable


def config_init_command(
    child_cmd: Sequence[str], *, child_python: str | None = None
) -> list[str]:
    """The command that generates a config: the child's sibling CLI.

    ``<bin-dir>/chimera config init`` next to ``chimera-mcp`` when it exists
    (the venv case, including the release gate's ``/tmp/release-venv``), else
    ``<child-python> -m chimera config init``. Both resolve the shipped
    template through ``chimera.config.find_example_config_path()`` — the probe
    never hand-writes a YAML template that would duplicate the config schema.
    """
    sibling = os.path.join(_child_bin_dir(child_cmd), "chimera")
    if os.path.isfile(sibling):
        return [sibling, "config", "init"]
    exe = child_python or resolve_child_python(child_cmd)
    return [exe, "-m", "chimera", "config", "init"]


#: Bridge programs: parse/serialise the YAML document with the CHILD's
#: interpreter when the probe's own interpreter has no PyYAML. A hand-rolled
#: subset parser is never used — it silently truncates documents on syntax it
#: does not know (e.g. ``>-`` chomping), which would corrupt the config we are
#: about to hand to the server.
_YAML_TO_JSON_PROGRAM = (
    "import json,sys,yaml;"
    "sys.stdout.write(json.dumps(yaml.safe_load(open(sys.argv[1], encoding='utf-8'))))"
)
_JSON_TO_YAML_PROGRAM = (
    "import json,sys,yaml;"
    "yaml.safe_dump(json.load(sys.stdin), open(sys.argv[1], 'w', encoding='utf-8'),"
    "sort_keys=False, default_flow_style=False)"
)


def _yaml_available() -> bool:
    """True when this interpreter can import PyYAML."""
    try:
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True


def load_config_document(path: str, *, python_exe: str | None = None) -> dict:
    """Parse a config YAML document into a plain dict.

    Prefers this interpreter's PyYAML; otherwise delegates to *python_exe*
    (the child's sibling interpreter). Raises :class:`ProbeSetupError` when
    neither can parse it, rather than guessing at the document.
    """
    try:
        if _yaml_available():
            import yaml

            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        elif python_exe:
            proc = subprocess.run(
                [python_exe, "-c", _YAML_TO_JSON_PROGRAM, str(path)],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise ProbeSetupError(
                    f"failed to parse {path} with {python_exe}: "
                    f"{proc.stderr.strip()[:400]}"
                )
            data = json.loads(proc.stdout)
        else:
            raise ProbeSetupError(
                f"PyYAML is not importable by {sys.executable} and no child "
                f"interpreter is known — cannot read {path}"
            )
    except OSError as exc:
        raise ProbeSetupError(f"cannot read config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProbeSetupError(f"config {path} did not parse to a mapping")
    return data


def write_config_document(
    path: str, document: Mapping[str, Any], *, python_exe: str | None = None
) -> None:
    """Serialise *document* back to *path* (same interpreter policy as load)."""
    if _yaml_available():
        import yaml

        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(dict(document), fh, sort_keys=False, default_flow_style=False)
        return
    if not python_exe:
        raise ProbeSetupError(
            f"PyYAML is not importable by {sys.executable} and no child "
            f"interpreter is known — cannot write {path}"
        )
    payload = json.dumps(document)
    proc = subprocess.run(
        [python_exe, "-c", _JSON_TO_YAML_PROGRAM, str(path)],
        input=payload,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ProbeSetupError(
            f"failed to write {path} with {python_exe}: {proc.stderr.strip()[:400]}"
        )


# --------------------------------------------------------------------------- #
# Credential view + formation model remap (DF-CHIMERA-0917-5)
# --------------------------------------------------------------------------- #

_ENV_PLACEHOLDER = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


class Remap(NamedTuple):
    """One uncredentialed model substituted for a credentialed one."""

    model: str
    replacement: str
    env_var: str
    role: str

    def evidence_line(self) -> str:
        """The exact stdout evidence line for this substitution."""
        return (
            f"FORMATION_MODEL_REMAP={self.model} -> {self.replacement} "
            f"({self.env_var} unset; {self.role})"
        )


def _placeholder_env_var(value: Any) -> str | None:
    """The env var name inside a ``${VAR}`` config value, or ``None``."""
    if not isinstance(value, str):
        return None
    match = _ENV_PLACEHOLDER.match(value.strip())
    return match.group(1) if match else None


def _env_value(env: Mapping[str, str], name: str | None) -> str:
    if not name:
        return ""
    return (env.get(name) or "").strip()


def _credential_from_value(value: Any, env: Mapping[str, str]) -> str | None:
    """Resolve a config credential value (literal or ``${VAR}``) against *env*."""
    if not isinstance(value, str):
        return None
    var = _placeholder_env_var(value)
    if var is not None:
        return _env_value(env, var) or None
    return value.strip() or None


def effective_credential_env(env: Mapping[str, str]) -> dict[str, str]:
    """*env* plus the ``~/.hermes/.env`` fallback the config loader uses.

    ``chimera.config`` resolves provider keys from the process environment and,
    failing that, from ``~/.hermes/.env``; the probe mirrors that so a box whose
    keys live only in the Hermes dotenv file is not mis-read as uncredentialed.
    """
    merged = dict(_hermes_dotenv_values())
    merged.update({k: v for k, v in env.items() if isinstance(v, str)})
    return merged


def _hermes_dotenv_values() -> dict[str, str]:
    """Best-effort parse of ``~/.hermes/.env`` (stdlib only)."""
    values: dict[str, str] = {}
    try:
        with open(os.path.expanduser("~/.hermes/.env"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        values[key] = val
    return values


def provider_credential_env_var(
    config: Mapping[str, Any], provider: str | None
) -> str | None:
    """The env var name that must be set for *provider*, if the config names one."""
    if not provider:
        return None
    entry = (config.get("providers") or {}).get(provider)
    if isinstance(entry, Mapping):
        if entry.get("api_key_env"):
            return str(entry["api_key_env"])
        var = _placeholder_env_var(entry.get("api_key"))
        if var:
            return var
    return _placeholder_env_var((config.get("api_keys") or {}).get(provider))


def provider_credential_resolved(
    config: Mapping[str, Any], provider: str | None, env: Mapping[str, str]
) -> bool:
    """Mirror of ``chimera.config.provider_credential_resolved`` over the document.

    Resolution order: ``api_keys[provider]`` (literal or ``${VAR}``) →
    ``providers[provider].api_key`` → ``providers[provider].api_key_env``.
    """
    if not provider:
        return False
    if _credential_from_value((config.get("api_keys") or {}).get(provider), env):
        return True
    entry = (config.get("providers") or {}).get(provider)
    if isinstance(entry, Mapping):
        if _credential_from_value(entry.get("api_key"), env):
            return True
        if _env_value(env, entry.get("api_key_env") if entry.get("api_key_env") else None):
            return True
    return False


def model_provider(config: Mapping[str, Any], model: str) -> str | None:
    """The provider named by *model*'s catalog entry, or ``None``."""
    entry = (config.get("models") or {}).get(model)
    if isinstance(entry, Mapping) and entry.get("provider"):
        return str(entry["provider"])
    return None


def resolve_alias(config: Mapping[str, Any], name: str) -> str:
    """Resolve the ``default`` / ``default_worker`` formation aliases."""
    defaults = config.get("defaults") or {}
    if name == "default":
        return str(defaults.get("default_aggregator") or name)
    if name == "default_worker":
        return str(defaults.get("default_worker") or name)
    return name


def formation_model_references(preset: Any) -> list[tuple[tuple, str]]:
    """``(path, model-name)`` for every model a formation preset references.

    Covers the named-preset reference sites: ``aggregator``/``audit`` scalars,
    ``aggregators``/``worker_models`` lists and ``dag.stages[*].model``. The
    implicit worker slots of a preset that only sets ``workers: N`` are handled
    separately by :func:`_implicit_worker_slots` (they use
    ``defaults.default_worker``).
    """
    refs: list[tuple[tuple, str]] = []
    if not isinstance(preset, Mapping):
        return refs
    for key in ("aggregator", "audit"):
        value = preset.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(((key,), value.strip()))
    for key in ("aggregators", "worker_models"):
        value = preset.get(key)
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, str) and item.strip():
                    refs.append(((key, index), item.strip()))
    dag = preset.get("dag")
    if isinstance(dag, Mapping):
        for index, stage in enumerate(dag.get("stages") or []):
            model = stage.get("model") if isinstance(stage, Mapping) else None
            if isinstance(model, str) and model.strip():
                refs.append((("dag", "stages", index, "model"), model.strip()))
    return refs


def _implicit_worker_slots(preset: Any) -> int:
    """Worker slots that fall back to ``defaults.default_worker`` (0 when none)."""
    if not isinstance(preset, Mapping) or preset.get("mode") == "auto":
        return 0
    if preset.get("worker_models") or preset.get("dag"):
        return 0
    workers = preset.get("workers")
    if isinstance(workers, int) and workers > 0:
        return workers
    return 0


def _role(formation: str, path: tuple) -> str:
    """Human-readable reference site, e.g. ``speed.worker_models[1]``."""
    trail = ""
    for key in path:
        trail += f"[{key}]" if isinstance(key, int) else (f".{key}" if trail else str(key))
    return f"{formation}.{trail}"


def remap_uncredentialed_models(
    config: Mapping[str, Any],
    env: Mapping[str, str],
    *,
    formation: str,
    fallback: str = DEFAULT_REMAP_MODEL,
) -> tuple[dict, list[Remap]]:
    """Substitute models the *formation* references that have no credential.

    Pure: takes the parsed config document plus an environment mapping and
    returns ``(new_config, remaps)`` — the document is deep-copied, never
    mutated in place. Every substitution is returned as a :class:`Remap` so the
    caller can PRINT it; a remap is never silent, because a gate that quietly
    substitutes a different model weakens its own coverage claim.

    The remap happens only when the fallback model itself has a resolved
    credential — otherwise nothing is substituted (and the caller reports the
    formation as unsatisfiable) rather than steering the child at another model
    that cannot run either.
    """
    document = copy.deepcopy(dict(config))
    preset = (document.get("formations") or {}).get(formation)
    if not isinstance(preset, dict):
        return document, []

    fallback_provider = model_provider(document, fallback)
    fallback_usable = provider_credential_resolved(document, fallback_provider, env)
    remaps: list[Remap] = []

    def _substitute(path: tuple, name: str, resolved: str) -> None:
        # Reference paths are preset-relative (they name keys inside the
        # formation preset, e.g. ``worker_models[1]`` / ``dag.stages[0].model``).
        target: Any = preset
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = fallback
        env_var = (
            provider_credential_env_var(document, model_provider(document, resolved))
            or "provider credentials"
        )
        remaps.append(
            Remap(
                model=resolved,
                replacement=fallback,
                env_var=env_var,
                role=_role(formation, path),
            )
        )

    for path, name in formation_model_references(preset):
        resolved = resolve_alias(document, name)
        if provider_credential_resolved(document, model_provider(document, resolved), env):
            continue  # credentialed — untouched, the leak leg stays exercised
        if fallback_usable:
            _substitute(path, name, resolved)

    slots = _implicit_worker_slots(preset)
    if slots:
        default_worker = resolve_alias(document, "default_worker")
        credentialed = provider_credential_resolved(
            document, model_provider(document, default_worker), env
        )
        if not credentialed and fallback_usable:
            preset["worker_models"] = [fallback] * slots
            env_var = (
                provider_credential_env_var(
                    document, model_provider(document, default_worker)
                )
                or "provider credentials"
            )
            remaps.append(
                Remap(
                    model=default_worker,
                    replacement=fallback,
                    env_var=env_var,
                    role=f"{formation}.workers({slots})",
                )
            )
    return document, remaps


def provision_config(
    plan: ProvisionPlan,
    *,
    child_cmd: Sequence[str],
    formation: str,
    env: Mapping[str, str],
    credential_env: Mapping[str, str] | None = None,
) -> ProvisionResult:
    """Make the config the child will use ready on disk (subprocess I/O).

    ``env`` is the base environment the child runs under (``CHIMERA_CONFIG``
    must not be in it — the caller pins it afterwards). For a generated config
    this runs the child's sibling CLI, then applies — and reports — the
    formation's credential remaps. The generated directory is deliberately left
    on disk: the caller prints its path as evidence and the child may still be
    running when the probe returns.
    """
    if plan.source == "generated":
        os.makedirs(plan.cwd, exist_ok=True)
        command = config_init_command(child_cmd)
        proc = subprocess.run(
            command, cwd=plan.cwd, env=dict(env), capture_output=True, text=True
        )
        assert plan.config_path is not None
        if proc.returncode != 0 or not os.path.isfile(plan.config_path):
            raise ProbeSetupError(
                f"`{' '.join(command)}` failed in {plan.cwd} "
                f"(rc={proc.returncode}): {(proc.stderr or proc.stdout).strip()[:600]}"
            )
        child_python = resolve_child_python(child_cmd)
        document = load_config_document(plan.config_path, python_exe=child_python)
        remapped, remaps = remap_uncredentialed_models(
            document, credential_env if credential_env is not None else env, formation=formation
        )
        if remaps:
            write_config_document(plan.config_path, remapped, python_exe=child_python)
        return ProvisionResult(plan.config_path, plan.cwd, plan.source, tuple(remaps))

    if plan.source == "explicit":
        assert plan.config_path is not None
        if not os.path.isfile(plan.config_path):
            raise ProbeSetupError(f"--config={plan.config_path} does not exist")
        return ProvisionResult(plan.config_path, plan.cwd, plan.source, ())

    if not os.path.isdir(plan.cwd):
        raise ProbeSetupError(f"--cwd={plan.cwd} is not a directory")
    return ProvisionResult(None, plan.cwd, plan.source, ())


# --------------------------------------------------------------------------- #
# JSON-RPC request / response contract
# --------------------------------------------------------------------------- #


def depth_arguments(formation: str = DEPTH_FORMATION) -> dict:
    """The chimera_deliberate arguments for one formation."""
    return {"prompt": DEPTH_PROMPT, "formation": formation}


def build_messages(formation: str = DEPTH_FORMATION) -> list[dict]:
    """The exact JSON-RPC conversation the probe drives: ids 1..3 in order."""
    return [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "probe", "version": "0.0.1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": DEPTH_TOOL, "arguments": depth_arguments(formation)},
        },
    ]


def is_jsonrpc_line(line: str) -> bool:
    """A stdout line is 'pure' iff it parses as a JSON-RPC 2.0 object."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return False
    return isinstance(obj, dict) and obj.get("jsonrpc") == "2.0"


def collect_responses(stdout_lines: list[str]) -> tuple[list[int], dict[int, dict]]:
    """Extract response ids (in arrival order) and responses by id."""
    order: list[int] = []
    responses: dict[int, dict] = {}
    for text in stdout_lines:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("jsonrpc") == "2.0" and obj.get("id") is not None:
            responses[int(obj["id"])] = obj
            order.append(int(obj["id"]))
    return order, responses


def extract_tool_text(result: dict) -> str:
    """Extract the tool's text payload from an MCP CallToolResult shape."""
    content = result.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        if parts:
            return "".join(parts)
    text = result.get("text")
    if isinstance(text, str):
        return text
    return ""


def check_depth_result(r3: dict) -> tuple[list[str], dict]:
    """Validate the tools/call chimera_deliberate result.

    Returns (problems, info). ``info["answer"]`` carries the merged answer
    when the call succeeded; ``info["marker_hit"]`` says whether the
    deterministic arithmetic marker (17 * 23 = 391) appears in it.
    """
    problems: list[str] = []
    info: dict = {}
    if r3.get("isError"):
        problems.append(f"{DEPTH_TOOL} returned an error result")
    text = extract_tool_text(r3)
    if not text:
        problems.append(f"{DEPTH_TOOL} returned no text content")
        return problems, info
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        problems.append(f"{DEPTH_TOOL} did not return JSON content")
        return problems, info
    if not isinstance(payload, dict):
        problems.append(f"{DEPTH_TOOL} JSON is not an object")
        return problems, info
    answer = payload.get("answer", "")
    if not (isinstance(answer, str) and answer.strip()):
        problems.append(f"{DEPTH_TOOL} returned an empty answer")
        return problems, info
    info["answer"] = answer
    info["marker_hit"] = DEPTH_MARKER in answer
    return problems, info


def check_handshake(stdout_lines: list[str], order: list[int], responses: dict[int, dict]) -> list[str]:
    """Purity + ordering + inventory checks shared by every probe run."""
    problems: list[str] = []
    bad = [(i, line[:160]) for i, line in enumerate(stdout_lines, 1) if not is_jsonrpc_line(line)]
    if bad:
        problems.append(f"non-JSON-RPC stdout lines: {bad}")
    if order != EXPECTED_ORDER:
        problems.append(f"responses missing/out of order: got ids {order}, expected {EXPECTED_ORDER}")
    if stdout_lines:
        try:
            first_id = json.loads(stdout_lines[0]).get("id")
            if first_id != 1:
                problems.append("initialize response is not stdout line 1")
        except json.JSONDecodeError:
            problems.append("stdout line 1 is not JSON")
    tool_names = {t.get("name") for t in responses.get(2, {}).get("result", {}).get("tools", [])}
    if tool_names != TOOL_INVENTORY:
        problems.append(f"tools/list returned {tool_names}")
    return problems


# --------------------------------------------------------------------------- #
# Version reporting (DF-CHIMERA-V2-9)
# --------------------------------------------------------------------------- #
#
# The handshake's ``serverInfo.version`` is part of the contract a real MCP
# client uses to tell one build from another. The pre-0.2.6 server advertised
# the mcp SDK's own version (1.28.1) for a 0.2.6 chimera, because the SDK's
# ``FastMCP`` takes no version kwarg and the low-level server falls back to
# ``pkg_version("mcp")``. The probe always reports what the handshake said and
# can gate on it with ``--expected-version``.


def server_info_version(result: Mapping[str, Any] | None) -> str | None:
    """The ``serverInfo.version`` an initialize result reports, or ``None``.

    ``None`` covers both "no initialize response at all" and "the response
    carried no version" — the probe prints it as ``(missing)`` instead of
    inventing a value (which is what hid this defect: a wrong version looked
    like a real one).
    """
    if not isinstance(result, Mapping):
        return None
    info = result.get("serverInfo")
    if not isinstance(info, Mapping):
        return None
    version = info.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def server_version_mismatch(expected: str | None, actual: str | None) -> str | None:
    """The named mismatch evidence line, or ``None`` when nothing is compared."""
    if not expected or actual == expected:
        return None
    return f"SERVER_VERSION_MISMATCH=expected:{expected} actual:{actual or MISSING_VERSION}"


def drive_stdio(
    cmd: list[str], env: dict[str, str], cwd: str, formation: str = DEPTH_FORMATION
) -> tuple[list[str], list[int], dict[int, dict], str]:
    """Run the JSON-RPC conversation against ``cmd`` over real stdio pipes.

    Paced like a real MCP client: stdin stays open while responses are read
    (closing stdin early races the mcp SDK's EOF shutdown and can drop the
    last response), then stdin is closed and the process is allowed to exit.
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=cwd,
    )
    assert proc.stdin is not None and proc.stdout is not None

    msgs = build_messages(formation)
    proc.stdin.write("".join(json.dumps(m) + "\n" for m in msgs).encode())
    proc.stdin.flush()

    stdout_lines: list[str] = []
    buf = b""

    def _drain() -> None:
        nonlocal buf
        try:
            ready, _, _ = select.select([proc.stdout], [], [], 0)
        except (ValueError, OSError):
            return
        if not ready:
            return
        chunk = os.read(proc.stdout.fileno(), 65536)
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode(errors="replace").strip()
            if text:
                stdout_lines.append(text)

    deadline = time.monotonic() + READ_DEADLINE_S
    while len(collect_responses(stdout_lines)[0]) < 3 and time.monotonic() < deadline:
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if ready:
            _drain()
    proc.stdin.close()
    while time.monotonic() < deadline + DRAIN_DEADLINE_S:
        if proc.poll() is not None:
            _drain()
            break
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if ready:
            _drain()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    err = (proc.stderr.read() if proc.stderr else b"").decode(errors="replace")
    order, responses = collect_responses(stdout_lines)
    return stdout_lines, order, responses, err


def main(argv: list[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    problem = usage_error(raw)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    options, cmd = parse_owned_options(raw)
    if not cmd:
        cmd = [os.path.join(REPO, ".venv", "bin", "chimera-mcp")]
    # Resolve the child token against the INVOKING cwd BEFORE provisioning and
    # before the spawn: the generated-config default runs the child in its own
    # temp dir, where a relative token does not exist (QA-CHIMERA-V2-17).
    cmd, child_problem = resolve_child_command(cmd, base_dir=os.getcwd())
    if child_problem:
        print(child_problem, file=sys.stderr)
        return 2

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    # The credential view mirrors the config loader (process env, then the
    # Hermes dotenv fallback) so a box whose keys live only in ~/.hermes/.env is
    # not mis-read as uncredentialed.
    credential_env = effective_credential_env(env)
    init_env = {k: v for k, v in env.items() if k != "CHIMERA_CONFIG"}

    plan = plan_config_provision(options)
    try:
        provisioned = provision_config(
            plan,
            child_cmd=cmd,
            formation=options.formation,
            env=init_env,
            credential_env=credential_env,
        )
    except ProbeSetupError as exc:
        print(f"PROBE SETUP FAIL: {exc}", file=sys.stderr)
        return 2

    if provisioned.config_path:
        env["CHIMERA_CONFIG"] = provisioned.config_path
    else:
        # cwd mode: let the child discover the directory's own chimera.yaml.
        env.pop("CHIMERA_CONFIG", None)

    stdout_lines, order, responses, err = drive_stdio(
        cmd, env, provisioned.cwd, options.formation
    )

    # The handshake version (DF-CHIMERA-V2-9): always reported, optionally gated.
    handshake_version = server_info_version(responses.get(1, {}).get("result", {}))
    version_mismatch = server_version_mismatch(options.expected_version, handshake_version)

    problems = check_handshake(stdout_lines, order, responses)
    depth_problems, depth_info = check_depth_result(responses.get(3, {}).get("result", {}))
    problems.extend(depth_problems)
    if version_mismatch:
        problems.append(
            f"version mismatch: expected {options.expected_version}, "
            f"got {handshake_version or MISSING_VERSION}"
        )

    tool_names = {t.get("name") for t in responses.get(2, {}).get("result", {}).get("tools", [])}
    print(f"CHILD_CMD={' '.join(cmd)}")
    print(f"FORMATION={options.formation}")
    print(f"CONFIG_SOURCE={provisioned.source}")
    print(
        "CONFIG_PATH="
        + (provisioned.config_path or "(unset: child discovers its own config from cwd)")
    )
    print(f"PROBE_CWD={provisioned.cwd}")
    print(f"SERVER_VERSION={handshake_version or MISSING_VERSION}")
    if version_mismatch:
        print(version_mismatch)
    print(f"MODEL_REMAPS_TOTAL={len(provisioned.remaps)}")
    for remap in provisioned.remaps:
        print(remap.evidence_line())
    print(f"NON_JSON_RPC_STDOUT_LINES={sum(1 for ln in stdout_lines if not is_jsonrpc_line(ln))}")
    print(f"RESPONSE_IDS={order}")
    print(f"TOOL_NAMES={sorted(tool_names)}")
    print(f"DEPTH_TOOL={DEPTH_TOOL}")
    answer = depth_info.get("answer", "")
    if isinstance(answer, str) and answer.strip():
        first_line = next((ln.strip() for ln in answer.splitlines() if ln.strip()), "")
        marker = "hit" if depth_info.get("marker_hit") else "NOT stated verbatim"
        print(f"ANSWER_CHARS={len(answer)}")
        print(f"ANSWER_MARKER={DEPTH_MARKER_NOTE}: {marker}")
        print(f"ANSWER_HEAD={first_line[:120]!r}")
    for i, line in enumerate(stdout_lines, 1):
        print(f"  stdout[{i}]: {line[:120]}")
    if problems:
        print("PROBE FAIL:")
        for p in problems:
            print(f"  - {p}")
        print("=== STDERR (last 30 lines) ===")
        print("\n".join(err.splitlines()[-30:]))
        return 1
    print(
        f"PROBE OK: all stdout lines are JSON-RPC 2.0; initialize is line 1; "
        f"3 tools; {DEPTH_TOOL} returned a non-empty merged answer"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
