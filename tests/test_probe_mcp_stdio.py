"""Offline regression tests for scripts/probe_mcp_stdio.py — DF-CHIMERA-0911-1.

The release probe is the gate that proves a wheel's ``chimera-mcp`` stays
stdout-pure on a REAL deliberation call. 0.2.3's probe only made a
``chimera_models`` handshake call, which never triggers the lazy LiteLLM
import — so a polluted-on-depth wheel could pass the old probe. These tests
pin the probe's request/validation contract OFFLINE (no subprocess, no
network):

* the depth call is a real ``chimera_deliberate`` tools/call with a
  deterministic arithmetic prompt and formation=simple;
* the validator rejects the failure shapes the probe exists to catch
  (polluted stdout, wrong order, missing tool, non-JSON or empty answer);
* the driver preserves the 0.2.3-era purity checks (initialize line 1,
  exact 3-tool inventory, response order, zero-pollution exit contract).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
PROBE_PATH = REPO / "scripts" / "probe_mcp_stdio.py"

_ERROR_TEXT = "Error: dispatcher boom"
_OK_RESULT = {"content": [{"type": "text", "text": json.dumps({"answer": "17 * 23 = 391"})}]}
_EMPTY_ANSWER_RESULT = {"content": [{"type": "text", "text": json.dumps({"answer": ""})}]}
_BLANK_ANSWER_RESULT = {"content": [{"type": "text", "text": json.dumps({"answer": "  "})}]}
_NO_TEXT_RESULT = {"content": [{"type": "image", "data": "x"}]}
_ERR_RESULT = {"content": [{"type": "text", "text": _ERROR_TEXT}], "isError": True}
_NON_JSON_RESULT = {"content": [{"type": "text", "text": "hello, world"}]}

_TOOLS_LIST_RESULT = {
    "tools": [
        {"name": "chimera_deliberate", "description": "d"},
        {"name": "chimera_formations", "description": "f"},
        {"name": "chimera_models", "description": "m"},
    ]
}


def _load_probe() -> ModuleType:
    """Load scripts/probe_mcp_stdio.py as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("probe_mcp_stdio", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["probe_mcp_stdio"] = mod
    spec.loader.exec_module(mod)
    return mod


probe = _load_probe()


# --- request contract ------------------------------------------------------- #


def test_depth_call_is_chimera_deliberate() -> None:
    """The depth call must be a REAL chimera_deliberate tools/call."""
    calls = [m for m in probe.build_messages() if m.get("method") == "tools/call"]
    assert len(calls) == 1, f"expected exactly one tools/call, got {len(calls)}"
    call = calls[0]
    assert call["id"] == 3
    assert call["params"]["name"] == "chimera_deliberate"


def test_depth_arguments_are_deterministic_arithmetic() -> None:
    """Deterministic prompt + formation=simple: cheap, stable marker, full merge path."""
    args = probe.DEPTH_ARGUMENTS
    assert args["prompt"] == "What is 17 * 23? Show the computation."
    assert args["formation"] == "simple"


def test_depth_marker_is_correct_arithmetic() -> None:
    """The release marker must be real arithmetic — a wrong marker would fail live."""
    assert str(17 * 23) == probe.DEPTH_MARKER
    assert probe.DEPTH_MARKER_NOTE == "17 * 23 = 391"


def test_probe_source_never_regresses_to_catalog_call() -> None:
    """The probe source must not name a shallow tool as its depth call."""
    src = PROBE_PATH.read_text(encoding="utf-8")
    assert 'DEPTH_TOOL = "chimera_deliberate"' in src
    assert 'DEPTH_TOOL = "chimera_models"' not in src
    assert 'DEPTH_TOOL = "chimera_formations"' not in src


def test_conversation_shape_matches_handshake_contract() -> None:
    """initialize first, notifications/initialized second, tools/list before the call."""
    msgs = probe.build_messages()
    assert [m.get("id") for m in msgs] == [1, None, 2, 3]
    assert msgs[0]["method"] == "initialize"
    assert msgs[1]["method"] == "notifications/initialized"
    assert msgs[2]["method"] == "tools/list"
    assert msgs[3]["method"] == "tools/call"
    assert all(m["jsonrpc"] == "2.0" for m in msgs)


# --- response classification ------------------------------------------------ #


def test_jsonrpc_line_accepts_valid_frames() -> None:
    assert probe.is_jsonrpc_line('{"jsonrpc": "2.0", "id": 1, "result": {}}')
    assert probe.is_jsonrpc_line('{"jsonrpc": "2.0", "method": "x"}')
    assert probe.is_jsonrpc_line('{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}')


def test_jsonrpc_line_rejects_pollution() -> None:
    """The exact 0.2.3 pollution shapes must classify as non-JSON-RPC."""
    assert not probe.is_jsonrpc_line("provider_cache_hit module=... event=provider_cache_hit")
    assert not probe.is_jsonrpc_line("2026-09-11T12:00:00Z [info] provider_discovery_done")
    assert not probe.is_jsonrpc_line("")
    assert not probe.is_jsonrpc_line("not json at all")
    assert not probe.is_jsonrpc_line("[1, 2, 3]")
    assert not probe.is_jsonrpc_line('{"id": 1}')  # missing jsonrpc key
    assert not probe.is_jsonrpc_line('{"jsonrpc": "1.0", "id": 1}')  # wrong version


def test_collect_responses_order_and_map() -> None:
    lines = [
        '{"jsonrpc": "2.0", "id": 1, "result": {}}',
        '{"jsonrpc": "2.0", "id": 2, "result": {}}',
        '{"jsonrpc": "2.0", "id": 3, "result": {}}',
    ]
    order, responses = probe.collect_responses(lines)
    assert order == [1, 2, 3]
    assert sorted(responses) == [1, 2, 3]


def test_collect_responses_ignores_pollution_and_notifications() -> None:
    lines = [
        "structlog noise line",
        '{"jsonrpc": "2.0", "method": "notifications/initialized"}',
        '{"jsonrpc": "2.0", "id": 1, "result": {}}',
    ]
    order, responses = probe.collect_responses(lines)
    assert order == [1]
    assert sorted(responses) == [1]


# --- depth-call validation --------------------------------------------------- #


def test_depth_result_ok_answer_and_marker() -> None:
    problems, info = probe.check_depth_result(_OK_RESULT)
    assert problems == []
    assert info["answer"] == "17 * 23 = 391"
    assert info["marker_hit"] is True


def test_depth_result_marker_miss_is_reported_not_fatal() -> None:
    """A model may phrase the answer without the verbatim marker; that is not pollution."""
    ok = {"content": [{"type": "text", "text": json.dumps({"answer": "The product is 391."})}]}
    problems, info = probe.check_depth_result(ok)
    assert problems == []
    assert info["marker_hit"] is True  # '391' appears
    ok2 = {"content": [{"type": "text", "text": json.dumps({"answer": "Three hundred ninety-one."})}]}
    problems2, info2 = probe.check_depth_result(ok2)
    assert problems2 == []
    assert info2["marker_hit"] is False


def test_depth_result_rejects_error_result() -> None:
    problems, _ = probe.check_depth_result(_ERR_RESULT)
    assert any("error result" in p for p in problems)


def test_depth_result_rejects_missing_text() -> None:
    problems, _ = probe.check_depth_result(_NO_TEXT_RESULT)
    assert any("no text content" in p for p in problems)


def test_depth_result_rejects_non_json_text() -> None:
    problems, _ = probe.check_depth_result(_NON_JSON_RESULT)
    assert any("did not return JSON" in p for p in problems)


def test_depth_result_rejects_non_object_json() -> None:
    result = {"content": [{"type": "text", "text": json.dumps([1, 2])}]}
    problems, _ = probe.check_depth_result(result)
    assert any("not an object" in p for p in problems)


def test_depth_result_rejects_empty_answer() -> None:
    for result in (_EMPTY_ANSWER_RESULT, _BLANK_ANSWER_RESULT):
        problems, _ = probe.check_depth_result(result)
        assert any("empty answer" in p for p in problems), result


def test_depth_result_rejects_missing_answer_key() -> None:
    result = {"content": [{"type": "text", "text": json.dumps({"trace": {}})}]}
    problems, _ = probe.check_depth_result(result)
    assert any("empty answer" in p for p in problems)


# --- result-text extraction (CallToolResult shapes) -------------------------- #


def test_extract_tool_text_content_list() -> None:
    assert probe.extract_tool_text(_OK_RESULT) == '{"answer": "17 * 23 = 391"}'


def test_extract_tool_text_multiple_parts_concatenated() -> None:
    result = {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
    assert probe.extract_tool_text(result) == "ab"


def test_extract_tool_text_flat_fallback() -> None:
    assert probe.extract_tool_text({"text": "flat"}) == "flat"


def test_extract_tool_text_empty_shapes() -> None:
    assert probe.extract_tool_text({}) == ""
    assert probe.extract_tool_text({"content": []}) == ""
    assert probe.extract_tool_text({"content": "not-a-list"}) == ""


# --- handshake / purity checks ----------------------------------------------- #


def _handshake_lines() -> tuple[list[str], list[int], dict[int, dict]]:
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "chimera"}}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "result": _TOOLS_LIST_RESULT}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "result": _OK_RESULT}),
    ]
    order, responses = probe.collect_responses(lines)
    return lines, order, responses


def test_handshake_clean_run_has_no_problems() -> None:
    lines, order, responses = _handshake_lines()
    assert probe.check_handshake(lines, order, responses) == []


def test_handshake_flags_polluted_stdout() -> None:
    lines, order, responses = _handshake_lines()
    polluted = ["provider_cache_hit module=chimera provider=deepseek"] + lines
    problems = probe.check_handshake(polluted, order, responses)
    assert any("non-JSON-RPC stdout lines" in p for p in problems)


def test_handshake_flags_wrong_order() -> None:
    lines, _, responses = _handshake_lines()
    problems = probe.check_handshake(lines, [2, 1, 3], responses)
    assert any("out of order" in p for p in problems)


def test_handshake_flags_missing_response() -> None:
    lines, _, responses = _handshake_lines()
    problems = probe.check_handshake(lines, [1, 2], responses)
    assert any("out of order" in p for p in problems)


def test_handshake_flags_initialize_not_line_1() -> None:
    lines, order, responses = _handshake_lines()
    problems = probe.check_handshake(list(reversed(lines)), order, responses)
    assert any("not stdout line 1" in p for p in problems)


def test_handshake_flags_non_json_line_1() -> None:
    lines, order, responses = _handshake_lines()
    problems = probe.check_handshake(["garbage"] + lines[1:], order, responses)
    assert any("line 1 is not JSON" in p for p in problems)


def test_handshake_flags_missing_tool() -> None:
    lines, order, responses = _handshake_lines()
    responses[2]["result"]["tools"] = _TOOLS_LIST_RESULT["tools"][:2]
    problems = probe.check_handshake(lines, order, responses)
    assert any("tools/list returned" in p for p in problems)


def test_handshake_flags_no_responses_at_all() -> None:
    problems = probe.check_handshake(["garbage"], [], {})
    assert any("out of order" in p for p in problems)
    assert any("line 1 is not JSON" in p for p in problems)


# --- driver output / exit contract ------------------------------------------- #


def test_main_success_exit_contract(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A clean conversation prints evidence lines and exits 0."""
    captured: dict = {}

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        captured["cmd"] = cmd
        captured["formation"] = formation
        lines, order, responses = _handshake_lines()
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main(["/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 0
    assert captured["cmd"] == ["/fake/venv/bin/chimera-mcp"]
    assert captured["formation"] == "simple"
    assert "FORMATION=simple" in out
    assert "NON_JSON_RPC_STDOUT_LINES=0" in out
    assert "RESPONSE_IDS=[1, 2, 3]" in out
    assert "TOOL_NAMES=['chimera_deliberate', 'chimera_formations', 'chimera_models']" in out
    assert "DEPTH_TOOL=chimera_deliberate" in out
    assert "ANSWER_CHARS=" in out
    assert "PROBE OK" in out


def test_main_failure_exit_contract(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A polluted run prints the failing evidence and exits 1."""

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        lines, order, responses = _handshake_lines()
        return ["provider_cache_hit event=provider_cache_hit"] + lines, order, responses, "stderr-text"

    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main(["/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "NON_JSON_RPC_STDOUT_LINES=1" in out
    assert "PROBE FAIL" in out
    assert "non-JSON-RPC stdout lines" in out
    assert "=== STDERR (last 30 lines) ===" in out
    assert "stderr-text" in out


def test_main_depth_failure_exit_contract(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A handshake-clean but empty-answer run still fails (depth gate)."""

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "result": _TOOLS_LIST_RESULT}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "result": _EMPTY_ANSWER_RESULT}),
        ]
        order, responses = probe.collect_responses(lines)
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main(["/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "NON_JSON_RPC_STDOUT_LINES=0" in out  # stdout pure, but...
    assert "empty answer" in out
    assert "PROBE FAIL" in out


def test_read_deadline_minutes_not_seconds() -> None:
    """The depth call is network-bound — the deadline must allow minutes."""
    assert probe.READ_DEADLINE_S >= 120
    assert probe.DRAIN_DEADLINE_S >= 10


# --- formation override (DF-CHIMERA-0911-1) ---------------------------------- #
#
# The 0.2.4 leak was formation-dependent: formation=simple stayed clean while
# formation=speed's OpenRouter leg made LiteLLM print an ANSI "Provider List"
# banner onto stdout. The release gate must therefore be able to drive a
# NON-default formation — through a probe-owned token that cannot be confused
# with the child server's argv, or through an env var.

FORMATION_ENV = "CHIMERA_PROBE_FORMATION"


def test_default_formation_is_simple() -> None:
    assert probe.DEPTH_FORMATION == "simple"
    formation, cmd = probe.parse_formation(["/fake/venv/bin/chimera-mcp"], env={})
    assert formation == "simple"
    assert cmd == ["/fake/venv/bin/chimera-mcp"]


def test_formation_option_is_parsed_and_stripped_from_child_cmd() -> None:
    formation, cmd = probe.parse_formation(
        ["--formation=speed", "/fake/venv/bin/chimera-mcp", "chimera.yaml"], env={}
    )
    assert formation == "speed"
    assert cmd == ["/fake/venv/bin/chimera-mcp", "chimera.yaml"]


def test_formation_option_works_in_any_position() -> None:
    formation, cmd = probe.parse_formation(["chimera", "mcp", "--formation=auto"], env={})
    assert formation == "auto"
    assert cmd == ["chimera", "mcp"]


def test_formation_env_var_selects_formation() -> None:
    formation, cmd = probe.parse_formation(["/fake/venv/bin/chimera-mcp"], env={FORMATION_ENV: "speed"})
    assert formation == "speed"
    assert cmd == ["/fake/venv/bin/chimera-mcp"]


def test_formation_option_beats_env_var() -> None:
    formation, _ = probe.parse_formation(
        ["--formation=debate", "/fake/bin/chimera-mcp"], env={FORMATION_ENV: "speed"}
    )
    assert formation == "debate"


def test_formation_env_var_blank_falls_back_to_default() -> None:
    formation, _ = probe.parse_formation(["/fake/bin/chimera-mcp"], env={FORMATION_ENV: "  "})
    assert formation == "simple"


def test_empty_option_value_keeps_the_env_formation() -> None:
    formation, cmd = probe.parse_formation(
        ["--formation=", "/fake/bin/chimera-mcp"], env={FORMATION_ENV: "speed"}
    )
    assert formation == "speed"
    assert cmd == ["/fake/bin/chimera-mcp"]


def test_other_flags_and_paths_survive_untouched() -> None:
    """Only the probe-owned token is consumed — the child command is preserved."""
    argv = ["/fake/venv/bin/chimera-mcp", "/etc/chimera.yaml", "--verbose"]
    formation, cmd = probe.parse_formation(argv, env={})
    assert formation == "simple"
    assert cmd == argv


def test_formation_override_is_injected_into_the_tools_call() -> None:
    """The selected formation must reach the chimera_deliberate arguments."""
    call = [m for m in probe.build_messages("speed") if m.get("method") == "tools/call"][0]
    args = call["params"]["arguments"]
    assert args["formation"] == "speed"
    assert args["prompt"] == probe.DEPTH_PROMPT
    # Default stays simple, and the module-level constant stays in lockstep.
    default_call = [m for m in probe.build_messages() if m.get("method") == "tools/call"][0]
    assert default_call["params"]["arguments"] == probe.DEPTH_ARGUMENTS
    assert probe.depth_arguments() == probe.DEPTH_ARGUMENTS
    assert probe.depth_arguments("speed")["formation"] == "speed"


def test_main_threads_the_formation_to_the_driver(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict = {}

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        captured["cmd"] = cmd
        captured["formation"] = formation
        lines, order, responses = _handshake_lines()
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main(["--formation=speed", "/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 0
    assert captured["cmd"] == ["/fake/venv/bin/chimera-mcp"]
    assert captured["formation"] == "speed"
    assert "FORMATION=speed" in out
    assert "CHILD_CMD=/fake/venv/bin/chimera-mcp" in out


def test_main_env_override_threads_to_the_driver(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict = {}

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        captured["formation"] = formation
        lines, order, responses = _handshake_lines()
        return lines, order, responses, ""

    monkeypatch.setenv(FORMATION_ENV, "speed")
    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main(["/fake/venv/bin/chimera-mcp"])
    assert rc == 0
    assert captured["formation"] == "speed"


def test_bare_formation_flag_is_a_usage_error(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A space-separated ``--formation speed`` is ambiguous — refuse it.

    The token after ``--formation`` could equally be the child's config path,
    so the probe must not guess: exit 2 and never spawn anything.
    """

    def explode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("drive_stdio must not run on a usage error")

    monkeypatch.setattr(probe, "drive_stdio", explode)
    rc = probe.main(["--formation", "speed", "/fake/venv/bin/chimera-mcp"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "--formation=NAME" in err


def test_tool_inventory_constant_matches_mcp_server() -> None:
    """Keep the probe's inventory in lockstep with tests/test_mcp_stdio_purity.py."""
    purity = (REPO / "tests" / "test_mcp_stdio_purity.py").read_text(encoding="utf-8")
    match = None
    for line in purity.splitlines():
        if line.startswith("TOOL_NAMES = "):
            match = line
            break
    assert match is not None, "TOOL_NAMES constant vanished from test_mcp_stdio_purity.py"
    expected = eval(match.split("=", 1)[1].strip())  # noqa: S307 - trusted repo constant
    assert set(expected) == probe.TOOL_INVENTORY


# --- release-dependency contract -------------------------------------------- #
#
# The probe gates the WHEEL, so the wheel's dependency range is part of the
# contract: litellm 1.100.0 replaced its stderr ``logging.StreamHandler()``
# with ``LevelRoutingStreamHandler``, which routes every record below WARNING
# to sys.stdout on the first real completion() — exactly the lazy pollution
# this probe exists to catch. ``force_stderr`` only pins chimera's OWN sinks,
# so an uncapped litellm range re-introduces the bug for every fresh install.
# These tests keep the cap load-bearing (dropping it silently un-fixes the
# release) and keep the lock honest.

LITELLM_STDOUT_ROUTING_RELEASES = ("1.100.0", "1.100.1")


def _project_dependencies() -> list[str]:
    import tomllib

    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def _litellm_specifier() -> str:
    import re

    deps = [d for d in _project_dependencies() if d.split(";")[0].strip().startswith("litellm")]
    assert len(deps) == 1, f"expected exactly one litellm requirement, got {deps}"
    return re.sub(r"^litellm", "", deps[0].split(";")[0]).strip()


def test_litellm_pin_excludes_stdout_routing_releases() -> None:
    """pyproject must exclude the litellm releases that log INFO to stdout."""
    from packaging.specifiers import SpecifierSet

    spec = SpecifierSet(_litellm_specifier())
    for bad in LITELLM_STDOUT_ROUTING_RELEASES:
        assert bad not in spec, (
            f"litellm {bad} routes sub-WARNING records to sys.stdout "
            f"(LevelRoutingStreamHandler) — requirement {_litellm_specifier()!r} "
            "re-admits it and breaks MCP stdout purity on a real deliberation"
        )
    assert "1.99.0" in spec, "the last stderr-only litellm release must stay installable"


def test_locked_litellm_honours_the_pin() -> None:
    """uv.lock must resolve litellm inside the pyproject range."""
    import tomllib

    from packaging.specifiers import SpecifierSet

    lock = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))
    pkg = [p for p in lock["package"] if p["name"] == "litellm"]
    assert len(pkg) == 1, f"expected one litellm entry in uv.lock, got {len(pkg)}"
    locked = pkg[0]["version"]
    assert locked in SpecifierSet(_litellm_specifier()), (
        f"uv.lock pins litellm=={locked}, outside {_litellm_specifier()!r}"
    )
    assert locked not in LITELLM_STDOUT_ROUTING_RELEASES


# --- probe-owned config provisioning (DF-CHIMERA-0917-5) ----------------------
#
# CI run 35224141038 (tag v0.2.6): the release-verify MCP gate failed with
# ``PROBE FAIL: chimera_deliberate returned an empty answer`` +
# ``{"error": "unknown_formation", "formation": "simple", "available": []}``.
# Root cause: the probe spawned the child with the REPO ROOT as cwd and leaned
# on the repo-root ``chimera.yaml`` — which is untracked by design
# (DF-CHIMERA-0916B-4). A fresh CI checkout therefore had NO config, the child
# loaded empty defaults (``formations == {}``) and answered in ~1s with zero
# provider calls: the gate looked like it ran while testing nothing.
#
# The probe now provisions its own config (generated in a temp dir via the
# child's own sibling CLI), and remaps models whose provider has no resolved
# credential so a single-key environment (DEEPSEEK_API_KEY only) can still drive
# the formation for real. Every remap is printed — never silent.

CONFIG_OPTION = "--config="
CWD_OPTION = "--cwd="


def test_default_plan_generates_a_config_in_a_temp_dir(tmp_path: Path) -> None:
    """Neither --config nor --cwd: the probe owns the config it drives."""
    options, cmd = probe.parse_owned_options(["/fake/venv/bin/chimera-mcp"], env={})
    plan = probe.plan_config_provision(options, temp_dir=str(tmp_path))
    assert plan.source == "generated"
    assert plan.generate is True
    assert plan.cwd == str(tmp_path)
    assert plan.config_path == str(tmp_path / "chimera.yaml")
    assert cmd == ["/fake/venv/bin/chimera-mcp"]


def test_default_plan_never_falls_back_to_the_repo_root() -> None:
    """With no temp_dir the plan still provisions elsewhere — never REPO.

    A repo-root cwd is exactly the shape that failed in CI: the live config is
    untracked, so a checkout has none.
    """
    plan = probe.plan_config_provision(probe.ProbeOptions(formation="simple"))
    assert plan.source == "generated" and plan.generate is True
    assert plan.cwd != str(REPO)
    assert os.path.isdir(plan.cwd)
    assert os.path.basename(plan.cwd).startswith("chimera-probe-cfg-")
    assert plan.config_path == os.path.join(plan.cwd, "chimera.yaml")


def test_config_option_is_explicit_and_derives_cwd_from_the_file(tmp_path: Path) -> None:
    config = tmp_path / "site" / "chimera.yaml"
    config.parent.mkdir()
    config.write_text("formations: {}\n", encoding="utf-8")
    options, cmd = probe.parse_owned_options(
        [f"{CONFIG_OPTION}{config}", "/fake/venv/bin/chimera-mcp"], env={}
    )
    assert options.config == str(config)
    assert cmd == ["/fake/venv/bin/chimera-mcp"]  # probe-owned token stripped
    plan = probe.plan_config_provision(options)
    assert plan.source == "explicit"
    assert plan.generate is False
    assert plan.config_path == str(config)
    assert plan.cwd == str(config.parent)


def test_config_option_with_cwd_option_uses_that_cwd(tmp_path: Path) -> None:
    config = tmp_path / "cfg.yaml"
    config.write_text("formations: {}\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    options, _ = probe.parse_owned_options(
        [f"{CONFIG_OPTION}{config}", f"{CWD_OPTION}{elsewhere}"], env={}
    )
    plan = probe.plan_config_provision(options)
    assert plan.config_path == str(config)
    assert plan.cwd == str(elsewhere)


def test_cwd_option_means_the_directory_discovers_its_own_config(tmp_path: Path) -> None:
    """--cwd without --config: no provisioning, the child walks up from there."""
    options, cmd = probe.parse_owned_options(
        [f"{CWD_OPTION}{tmp_path}", "/fake/venv/bin/chimera-mcp"], env={}
    )
    plan = probe.plan_config_provision(options)
    assert plan.source == "cwd"
    assert plan.generate is False
    assert plan.config_path is None
    assert plan.cwd == str(tmp_path)
    assert cmd == ["/fake/venv/bin/chimera-mcp"]


def test_child_command_is_unchanged_by_the_new_owned_options() -> None:
    """--config/--cwd are probe-owned: they never reach the child argv."""
    argv = ["--config=/a.yaml", "--cwd=/b", "--formation=debate", "chimera", "mcp"]
    options, cmd = probe.parse_owned_options(argv, env={})
    assert cmd == ["chimera", "mcp"]
    assert (options.config, options.cwd, options.formation) == ("/a.yaml", "/b", "debate")


@pytest.mark.parametrize("option", ["--formation", "--config", "--cwd"])
def test_bare_probe_options_are_usage_errors(capsys, monkeypatch, option: str) -> None:  # type: ignore[no-untyped-def]
    """A space-separated ``--opt VALUE`` stays ambiguous — exit 2, spawn nothing."""

    def explode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("no provisioning/driving on a usage error")

    monkeypatch.setattr(probe, "provision_config", explode)
    monkeypatch.setattr(probe, "drive_stdio", explode)
    rc = probe.main([option, "/tmp", "/fake/venv/bin/chimera-mcp"])
    err = capsys.readouterr().err
    assert rc == 2
    assert f"{option}=" in err
    assert "usage error" in err


@pytest.mark.parametrize("option", [CONFIG_OPTION, CWD_OPTION])
def test_empty_probe_option_values_are_usage_errors(capsys, monkeypatch, option: str) -> None:  # type: ignore[no-untyped-def]
    """An empty path is unusable — the probe must not silently provision one."""

    def explode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("no provisioning/driving on a usage error")

    monkeypatch.setattr(probe, "provision_config", explode)
    monkeypatch.setattr(probe, "drive_stdio", explode)
    rc = probe.main([option, "/fake/venv/bin/chimera-mcp"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "needs a path" in err


def test_config_init_command_prefers_the_childs_sibling_cli(tmp_path: Path) -> None:
    """The generator is the child's own CLI — never a hand-written YAML template."""
    for name in ("chimera-mcp", "chimera"):
        entry = tmp_path / name
        entry.write_text("#!/bin/sh\n", encoding="utf-8")
        entry.chmod(0o755)
    assert probe.config_init_command([str(tmp_path / "chimera-mcp")]) == [
        str(tmp_path / "chimera"),
        "config",
        "init",
    ]


def test_config_init_command_falls_back_to_the_child_python(tmp_path: Path) -> None:
    (tmp_path / "chimera-mcp").write_text("#!/bin/sh\n", encoding="utf-8")
    command = probe.config_init_command(
        [str(tmp_path / "chimera-mcp")], child_python="/tmp/release-venv/bin/python"
    )
    assert command == ["/tmp/release-venv/bin/python", "-m", "chimera", "config", "init"]


def test_resolve_child_python_prefers_the_bin_sibling(tmp_path: Path) -> None:
    (tmp_path / "chimera-mcp").write_text("", encoding="utf-8")
    (tmp_path / "python").write_text("", encoding="utf-8")
    assert probe.resolve_child_python([str(tmp_path / "chimera-mcp")]) == str(tmp_path / "python")


def test_resolve_child_python_falls_back_to_this_interpreter(tmp_path: Path) -> None:
    (tmp_path / "chimera-mcp").write_text("", encoding="utf-8")
    assert probe.resolve_child_python([str(tmp_path / "chimera-mcp")]) == sys.executable


# --- provision_config: real generation through the child's CLI --------------- #

_FAKE_CLI = """#!{python}
import shutil, sys
from pathlib import Path

if sys.argv[1:3] == ["config", "init"]:
    shutil.copyfile({template!r}, Path.cwd() / "chimera.yaml")
    print("Created chimera.yaml")
    raise SystemExit(0)
print("unexpected args: %r" % (sys.argv[1:],), file=sys.stderr)
raise SystemExit(9)
"""


def _fake_child_bin(tmp_path: Path) -> Path:
    """A bin dir holding a stub ``chimera`` that copies the SHIPPED template.

    Using the repo's real ``chimera.yaml.example`` keeps the fixture honest:
    the remap contract is verified against the template that actually ships.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cli = bin_dir / "chimera"
    cli.write_text(
        _FAKE_CLI.format(python=sys.executable, template=str(REPO / "chimera.yaml.example")),
        encoding="utf-8",
    )
    cli.chmod(0o755)
    (bin_dir / "chimera-mcp").write_text("#!/bin/sh\n", encoding="utf-8")
    return bin_dir


def test_provision_config_generates_remaps_and_writes_the_config(tmp_path: Path) -> None:
    """End-to-end offline: generate → remap → write, with the evidence returned."""
    bin_dir = _fake_child_bin(tmp_path)
    child_cmd = [str(bin_dir / "chimera-mcp")]
    plan = probe.plan_config_provision(
        probe.ProbeOptions(formation="speed"), temp_dir=str(tmp_path / "cfg")
    )
    result = probe.provision_config(
        plan,
        child_cmd=child_cmd,
        formation="speed",
        env={"PATH": os.environ.get("PATH", "")},
        credential_env={"DEEPSEEK_API_KEY": "test-deepseek"},
    )
    assert result.source == "generated"
    assert result.config_path == plan.config_path
    assert os.path.isfile(result.config_path)
    assert os.path.isdir(plan.cwd), "the config dir is kept while the child may still run"
    assert [r.model for r in result.remaps] == ["openrouter/qwen/qwen3-coder"]
    remap = result.remaps[0]
    assert remap.replacement == "deepseek/deepseek-v4-flash"
    assert remap.env_var == "OPENROUTER_API_KEY"
    assert remap.role == "speed.worker_models[1]"
    # The written config really carries the substitution...
    written = probe.load_config_document(result.config_path)
    assert written["formations"]["speed"]["worker_models"] == [
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-flash",
    ]
    # ...and only the reference moved: the catalog entry itself is untouched.
    assert written["models"]["openrouter/qwen/qwen3-coder"]["provider"] == "openrouter"


def test_provision_config_leaves_a_credentialed_formation_untouched(tmp_path: Path) -> None:
    """With the key present nothing is substituted — the leak leg stays exercised."""
    bin_dir = _fake_child_bin(tmp_path)
    plan = probe.plan_config_provision(
        probe.ProbeOptions(formation="speed"), temp_dir=str(tmp_path / "cfg")
    )
    result = probe.provision_config(
        plan,
        child_cmd=[str(bin_dir / "chimera-mcp")],
        formation="speed",
        env={},
        credential_env={
            "DEEPSEEK_API_KEY": "test-deepseek",
            "OPENROUTER_API_KEY": "test-openrouter",
        },
    )
    assert result.remaps == ()
    written = probe.load_config_document(result.config_path)
    assert written["formations"]["speed"]["worker_models"] == [
        "deepseek/deepseek-v4-flash",
        "openrouter/qwen/qwen3-coder",
    ]


def test_provision_config_fails_loudly_when_generation_fails(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cli = bin_dir / "chimera"
    cli.write_text("#!/bin/sh\necho 'boom' >&2\nexit 3\n", encoding="utf-8")
    cli.chmod(0o755)
    plan = probe.plan_config_provision(
        probe.ProbeOptions(formation="simple"), temp_dir=str(tmp_path / "cfg")
    )
    with pytest.raises(probe.ProbeSetupError, match="failed"):
        probe.provision_config(
            plan, child_cmd=[str(bin_dir / "chimera-mcp")], formation="simple", env={}
        )


def test_provision_config_rejects_a_missing_explicit_config(tmp_path: Path) -> None:
    plan = probe.plan_config_provision(
        probe.ProbeOptions(formation="simple", config=str(tmp_path / "nope.yaml"))
    )
    with pytest.raises(probe.ProbeSetupError, match="does not exist"):
        probe.provision_config(plan, child_cmd=["/fake/bin/chimera-mcp"], formation="simple", env={})


def test_provision_config_rejects_a_missing_cwd(tmp_path: Path) -> None:
    plan = probe.plan_config_provision(
        probe.ProbeOptions(formation="simple", cwd=str(tmp_path / "nope"))
    )
    with pytest.raises(probe.ProbeSetupError, match="not a directory"):
        probe.provision_config(plan, child_cmd=["/fake/bin/chimera-mcp"], formation="simple", env={})


def test_yaml_bridge_used_when_this_interpreter_has_no_pyyaml(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The CI runner's python may have no PyYAML — the child's interpreter has it.

    A hand-rolled subset parser is not an option (it silently truncates a
    document on syntax it does not know), so the parse/serialise fall back to
    ``python_exe``. Verified for real against the shipped template.
    """
    monkeypatch.setattr(probe, "_yaml_available", lambda: False)
    source = REPO / "chimera.yaml.example"
    document = probe.load_config_document(str(source), python_exe=sys.executable)
    assert "speed" in document["formations"]
    assert document["formations"]["speed"]["worker_models"][1] == "openrouter/qwen/qwen3-coder"

    target = tmp_path / "round-trip.yaml"
    probe.write_config_document(str(target), document, python_exe=sys.executable)
    reloaded = probe.load_config_document(str(target), python_exe=sys.executable)
    assert reloaded == document


def test_yaml_load_without_pyyaml_or_interpreter_fails_loudly(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(probe, "_yaml_available", lambda: False)
    config = tmp_path / "chimera.yaml"
    config.write_text("formations: {}\n", encoding="utf-8")
    with pytest.raises(probe.ProbeSetupError, match="PyYAML is not importable"):
        probe.load_config_document(str(config))


# --- formation credential remap (DF-CHIMERA-0917-5) --------------------------- #
#
# The generated 'speed' formation uses openrouter/qwen/qwen3-coder, which needs
# OPENROUTER_API_KEY — a repo secret that does not exist. The gate must not
# depend on it: uncredentialed models are remapped onto a credentialed deepseek
# model and every substitution is PRINTED (a silent substitution would weaken
# the gate's own coverage claim). When the key IS set, nothing is remapped, so
# the 0.2.3 OpenRouter stdout-leak leg stays exercised.

_QWEN = "openrouter/qwen/qwen3-coder"
_FLASH = "deepseek/deepseek-v4-flash"

_REMAP_DOC: dict = {
    "api_keys": {"deepseek": "${DEEPSEEK_API_KEY}", "openrouter": "${OPENROUTER_API_KEY}"},
    "defaults": {"default_worker": _QWEN, "default_aggregator": _FLASH},
    "providers": {
        "deepseek": {"base_url": "https://api.deepseek.com/v1"},
        "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
    },
    "models": {
        _FLASH: {"provider": "deepseek"},
        _QWEN: {"provider": "openrouter"},
    },
    "formations": {
        "speed": {
            "workers": 2,
            "worker_models": [_FLASH, _QWEN],
            "aggregator": _FLASH,
        },
        "audit": {"workers": 2, "aggregator": "default", "audit": _QWEN},
        "auto": {"mode": "auto"},
        "defaults-only": {"workers": 2, "aggregator": _FLASH},
    },
}


def test_remap_substitutes_an_uncredentialed_model_and_reports_it() -> None:
    remapped, remaps = probe.remap_uncredentialed_models(
        _REMAP_DOC, {"DEEPSEEK_API_KEY": "d"}, formation="speed"
    )
    assert len(remaps) == 1
    remap = remaps[0]
    assert remap.model == _QWEN
    assert remap.replacement == _FLASH
    assert remap.env_var == "OPENROUTER_API_KEY"
    assert remap.role == "speed.worker_models[1]"
    assert remapped["formations"]["speed"]["worker_models"] == [_FLASH, _FLASH]


def test_remap_is_never_silent_evidence_line_shape() -> None:
    _, remaps = probe.remap_uncredentialed_models(
        _REMAP_DOC, {"DEEPSEEK_API_KEY": "d"}, formation="speed"
    )
    assert remaps[0].evidence_line() == (
        "FORMATION_MODEL_REMAP=openrouter/qwen/qwen3-coder -> deepseek/deepseek-v4-flash "
        "(OPENROUTER_API_KEY unset; speed.worker_models[1])"
    )


def test_remap_leaves_credentialed_models_untouched() -> None:
    remapped, remaps = probe.remap_uncredentialed_models(
        _REMAP_DOC,
        {"DEEPSEEK_API_KEY": "d", "OPENROUTER_API_KEY": "o"},
        formation="speed",
    )
    assert remaps == []
    assert remapped == _REMAP_DOC
    assert remapped["formations"]["speed"]["worker_models"][1] == _QWEN


def test_remap_does_not_mutate_the_input_document() -> None:
    before = json.dumps(_REMAP_DOC, sort_keys=True)
    probe.remap_uncredentialed_models(_REMAP_DOC, {"DEEPSEEK_API_KEY": "d"}, formation="speed")
    assert json.dumps(_REMAP_DOC, sort_keys=True) == before


def test_remap_is_scoped_to_the_driven_formation() -> None:
    """Driving another formation must not rewrite an unrelated preset's models."""
    remapped, remaps = probe.remap_uncredentialed_models(
        _REMAP_DOC, {"DEEPSEEK_API_KEY": "d"}, formation="auto"
    )
    assert remaps == []  # auto has no explicit models: the dispatcher picks
    assert remapped["formations"]["audit"]["audit"] == _QWEN
    assert remapped["formations"]["speed"]["worker_models"] == [_FLASH, _QWEN]


def test_remap_handles_the_audit_preset_alias_and_explicit_model() -> None:
    remapped, remaps = probe.remap_uncredentialed_models(
        _REMAP_DOC, {"DEEPSEEK_API_KEY": "d"}, formation="audit"
    )
    # The explicit audit model AND the preset's implicit worker slots (which
    # resolve to an uncredentialed defaults.default_worker) are both handled.
    assert {r.role for r in remaps} == {"audit.audit", "audit.workers(2)"}
    assert remapped["formations"]["audit"]["audit"] == _FLASH
    assert remapped["formations"]["audit"]["worker_models"] == [_FLASH, _FLASH]
    # 'aggregator: default' resolves to a credentialed default — untouched.
    assert remapped["formations"]["audit"]["aggregator"] == "default"


def test_remap_covers_implicit_default_workers() -> None:
    """A preset with only ``workers: N`` uses defaults.default_worker."""
    remapped, remaps = probe.remap_uncredentialed_models(
        _REMAP_DOC, {"DEEPSEEK_API_KEY": "d"}, formation="defaults-only"
    )
    assert [r.model for r in remaps] == [_QWEN]
    assert remaps[0].role == "defaults-only.workers(2)"
    assert remapped["formations"]["defaults-only"]["worker_models"] == [_FLASH, _FLASH]


def test_remap_is_skipped_when_the_fallback_is_also_uncredentialed() -> None:
    """No credential at all: substitute nothing rather than steer at another dead end."""
    remapped, remaps = probe.remap_uncredentialed_models(_REMAP_DOC, {}, formation="speed")
    assert remaps == []
    assert remapped["formations"]["speed"]["worker_models"] == [_FLASH, _QWEN]


def test_remap_unknown_formation_is_a_no_op() -> None:
    remapped, remaps = probe.remap_uncredentialed_models(
        _REMAP_DOC, {"DEEPSEEK_API_KEY": "d"}, formation="nope"
    )
    assert remaps == [] and remapped == _REMAP_DOC


def test_credential_resolution_matches_the_config_loader_rules() -> None:
    """Mirror of chimera.config.provider_credential_resolved over the document."""
    doc = {
        "api_keys": {"deepseek": "${DEEPSEEK_API_KEY}"},
        "providers": {
            "openrouter": {"base_url": "x", "api_key_env": "OR_ALT_KEY"},
            "zai": {"base_url": "x", "api_key": "${ZAI_API_KEY}"},
            "google": {"base_url": "x", "api_key": "literal-key"},
        },
        "models": {_FLASH: {"provider": "deepseek"}, "m": {"provider": "nope"}},
    }
    assert probe.provider_credential_resolved(doc, "deepseek", {"DEEPSEEK_API_KEY": "d"}) is True
    assert probe.provider_credential_resolved(doc, "deepseek", {"DEEPSEEK_API_KEY": "  "}) is False
    assert probe.provider_credential_resolved(doc, "openrouter", {"OR_ALT_KEY": "k"}) is True
    assert probe.provider_credential_resolved(doc, "openrouter", {}) is False
    assert probe.provider_credential_resolved(doc, "zai", {"ZAI_API_KEY": "z"}) is True
    assert probe.provider_credential_resolved(doc, "google", {}) is True  # literal key
    assert probe.provider_credential_resolved(doc, "unknown", {"X": "1"}) is False
    assert probe.provider_credential_resolved(doc, None, {}) is False


def test_provider_credential_env_var_names_the_missing_key() -> None:
    doc = _REMAP_DOC | {"providers": {"openrouter": {"base_url": "x", "api_key_env": "OR_ALT"}}}
    assert probe.provider_credential_env_var(doc, "openrouter") == "OR_ALT"
    assert probe.provider_credential_env_var(_REMAP_DOC, "openrouter") == "OPENROUTER_API_KEY"
    assert probe.provider_credential_env_var(_REMAP_DOC, "deepseek") == "DEEPSEEK_API_KEY"
    assert probe.provider_credential_env_var(_REMAP_DOC, "missing") is None


def test_effective_credential_env_falls_back_to_the_hermes_dotenv(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A box whose keys live only in ~/.hermes/.env is not read as uncredentialed."""
    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    (home / ".hermes" / ".env").write_text("OPENROUTER_API_KEY=or-key\n# c\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    env = probe.effective_credential_env({"DEEPSEEK_API_KEY": "d"})
    assert env["OPENROUTER_API_KEY"] == "or-key"
    assert env["DEEPSEEK_API_KEY"] == "d"


# --- driver evidence contract for provisioning -------------------------------- #


def test_main_provisions_its_own_config_and_reports_it(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict = {}

    def fake_provision(plan, *, child_cmd, formation, env, credential_env=None):  # noqa: ANN001
        captured["plan"] = plan
        captured["formation"] = formation
        captured["init_env"] = env
        return probe.ProvisionResult(
            config_path="/tmp/gen/chimera.yaml",
            cwd="/tmp/gen",
            source="generated",
            remaps=(
                probe.Remap(
                    model=_QWEN,
                    replacement=_FLASH,
                    env_var="OPENROUTER_API_KEY",
                    role="speed.worker_models[1]",
                ),
            ),
        )

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        captured["env"] = env
        captured["cwd"] = cwd
        lines, order, responses = _handshake_lines()
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "provision_config", fake_provision)
    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    # The live repo config must NOT leak into the child: CHIMERA_CONFIG is
    # pinned to the provisioned file.
    monkeypatch.setenv("CHIMERA_CONFIG", "/home/kara/chimera-v2/chimera.yaml")
    rc = probe.main(["--formation=speed", "/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 0
    assert captured["plan"].source == "generated"
    assert "CHIMERA_CONFIG" not in captured["init_env"]
    assert captured["env"]["CHIMERA_CONFIG"] == "/tmp/gen/chimera.yaml"
    assert captured["cwd"] == "/tmp/gen"
    assert "CONFIG_SOURCE=generated" in out
    assert "CONFIG_PATH=/tmp/gen/chimera.yaml" in out
    assert "PROBE_CWD=/tmp/gen" in out
    assert "MODEL_REMAPS_TOTAL=1" in out
    assert (
        "FORMATION_MODEL_REMAP=openrouter/qwen/qwen3-coder -> deepseek/deepseek-v4-flash "
        "(OPENROUTER_API_KEY unset; speed.worker_models[1])" in out
    )
    assert "PROBE OK" in out


def test_main_cwd_mode_clears_chimera_config_for_the_child(capsys, monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """--cwd must let the child discover ITS directory's config, not the parent's."""

    def fake_provision(plan, *, child_cmd, formation, env, credential_env=None):  # noqa: ANN001
        return probe.ProvisionResult(None, str(tmp_path), "cwd", ())

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        fake_drive.env = env  # type: ignore[attr-defined]
        lines, order, responses = _handshake_lines()
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "provision_config", fake_provision)
    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    monkeypatch.setenv("CHIMERA_CONFIG", "/home/kara/chimera-v2/chimera.yaml")
    rc = probe.main([f"{CWD_OPTION}{tmp_path}", "/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "CHIMERA_CONFIG" not in fake_drive.env  # type: ignore[attr-defined]
    assert "CONFIG_SOURCE=cwd" in out
    assert "CONFIG_PATH=(unset: child discovers its own config from cwd)" in out
    assert "MODEL_REMAPS_TOTAL=0" in out


def test_main_setup_failure_exits_2_without_driving(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An unprovisionable config is a setup error (exit 2), not a purity failure."""

    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise probe.ProbeSetupError("`chimera config init` failed (rc=1): nope")

    def explode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("the child must not be spawned when setup failed")

    monkeypatch.setattr(probe, "provision_config", boom)
    monkeypatch.setattr(probe, "drive_stdio", explode)
    rc = probe.main(["/fake/venv/bin/chimera-mcp"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "PROBE SETUP FAIL" in err
    assert "chimera config init" in err


# --- expected-version gate (DF-CHIMERA-V2-9) --------------------------------- #
#
# The initialize handshake must report the PACKAGE version. Pre-0.2.6 the MCP
# server advertised the mcp SDK's own version (1.28.1) for a 0.2.6 chimera, so
# a client could not tell which build it had reached. The probe always prints
# SERVER_VERSION=<serverInfo.version> and, with --expected-version=X, exits 1
# naming the mismatch. The option follows the same single-token rule as
# --formation/--config/--cwd (a bare '--expected-version X' pair is ambiguous
# with the child's argv: exit 2) and is stripped from the child command.

EXPECTED_VERSION_OPTION = "--expected-version="


def _server_info(version: str | None) -> dict:
    """A serverInfo block, with or without the version field."""
    info: dict = {"name": "chimera"}
    if version is not None:
        info["version"] = version
    return info


def _handshake_lines_with_version(
    version: str | None,
) -> tuple[list[str], list[int], dict[int, dict]]:
    """``_handshake_lines()`` with an explicit (or absent) handshake version."""
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": _server_info(version)}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "result": _TOOLS_LIST_RESULT}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "result": _OK_RESULT}),
    ]
    order, responses = probe.collect_responses(lines)
    return lines, order, responses


def test_server_info_version_reads_the_handshake_version() -> None:
    assert probe.server_info_version({"serverInfo": {"name": "chimera", "version": "0.2.6"}}) == "0.2.6"
    assert probe.server_info_version({"serverInfo": {"version": " 0.2.6 "}}) == "0.2.6"


def test_server_info_version_is_none_when_absent() -> None:
    """No response / no version field / blank version: unknown, not a guess."""
    assert probe.server_info_version(None) is None
    assert probe.server_info_version({}) is None
    assert probe.server_info_version({"serverInfo": {"name": "chimera"}}) is None
    assert probe.server_info_version({"serverInfo": {"version": "  "}}) is None
    assert probe.server_info_version({"serverInfo": "chimera"}) is None
    assert probe.server_info_version({"serverInfo": {"version": 3}}) is None


def test_server_version_mismatch_line_shape() -> None:
    assert probe.server_version_mismatch("0.2.6", "0.2.6") is None
    assert probe.server_version_mismatch(None, "0.2.6") is None  # nothing to compare
    assert probe.server_version_mismatch("0.2.6", None) == (
        "SERVER_VERSION_MISMATCH=expected:0.2.6 actual:(missing)"
    )
    assert probe.server_version_mismatch("9.9.9", "1.28.1") == (
        "SERVER_VERSION_MISMATCH=expected:9.9.9 actual:1.28.1"
    )


def test_expected_version_option_is_parsed_and_stripped_from_the_child_cmd() -> None:
    options, cmd = probe.parse_owned_options(
        [f"{EXPECTED_VERSION_OPTION}0.2.6", "/fake/venv/bin/chimera-mcp"], env={}
    )
    assert options.expected_version == "0.2.6"
    assert cmd == ["/fake/venv/bin/chimera-mcp"]


def test_expected_version_defaults_to_none() -> None:
    """Without the option the probe compares nothing — it only reports."""
    options, cmd = probe.parse_owned_options(["/fake/venv/bin/chimera-mcp"], env={})
    assert options.expected_version is None
    assert cmd == ["/fake/venv/bin/chimera-mcp"]


def test_expected_version_option_works_alongside_the_other_owned_options() -> None:
    argv = [
        "--formation=debate",
        f"{EXPECTED_VERSION_OPTION}0.2.6",
        "--cwd=/tmp/site-cfg",
        "chimera",
        "mcp",
    ]
    options, cmd = probe.parse_owned_options(argv, env={})
    assert cmd == ["chimera", "mcp"]
    assert (options.formation, options.expected_version, options.cwd) == (
        "debate",
        "0.2.6",
        "/tmp/site-cfg",
    )


def test_bare_expected_version_flag_is_a_usage_error(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``--expected-version 0.2.6`` is ambiguous — exit 2, spawn nothing."""

    def explode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("no provisioning/driving on a usage error")

    monkeypatch.setattr(probe, "provision_config", explode)
    monkeypatch.setattr(probe, "drive_stdio", explode)
    rc = probe.main(["--expected-version", "0.2.6", "/fake/venv/bin/chimera-mcp"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "--expected-version=VER" in err


def test_empty_expected_version_value_is_a_usage_error(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An empty version cannot be compared — refuse it rather than skip the gate."""

    def explode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("no provisioning/driving on a usage error")

    monkeypatch.setattr(probe, "provision_config", explode)
    monkeypatch.setattr(probe, "drive_stdio", explode)
    rc = probe.main([EXPECTED_VERSION_OPTION, "/fake/venv/bin/chimera-mcp"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "needs a version" in err


def test_main_always_prints_the_handshake_version(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """SERVER_VERSION=<actual> is unconditional evidence, not gated on the flag."""

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        lines, order, responses = _handshake_lines_with_version("0.2.6")
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main(["/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SERVER_VERSION=0.2.6" in out
    assert "SERVER_VERSION_MISMATCH" not in out


def test_main_reports_a_missing_version_as_missing(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A handshake with no version field is reported as (missing), never as OK."""

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        lines, order, responses = _handshake_lines_with_version(None)
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main([EXPECTED_VERSION_OPTION + "0.2.6", "/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "SERVER_VERSION=(missing)" in out
    assert "SERVER_VERSION_MISMATCH=expected:0.2.6 actual:(missing)" in out


def test_main_expected_version_match_is_green(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A matching version keeps the run green and prints no mismatch line."""

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        lines, order, responses = _handshake_lines_with_version("0.2.6")
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main([EXPECTED_VERSION_OPTION + "0.2.6", "/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SERVER_VERSION=0.2.6" in out
    assert "SERVER_VERSION_MISMATCH" not in out
    assert "PROBE OK" in out


def test_main_expected_version_mismatch_exits_1_and_names_it(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The release gate: a build advertising another version fails the probe.

    This is the exact pre-0.2.6 shape — a 0.2.6 build whose handshake said
    ``1.28.1`` (the mcp SDK's version).
    """

    def fake_drive(cmd, env, cwd, formation):  # noqa: ANN001
        lines, order, responses = _handshake_lines_with_version("1.28.1")
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main([EXPECTED_VERSION_OPTION + "0.2.6", "/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "SERVER_VERSION=1.28.1" in out
    assert "SERVER_VERSION_MISMATCH=expected:0.2.6 actual:1.28.1" in out
    assert "PROBE FAIL" in out
    assert "version mismatch" in out

