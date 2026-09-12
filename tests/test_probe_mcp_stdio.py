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
import sys
from pathlib import Path
from types import ModuleType

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

    def fake_drive(cmd, env, cwd):  # noqa: ANN001
        captured["cmd"] = cmd
        lines, order, responses = _handshake_lines()
        return lines, order, responses, ""

    monkeypatch.setattr(probe, "drive_stdio", fake_drive)
    rc = probe.main(["/fake/venv/bin/chimera-mcp"])
    out = capsys.readouterr().out
    assert rc == 0
    assert captured["cmd"] == ["/fake/venv/bin/chimera-mcp"]
    assert "NON_JSON_RPC_STDOUT_LINES=0" in out
    assert "RESPONSE_IDS=[1, 2, 3]" in out
    assert "TOOL_NAMES=['chimera_deliberate', 'chimera_formations', 'chimera_models']" in out
    assert "DEPTH_TOOL=chimera_deliberate" in out
    assert "ANSWER_CHARS=" in out
    assert "PROBE OK" in out


def test_main_failure_exit_contract(capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A polluted run prints the failing evidence and exits 1."""

    def fake_drive(cmd, env, cwd):  # noqa: ANN001
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

    def fake_drive(cmd, env, cwd):  # noqa: ANN001
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
