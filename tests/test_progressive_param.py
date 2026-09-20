"""CH-GAP-058 — the declared ``progressive`` parameter must actually take effect.

Live 2026-09-19: ``chimera_deliberate`` advertises ``progressive`` in its served
schema and forwards it into :class:`DeliberationOverrides`, but
``_apply_progressive`` only ever read ``wait_messages``:

* ``progressive=True`` alone → every stage stayed ``progressive=False``, no
  warning, no trace note (a silent no-op for an explicit caller request), and
* ``wait_messages`` alone → worker stages were switched to ``progressive=True``
  even though the caller never asked for it.

The shipped semantics (see ``_apply_progressive``) honor BOTH inputs, and this
module pins all three arms plus the served schema description:

(a) ``progressive=True`` with no ``wait_messages`` → the worker stages the DAG
    runner actually executes carry ``progressive=True``;
(b) the description ``tools/list`` serves for ``chimera_deliberate`` states the
    shipped behaviour (both inputs, and what each one does alone);
(c) ``progressive=False`` (the default) still yields non-progressive stages, and
    a non-progressive re-run is byte-identical to the pre-fix behaviour;
(d) the pre-existing ``wait_messages``-only path (progressive implied, list and
    trigger applied to every worker) is unchanged.

Everything runs in-process against ``FakeGateway`` — no provider, no network.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from chimera.engine import Engine
from chimera.mcp.server import build_server
from tests.conftest import FakeGateway, dispatch_json, resp

pytest.importorskip("mcp")


# --------------------------------------------------------------------------- #
# Harness: capture the Stage objects the DAG runner was handed
# --------------------------------------------------------------------------- #


def _make_engine(config):  # type: ignore[no-untyped-def]
    """Engine behind a FakeGateway; the payload can be swapped per test."""

    state: dict[str, str] = {"payload": dispatch_json()}

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # dispatcher
            return resp(state["payload"], model, tok_in=120, tok_out=180)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator
            return resp(f"[FINAL MERGED ANSWER from {model}]", model, tok_in=60, tok_out=90)
        return resp(f"[worker output {model}]", model, tok_in=25, tok_out=35)

    gw = FakeGateway(responder)
    return Engine(config, gw), gw, state


def _capture_stages(config, monkeypatch: pytest.MonkeyPatch, payload: str | None = None):  # type: ignore[no-untyped-def]
    """Return a list that the engine appends the executed Stage objects to.

    ``_run_dag`` is swapped for a probe that snapshots
    ``dispatch.formation.stages`` — the very objects the runner would execute —
    so the assertions read the post-override state of the exact stages that
    reach ``_call_stage``, without mocking the progressive logic under test.
    """
    seen: list[list] = []
    real_run_dag = Engine._run_dag

    async def probe(self, dispatch, *args, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(copy.deepcopy(dispatch.formation.stages))
        return await real_run_dag(self, dispatch, *args, **kwargs)

    monkeypatch.setattr(Engine, "_run_dag", probe)
    engine, gw, state = _make_engine(config)
    if payload is not None:
        state["payload"] = payload
    return engine, gw, seen


def _stage(stages: list, stage_id: str):  # type: ignore[no-untyped-def]
    return next(s for s in stages if s.id == stage_id)


# --------------------------------------------------------------------------- #
# (a) progressive=True with NO wait_messages now reaches the worker stages
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_progressive_true_without_wait_messages_sets_worker_stages(
    config, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    """C1: the explicit flag alone must set progressive on the worker stages.

    Pre-CH-GAP-058 this test fails with ``progressive is False`` on both worker
    stages (assertion rewritten textually so a revert fails loudly, not with an
    AttributeError).
    """
    from chimera.config import DeliberationOverrides

    engine, gw, seen = _capture_stages(config, monkeypatch)

    result = await engine.deliberate(
        "design a thing", "auto",
        overrides=DeliberationOverrides(progressive=True),
    )

    assert result.answer is not None
    assert len(seen) == 1, "the DAG runner was never handed a formation"
    stages = seen[0]
    workers = [s for s in stages if s.kind == "worker"]
    assert workers, "the fixture DAG must contain worker stages"
    for stage in workers:
        assert stage.progressive is True, (
            f"worker {stage.id!r} is progressive={stage.progressive!r} — the "
            "caller's progressive=True was dropped"
        )
        assert stage.wait_messages == [], (
            f"worker {stage.id!r} must not gain wait_messages from the flag alone"
        )
    # Non-worker stages are never touched.
    for stage in stages:
        if stage.kind != "worker":
            assert stage.progressive is False


@pytest.mark.asyncio
async def test_progressive_true_alone_does_not_change_worker_calls(
    config, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    """progressive without wait_messages adds no provider call — documented.

    The gate at the call site (``if stage.progressive and stage.wait_messages``)
    has nothing to feed, so the stage prompt is sent exactly once, as in a
    non-progressive run. The flag is therefore real (honored on the stages) but
    wire-neutral on its own, and the schema description says so.
    """
    from chimera.config import DeliberationOverrides

    engine_a, gw_a, _ = _capture_stages(config, monkeypatch)
    await engine_a.deliberate(
        "design a thing", "auto",
        overrides=DeliberationOverrides(progressive=True),
    )
    engine_b, gw_b, _ = _capture_stages(config, monkeypatch)
    await engine_b.deliberate("design a thing", "auto", overrides=DeliberationOverrides())

    def shape(calls):  # type: ignore[no-untyped-def]
        return [(m, json.dumps(msgs, sort_keys=True)) for m, msgs, _ in calls]

    assert shape(gw_a.calls) == shape(gw_b.calls), (
        "progressive=True alone changed the provider call sequence"
    )


@pytest.mark.asyncio
async def test_progressive_true_overrides_a_non_progressive_custom_dag(
    config, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    """A custom DAG that declares progressive=False is still flipped ON.

    ``_apply_progressive`` runs after the DAG is built, exactly like the
    per-stage model overrides, so it applies to auto, preset and custom DAGs.
    The DAG is dispatched as the fixed structure (``_dispatch_custom`` assigns
    the client's DAG to the result), so the capture sees the client's stages.
    """
    from chimera.config import DeliberationOverrides

    engine, _, seen = _capture_stages(config, monkeypatch)
    dag = {
        "stages": [
            {"id": "w1", "kind": "worker", "model": "deepseek/deepseek-chat",
             "depends_on": [], "progressive": False},
            {"id": "agg", "kind": "aggregator", "model": "zai-coding-plan/glm-5.2",
             "depends_on": ["w1"]},
        ],
        "edges": [["w1", "agg"]],
    }
    result = await engine.deliberate(
        "test", "auto", dag=dag, allow_custom_dag=True,
        overrides=DeliberationOverrides(progressive=True),
    )

    assert result.answer is not None
    worker = _stage(seen[0], "w1")
    assert worker.progressive is True, "the client's progressive=False survived the flag"
    aggregator = _stage(seen[0], "agg")
    assert aggregator.progressive is False, "a non-worker stage was flipped"


# --------------------------------------------------------------------------- #
# (b) the served schema description matches the shipped behavior
# --------------------------------------------------------------------------- #


def test_served_description_states_the_shipped_progressive_behavior(config) -> None:  # type: ignore[no-untyped-def]
    """C2: ``tools/list``'s description must describe what ships.

    The docstring IS the schema description (mcp 1.28.1 ``Tool.from_function``
    uses ``fn.__doc__``), so read it off the built server exactly as a client
    does rather than inspecting the source text. Whitespace is collapsed before
    matching: the served string keeps the docstring's continuation-line
    indentation, which is formatting, not contract.
    """
    server = build_server(config=config, engine=object())
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    description = " ".join(tools["chimera_deliberate"].description.split())

    # The two inputs are named as inputs, not as one merged feature.
    assert (
        "``progressive=True`` turns progressive prompting ON for every worker "
        "stage of the run (inherited stages included), whether or not "
        "``wait_messages`` is given; it never turns it off."
    ) in description
    # wait_messages is stated to be sufficient on its own (pre-existing behavior).
    assert (
        "``wait_messages`` feeds those context messages one at a time and is "
        "itself sufficient to enable progressive prompting"
    ) in description
    # progressive alone is stated to be wire-neutral, which is what the engine does.
    assert (
        "so ``progressive`` alone adds no extra provider calls: the stage prompt "
        "is then sent once, exactly as in a non-progressive run"
    ) in description
    # trigger's gate is stated.
    assert (
        "``trigger`` overrides the final message that asks for the real output "
        "and is only used when ``wait_messages`` is set."
    ) in description


def test_deliberate_tool_still_declares_all_progressive_parameters(config) -> None:  # type: ignore[no-untyped-def]
    """The schema keeps advertising the parameters the engine now honors."""
    server = build_server(config=config, engine=object())
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    properties = tools["chimera_deliberate"].parameters["properties"]
    for name in ("progressive", "wait_messages", "trigger"):
        assert name in properties, f"{name} vanished from the served schema"
    assert properties["progressive"]["default"] is False


# --------------------------------------------------------------------------- #
# (c) default stays non-progressive — no regression
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_default_overrides_leave_stages_non_progressive(
    config, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    """C3: ``progressive=False`` (default) must not turn progressive on."""
    from chimera.config import DeliberationOverrides

    engine, gw, seen = _capture_stages(config, monkeypatch)
    await engine.deliberate(
        "design a thing", "auto", overrides=DeliberationOverrides(),
    )
    stages = seen[0]
    assert stages, "no stages captured"
    for stage in stages:
        assert stage.progressive is False, f"{stage.id} became progressive by default"
        assert stage.wait_messages == []
        assert stage.trigger == ""


@pytest.mark.asyncio
async def test_progressive_false_is_wire_identical_to_a_bare_run(
    config, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A default override run and a no-override run make the same calls.

    The flag's default path must stay untouched by the fix — same models, same
    temperatures, same message shapes.
    """
    from chimera.config import DeliberationOverrides

    engine_a, gw_a, _ = _capture_stages(config, monkeypatch)
    await engine_a.deliberate("design a thing", "auto", overrides=DeliberationOverrides())

    engine_b, gw_b, _ = _capture_stages(config, monkeypatch)
    await engine_b.deliberate("design a thing", "auto")

    def shape(calls):  # type: ignore[no-untyped-def]
        return [(m, json.dumps(msgs, sort_keys=True)) for m, msgs, _ in calls]

    assert shape(gw_a.calls) == shape(gw_b.calls)
    assert [c[2].get("temperature") for c in gw_a.calls] == [
        c[2].get("temperature") for c in gw_b.calls
    ]


# --------------------------------------------------------------------------- #
# (d) the wait_messages-only path is unchanged
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_wait_messages_alone_still_enables_progressive(
    config, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    """Pre-existing behavior: wait_messages implies progressive + arms the feed."""
    from chimera.config import DeliberationOverrides

    engine, gw, seen = _capture_stages(config, monkeypatch)
    await engine.deliberate(
        "test", "auto",
        overrides=DeliberationOverrides(
            wait_messages=["OVERRIDE MSG 1", "OVERRIDE MSG 2"],
            trigger="OVERRIDE TRIGGER: answer now",
        ),
    )
    for stage in seen[0]:
        if stage.kind == "worker":
            assert stage.progressive is True
            assert stage.wait_messages == ["OVERRIDE MSG 1", "OVERRIDE MSG 2"]
            assert stage.trigger == "OVERRIDE TRIGGER: answer now"

    temp03 = [c for c in gw.calls if c[2].get("temperature") == 0.3]
    wait_calls = [
        c for c in temp03
        if c[1] in ([{"role": "user", "content": "OVERRIDE MSG 1"}],
                    [{"role": "user", "content": "OVERRIDE MSG 2"}])
    ]
    assert len(wait_calls) == 4, (
        f"expected 2 wait calls per worker × 2 workers, got {len(wait_calls)}"
    )
    trigger_calls = [
        c for c in temp03
        if c[1] == [{"role": "user", "content": "OVERRIDE TRIGGER: answer now"}]
    ]
    assert len(trigger_calls) == 2, (
        f"expected one trigger call per worker, got {len(trigger_calls)}"
    )


@pytest.mark.asyncio
async def test_progressive_true_plus_wait_messages_sets_both(
    config, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    """The explicit flag and wait_messages together are not a conflict."""
    from chimera.config import DeliberationOverrides

    engine, _, seen = _capture_stages(config, monkeypatch)
    await engine.deliberate(
        "test", "auto",
        overrides=DeliberationOverrides(progressive=True, wait_messages=["CTX 1"]),
    )
    for stage in seen[0]:
        if stage.kind == "worker":
            assert stage.progressive is True
            assert stage.wait_messages == ["CTX 1"]


# --------------------------------------------------------------------------- #
# MCP surface: a progressive=True call reaches the engine with the flag intact
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_mcp_deliberate_forwards_progressive_to_the_stages(
    config, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    """C1 on the MCP surface: tools/call progressive=true → progressive stages.

    Drives the real tool through ``call_tool`` with a spy engine, so the whole
    forwarding path (served schema → ``DeliberationOverrides`` → engine call) is
    pinned on the arguments the tool actually passes, then re-drives that exact
    overrides object through the REAL engine to prove the stages carry the flag.
    """
    captured: dict = {}

    class SpyEngine:
        async def deliberate(self, *args, **kwargs):  # noqa: ANN002, ANN003
            captured.update(kwargs)
            # Neighbouring MCP tests (tests/test_mcp.py) return a
            # SimpleNamespace here; the tool only reads ``answer`` and
            # ``trace.model_dump``.
            return SimpleNamespace(
                answer="ok",
                trace=SimpleNamespace(model_dump=lambda mode: {"formation": "simple"}),
            )

    server = build_server(config=config, engine=SpyEngine())
    await server._tool_manager.call_tool(
        "chimera_deliberate",
        {"prompt": "hello", "formation": "simple", "progressive": True},
    )
    overrides = captured["overrides"]
    assert overrides.progressive is True
    assert overrides.wait_messages is None

    # …and that exact argument really does land on the worker stages.
    engine, _, seen = _capture_stages(config, monkeypatch)
    await engine.deliberate("hello", "simple", overrides=overrides)
    workers = [s for s in seen[0] if s.kind == "worker"]
    assert workers
    assert all(s.progressive is True for s in workers), (
        f"stages after the MCP call: "
        f"{[(s.id, s.progressive) for s in seen[0]]}"
    )
