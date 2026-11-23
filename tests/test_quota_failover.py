"""DF-CHIMERA-V2-130 — a quota-dead provider must not sink a deliberation.

The measured defect (live deployment): ``GET /v1/health`` reported
``detail.providers.deepseek.status='degraded'`` / ``error_class='quota'``
truthfully, while the selection path built its candidate set from credential
PRESENCE only.  A provider whose key exists but whose balance is empty was
therefore treated as perfectly usable, chosen, and every stage call failed —
3 of 4 real deliberations ended with a 502 or an empty answer.  The aggregator
retry then pointed at ``defaults.default_aggregator``, which was the same
quota-dead model, so the merge stage died too.

What these tests pin:

* a formation whose defaults name a quota-dead provider is served by the next
  healthy configured candidate (HTTP 200, every stage on the healthy provider,
  zero calls to the dead one),
* ``/v1/health`` keeps reporting ``error_class='quota'`` for the dead provider
  while that deliberation succeeds (no masking),
* the quota block is short-lived (its own TTL) and expires — a provider is
  never exiled permanently,
* a timeout / generic 5xx / pure rate limit never creates a quota block,
* the aggregator fallback is a model that can actually serve (a
  ``BudgetExhaustedError`` on the merge no longer escapes as a 500),
* when NOTHING healthy is left, the answer is a machine-readable 503 naming
  every skipped candidate (provider + model + failure class), and no call is
  spent discovering that,
* the SAME all-quota-dead deployment on the bare (no formation) ``auto`` path
  answers the same classified 503 instead of raising ``BudgetExhaustedError``
  out of the request (RELEASE-FINDING-2026-11-21-002): the dispatcher design
  call failing is caught, the block is recorded, and the DF-130 filter turns
  it into ``NoHealthyCandidateError``.

Wiring, not mocks of the thing under test: everything below drives the real
``create_app`` -> route -> ``Engine.deliberate`` -> selection -> gateway path.
Only the *transport* (provider HTTP) is stubbed, with the repo's FakeGateway;
the probe results come from the REAL ``_check_providers`` classifier over the
same kind of scripted transport.  No network.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera import blocked_models  # noqa: E402
from chimera.api.server import _check_providers, create_app  # noqa: E402
from chimera.blocked_models import (  # noqa: E402
    DEFAULT_BLOCK_COOLDOWN_S,
    DEFAULT_QUOTA_BLOCK_COOLDOWN_S,
    REASON_QUOTA,
    ModelBlockRegistry,
    classify_error,
    is_quota_error,
)
from chimera.config import ChimeraConfig  # noqa: E402
from chimera.dispatcher import Dispatcher  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.exceptions import BudgetExhaustedError, NoHealthyCandidateError  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway  # noqa: E402

#: The catalog id of the quota-dead provider (provider ``deepseek``).
DEAD_MODEL = "deepseek/deepseek-chat"
#: A second model on the SAME dead provider — quota exhaustion is account-level,
#: so it must be skipped for the same reason the first one is.
DEAD_MODEL_2 = "deepseek/deepseek-v4-flash"
#: The healthy provider's model (provider ``openrouter``).
HEALTHY_MODEL = "openrouter/google/gemini-2.5-flash"

#: The exact wording a 402-style exhausted balance carries.
_QUOTA_DETAIL = (
    "insufficient_quota: You exceeded your current quota, please check your plan and billing details."
)


class _StatusError(RuntimeError):
    """Provider error carrying an HTTP status code, like litellm's."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def _config(*, worker: str = DEAD_MODEL, aggregator: str | None = None) -> ChimeraConfig:
    """The live shape: dead ``deepseek`` + healthy ``openrouter``, both funded keys."""
    cfg = ChimeraConfig.model_validate(
        {
            "provider_discovery": False,
            "providers": {
                "deepseek": {"base_url": "https://api.deepseek.com/v1"},
                "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
            },
            "models": {
                DEAD_MODEL: {
                    "provider": "deepseek",
                    "cost_tier": "budget",
                    "categories": {
                        "code": 95.0,
                        "analysis": 85.0,
                        "design": 40.0,
                        "audit": 60.0,
                        "reasoning": 80.0,
                    },
                },
                DEAD_MODEL_2: {
                    "provider": "deepseek",
                    "cost_tier": "budget",
                    "categories": {
                        "code": 88.0,
                        "analysis": 80.0,
                        "design": 50.0,
                        "audit": 55.0,
                        "reasoning": 75.0,
                    },
                },
                HEALTHY_MODEL: {
                    "provider": "openrouter",
                    "cost_tier": "budget",
                    "categories": {
                        "code": 70.0,
                        "analysis": 75.0,
                        "design": 90.0,
                        "audit": 50.0,
                        "reasoning": 65.0,
                    },
                },
            },
            "defaults": {
                "dispatcher": HEALTHY_MODEL,
                "default_worker": worker,
                "default_aggregator": aggregator or worker,
            },
            "formations": {
                "auto": {"mode": "auto"},
                "simple": {"workers": 2, "aggregator": "default"},
            },
            "observability": {"log_level": "warning", "trace_enabled": False, "langfuse": {"enabled": False}},
            "server": {"host": "127.0.0.1", "port": 8000},
        }
    )
    # Both providers have a PRESENT key — the credential check is exactly what
    # the defect relied on to call a busted account "usable".
    cfg.api_keys.update({"deepseek": "sk-deepseek-present", "openrouter": "sk-openrouter-present"})
    return cfg


def _health(*, dead: bool = True, healthy: bool = True) -> dict[str, dict[str, Any]]:
    """A provider-health snapshot in the shape ``/v1/health`` produces."""
    snapshot: dict[str, dict[str, Any]] = {}
    if dead:
        snapshot["deepseek"] = {
            "healthy": False,
            "error": f"quota: {_QUOTA_DETAIL}",
            "error_class": "quota",
            "model_tested": DEAD_MODEL,
        }
    if healthy:
        snapshot["openrouter"] = {"healthy": True, "model_tested": HEALTHY_MODEL}
    return snapshot


def _transport() -> FakeGateway:
    """Provider transport: the dead account refuses, the healthy one answers.

    This is the ONLY stub in the success-path tests.  Selection, the formation,
    the aggregator retry and the HTTP layer all run for real.
    """

    def responder(model: str, messages: list[dict[str, str]], response_format: Any = None, **kw: Any):
        if model.startswith("deepseek/"):
            raise BudgetExhaustedError(model, "deepseek", details=_QUOTA_DETAIL)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return GatewayResponse(
                text=f"MERGED ANSWER from {model}", model=model, tokens_input=60, tokens_output=90
            )
        return GatewayResponse(
            text=f"worker output from {model}", model=model, tokens_input=20, tokens_output=40
        )

    return FakeGateway(responder)


def _resp(text: str, model: str) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=10, tokens_output=20)


def _calls(gateway: FakeGateway) -> list[str]:
    return [model for model, _messages, _kwargs in gateway.calls]


def _stage_models(body: dict[str, Any]) -> dict[str, str]:
    """``{stage_id: model}`` from a serialized trace."""
    return {stage["stage_id"]: stage["model"] for stage in body["trace"]["stages"]}


@pytest.fixture(autouse=True)
def _fresh_registry() -> Any:
    """Isolate the process-wide block registry (its own file-less instance)."""
    original = blocked_models.shared_registry
    blocked_models.set_shared_registry(ModelBlockRegistry(state_path=None))
    try:
        yield blocked_models.shared_registry
    finally:
        blocked_models.set_shared_registry(original)


def _client(
    config: ChimeraConfig, gateway: FakeGateway, snapshot: dict[str, dict[str, Any]] | None
) -> TestClient:
    engine = Engine(config, gateway, provider_health=(lambda: snapshot) if snapshot is not None else None)
    return TestClient(create_app(config=config, engine=engine))


# --------------------------------------------------------------------------- #
# 1. The measured shape: defaults name the dead provider, the run still answers
# --------------------------------------------------------------------------- #


def test_quota_dead_default_worker_is_served_by_the_healthy_provider() -> None:
    """Defaults name A (quota-dead) → HTTP 200, every stage served by B."""
    cfg = _config()
    gateway = _transport()
    client = _client(cfg, gateway, _health())

    response = client.post("/v1/deliberate", json={"prompt": "explain the release", "formation": "simple"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"] == f"MERGED ANSWER from {HEALTHY_MODEL}"

    stages = _stage_models(body)
    assert stages, "the trace must carry the stages that served the answer"
    # Every stage — workers AND the aggregator — ran on the healthy provider.
    assert set(stages.values()) == {HEALTHY_MODEL}
    # Nothing was billed on the dead account: the selection path never called it.
    assert [m for m in _calls(gateway) if m.startswith("deepseek/")] == []
    # No stage degraded, so no worker_failures and no degraded answer.
    assert body["trace"]["worker_failures"] == []
    assert body.get("worker_failures") is None


def test_a_recorded_quota_block_also_steers_selection_without_a_health_snapshot() -> None:
    """Cold health cache (no snapshot): the block recorded from the failure wins.

    Covers the window between a real quota failure and the next health probe —
    the engine must not need the probe to remember that the account is empty.
    """
    cfg = _config()
    blocked_models.shared_registry.record_failure(
        DEAD_MODEL,
        BudgetExhaustedError(DEAD_MODEL, "deepseek", details=_QUOTA_DETAIL),
    )
    gateway = _transport()
    client = _client(cfg, gateway, None)

    response = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "simple"})

    assert response.status_code == 200, response.text
    assert [m for m in _calls(gateway) if m.startswith("deepseek/")] == []
    assert set(_stage_models(response.json()).values()) == {HEALTHY_MODEL}


def test_account_level_exhaustion_covers_every_model_of_that_provider() -> None:
    """A quota verdict on one model skips the provider's OTHER models too."""
    cfg = _config(worker=DEAD_MODEL_2)
    gateway = _transport()
    client = _client(cfg, gateway, _health())

    response = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "simple"})

    assert response.status_code == 200, response.text
    # DEAD_MODEL_2's own provider is dead, even though the health probe only
    # tested DEAD_MODEL — otherwise a dead provider gets re-selected per model.
    assert [m for m in _calls(gateway) if m.startswith("deepseek/")] == []


# --------------------------------------------------------------------------- #
# 2. No masking: the health snapshot keeps telling the truth
# --------------------------------------------------------------------------- #


def test_health_still_reports_quota_while_the_deliberation_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One deployment: /v1/health says quota, /v1/deliberate answers 200."""
    cfg = _config()

    class _ProbeGateway:
        """Transport used by the health probe: dead provider refuses, other answers."""

        async def complete(
            self, model: str, messages: list[dict[str, str]], **kwargs: Any
        ) -> GatewayResponse:
            if model.startswith("deepseek/"):
                raise _StatusError(f"litellm.RateLimitError: {_QUOTA_DETAIL}", status_code=402)
            return GatewayResponse(text="pong", model=model, tokens_input=1, tokens_output=1)

    # The probe result comes from the REAL classifier, not a hand-written stub.
    real_probe = asyncio.run(_check_providers(cfg, _ProbeGateway()))
    assert real_probe["deepseek"]["healthy"] is False
    assert real_probe["deepseek"]["error_class"] == "quota"
    monkeypatch.setattr("chimera.api.server._check_providers", _real_probe(real_probe))

    gateway = _transport()
    app = create_app(
        config=cfg,
        engine=Engine(cfg, gateway, provider_health=lambda: real_probe),
    )
    client = TestClient(app)

    health = client.get("/v1/health").json()
    assert health["status"] == "degraded"
    assert health["unhealthy_providers"] == ["deepseek"]
    assert health["details"]["providers"]["deepseek"]["error_class"] == "quota"

    response = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "simple"})

    assert response.status_code == 200, response.text
    # The condition is still reported AFTER a successful deliberation.
    assert client.get("/v1/health").json()["details"]["providers"]["deepseek"]["error_class"] == "quota"


def _real_probe(status: dict[str, dict[str, Any]]) -> Any:
    async def probe(config: ChimeraConfig, gateway: Any) -> dict[str, dict[str, Any]]:
        return status

    return probe


def test_default_app_wires_the_engine_to_the_health_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The app-built engine reads the /v1/health cache — read-only, no probe.

    This is the seam itself: with no explicit engine, ``create_app`` must hand
    the engine the cache getter.  Before any probe the engine sees ``None`` (no
    verdict, nothing invented); after a health call it sees the same snapshot
    the endpoint served.
    """
    cfg = _config()
    status = _health()
    monkeypatch.setattr("chimera.api.server._check_providers", _real_probe(status))
    app = create_app(config=cfg)  # no engine → the production construction path

    engine = app.state.engine
    assert engine._provider_health is not None
    assert engine._provider_health() is None, "an unprobed cache must not invent a verdict"

    client = TestClient(app)
    assert client.get("/v1/health").json()["details"]["providers"]["deepseek"]["error_class"] == "quota"
    assert engine._provider_health() == status


# --------------------------------------------------------------------------- #
# 3. The block is short-lived and expires (no permanent exile)
# --------------------------------------------------------------------------- #


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def test_quota_block_uses_its_own_short_ttl_and_expires() -> None:
    """A topped-up provider becomes a candidate again after the quota TTL."""
    assert DEFAULT_QUOTA_BLOCK_COOLDOWN_S < DEFAULT_BLOCK_COOLDOWN_S / 10, (
        "the quota TTL must be materially shorter than the guardrail/credential one"
    )
    clock = _FakeClock()
    registry = ModelBlockRegistry(clock=clock, state_path=None)
    assert registry.quota_cooldown_s == DEFAULT_QUOTA_BLOCK_COOLDOWN_S

    assert registry.record_failure("model/a", BudgetExhaustedError("model/a", "prov", _QUOTA_DETAIL))
    assert registry.block_reason("model/a") == REASON_QUOTA
    assert registry.blocked_detail()["model/a"]["expires_in_s"] == pytest.approx(
        DEFAULT_QUOTA_BLOCK_COOLDOWN_S, abs=1.0
    )

    clock.now += DEFAULT_QUOTA_BLOCK_COOLDOWN_S - 1
    assert registry.is_blocked("model/a")

    clock.now += 2  # past the quota TTL, far below the guardrail TTL
    assert not registry.is_blocked("model/a")
    assert registry.blocked() == set()


def test_quota_block_persists_short_across_a_restart(tmp_path: Any) -> None:
    """A persisted quota block reloads with its own (short) remaining time."""
    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path).record_failure(
        "model/a", BudgetExhaustedError("model/a", "prov", _QUOTA_DETAIL)
    )

    reloaded = ModelBlockRegistry(state_path=path)
    assert reloaded.is_blocked("model/a")
    assert reloaded.block_reason("model/a") == REASON_QUOTA
    remaining = reloaded.blocked_detail()["model/a"]["expires_in_s"]
    assert 0 < remaining <= DEFAULT_QUOTA_BLOCK_COOLDOWN_S


def test_expired_quota_block_lets_the_default_worker_be_used_again() -> None:
    """After the TTL the configured default is selected again (end to end)."""
    cfg = _config()
    clock = _FakeClock()
    registry = ModelBlockRegistry(clock=clock, state_path=None)
    registry.record_failure(DEAD_MODEL, BudgetExhaustedError(DEAD_MODEL, "deepseek", _QUOTA_DETAIL))
    original = blocked_models.shared_registry
    blocked_models.set_shared_registry(registry)
    try:
        gateway = FakeGateway(lambda model, messages, **kw: _resp(f"ok {model}", model))
        engine = Engine(cfg, gateway)
        asyncio.run(engine.deliberate("hello", "simple"))
        assert [m for m in _calls(gateway) if m.startswith("deepseek/")] == []

        clock.now += DEFAULT_QUOTA_BLOCK_COOLDOWN_S + 1
        gateway.calls.clear()
        asyncio.run(engine.deliberate("hello", "simple"))
        # The provider is a candidate again — the block was not a life sentence.
        assert [m for m in _calls(gateway) if m.startswith("deepseek/")] != []
    finally:
        blocked_models.set_shared_registry(original)


# --------------------------------------------------------------------------- #
# 4. Transient failures never create a quota block
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("stage timed out after 60s"),
        RuntimeError("timed out after 120s"),
        _StatusError("upstream 500: internal server error", status_code=500),
        _StatusError("502 Bad Gateway", status_code=502),
        RuntimeError("429 rate limit exceeded"),
        RuntimeError("litellm.RateLimitError: rate limited, retry in 20s"),
        RuntimeError("APIConnectionError: connection refused"),
    ],
)
def test_timeout_and_5xx_never_create_a_quota_block(error: Exception) -> None:
    registry = ModelBlockRegistry(state_path=None)

    assert is_quota_error(error) is False
    assert registry.record_failure("model/a", error) is False
    assert registry.is_blocked("model/a") is False
    assert registry.blocked_detail() == {}


def test_budget_exhausted_error_is_the_quota_class_by_type() -> None:
    """The typed signal is recognised even with no billing prose in ``details``."""
    exc = BudgetExhaustedError("model/a", "prov")
    assert is_quota_error(exc) is True
    assert classify_error(exc) == REASON_QUOTA
    # …and the recorded stage error keeps the class (the engine records str(exc)).
    assert classify_error(str(exc)) == REASON_QUOTA


def test_a_timeout_failure_does_not_exclude_the_provider_from_the_next_run() -> None:
    """A run that dies on timeouts leaves candidacy untouched."""
    cfg = _config()

    def responder(model: str, messages: list[dict[str, str]], **kw: Any) -> GatewayResponse:
        raise TimeoutError("stage timed out after 60s")

    gateway = FakeGateway(responder)
    engine = Engine(cfg, gateway)
    result = asyncio.run(engine.deliberate("hello", "simple"))

    assert result.answer_degraded is True
    assert blocked_models.shared_registry.blocked_detail() == {}
    # The next run still selects the configured default — nothing was exiled.
    gateway.calls.clear()
    asyncio.run(engine.deliberate("hello", "simple"))
    assert set(_calls(gateway)) == {DEAD_MODEL}


# --------------------------------------------------------------------------- #
# 5. The aggregator is not a single point of failure
# --------------------------------------------------------------------------- #


def test_quota_dead_aggregator_falls_back_to_a_healthy_model() -> None:
    """A BudgetExhaustedError on the merge retries on a model that can serve.

    Before the fix the retry target was ``defaults.default_aggregator`` — the
    same dead account — and ``BudgetExhaustedError`` was not even caught by that
    retry, so it escaped the stage handler entirely (a 500, not a 502).
    """
    cfg = _config(worker=HEALTHY_MODEL, aggregator=DEAD_MODEL)
    gateway = _transport()
    client = _client(cfg, gateway, None)  # cold cache: only the failure itself signals

    response = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "simple"})

    assert response.status_code == 200, response.text
    body = response.json()
    aggregator = next(s for s in body["trace"]["stages"] if s["stage_id"] == "aggregator")
    assert aggregator["model"] == HEALTHY_MODEL
    assert body["answer"] == f"MERGED ANSWER from {HEALTHY_MODEL}"


# --------------------------------------------------------------------------- #
# 6. Nothing healthy left → a machine-readable error, not a bare 502
# --------------------------------------------------------------------------- #


def test_no_healthy_candidate_returns_machine_readable_503() -> None:
    cfg = _config()
    gateway = _transport()
    # BOTH providers are out of budget.
    snapshot = _health(healthy=False)
    snapshot["openrouter"] = {
        "healthy": False,
        "error": "quota: insufficient_quota",
        "error_class": "quota",
        "model_tested": HEALTHY_MODEL,
    }
    client = _client(cfg, gateway, snapshot)

    response = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "simple"})

    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert error["type"] == "no_healthy_candidate"
    # The provider's own words survive on the per-candidate entry.
    assert any("insufficient_quota" in str(a["detail"]) for a in error["attempts"])

    attempts = error["attempts"]
    assert {a["model"] for a in attempts} == {DEAD_MODEL, DEAD_MODEL_2, HEALTHY_MODEL}
    assert {a["error_class"] for a in attempts} == {"quota"}
    assert {a["provider"] for a in attempts} == {"deepseek", "openrouter"}
    # Nothing was billed discovering that: no provider call happened at all.
    assert gateway.calls == []


def test_no_healthy_candidate_error_names_every_attempted_candidate() -> None:
    """The exception itself (not just the HTTP body) is machine-readable."""
    cfg = _config()
    engine = Engine(cfg, FakeGateway(), provider_health=lambda: _dead_both())
    with pytest.raises(NoHealthyCandidateError) as excinfo:
        asyncio.run(engine.deliberate("hello", "simple"))

    attempts = excinfo.value.attempts
    assert {a["model"] for a in attempts} == {DEAD_MODEL, DEAD_MODEL_2, HEALTHY_MODEL}
    assert all(a["error_class"] == "quota" for a in attempts)
    assert any(a["provider"] == "deepseek" for a in attempts)


def _dead_both() -> dict[str, dict[str, Any]]:
    return {
        "deepseek": {"healthy": False, "error": "quota: insufficient_quota", "error_class": "quota"},
        "openrouter": {"healthy": False, "error": "quota: insufficient_quota", "error_class": "quota"},
    }


def test_missing_credentials_alone_is_not_a_no_candidate_error() -> None:
    """Only positive quota evidence triggers the arm — absent keys keep auth errors.

    Otherwise a deployment that simply never configured a key would start
    answering 503 "no healthy candidate" instead of its documented auth failure.
    """
    cfg = _config()
    cfg.api_keys.clear()
    gateway = FakeGateway(lambda model, messages, **kw: _resp("x", model))
    engine = Engine(cfg, gateway, provider_health=lambda: _health())

    result = asyncio.run(engine.deliberate("hello", "simple"))

    assert result.answer_degraded is False  # nothing was excluded; the calls ran
    assert gateway.calls != []


# --------------------------------------------------------------------------- #
# 7. The bare (no formation) auto path converges on the SAME classified error
#    (RELEASE-FINDING-2026-11-21-002)
# --------------------------------------------------------------------------- #


def _dead_only_config() -> ChimeraConfig:
    """The incident shape: ONE provider, quota-dead, and it IS the dispatcher.

    The release-verify traceback (run 44912051562) died on the dispatcher model
    itself — ``BudgetExhaustedError('Budget exhausted for model
    deepseek/deepseek-v4-flash (provider: deepseek)')`` raised out of
    ``dispatcher._dispatch_auto`` — because on ``auto`` the design call runs
    BEFORE the DF-CHIMERA-V2-130 quota filter ever sees the run.  With no other
    provider configured, ``auto`` must answer the same classified 503 an
    explicit formation answers.
    """
    cfg = ChimeraConfig.model_validate(
        {
            "provider_discovery": False,
            "providers": {
                "deepseek": {"base_url": "https://api.deepseek.com/v1"},
            },
            "models": {
                DEAD_MODEL: {
                    "provider": "deepseek",
                    "cost_tier": "budget",
                    "categories": {
                        "code": 95.0,
                        "analysis": 85.0,
                        "design": 40.0,
                        "audit": 60.0,
                        "reasoning": 80.0,
                    },
                },
                DEAD_MODEL_2: {
                    "provider": "deepseek",
                    "cost_tier": "budget",
                    "categories": {
                        "code": 88.0,
                        "analysis": 80.0,
                        "design": 50.0,
                        "audit": 55.0,
                        "reasoning": 75.0,
                    },
                },
            },
            "defaults": {
                "dispatcher": DEAD_MODEL_2,
                "default_worker": DEAD_MODEL,
                "default_aggregator": DEAD_MODEL,
            },
            "formations": {
                "auto": {"mode": "auto"},
                "simple": {"workers": 2, "aggregator": "default"},
            },
            "observability": {"log_level": "warning", "trace_enabled": False, "langfuse": {"enabled": False}},
            "server": {"host": "127.0.0.1", "port": 8000},
        }
    )
    # The key is PRESENT — the account is simply out of budget.  A missing key
    # is a different failure class and keeps its own (auth-error) behaviour.
    cfg.api_keys.update({"deepseek": "«redacted:sk-…»"})
    return cfg


def test_quota_dead_auto_dispatch_returns_machine_readable_503() -> None:
    """Bare request (no formation), cold health cache → 503 no_healthy_candidate.

    Pre-fix this raised ``BudgetExhaustedError`` out of the request (the raw
    traceback of the release-verify run).  The health cache is deliberately
    None here: the ONLY quota signal is the block the dispatcher's catch must
    record, so this test exercises BOTH halves of the fix — without the catch
    the exception escapes; without the record the run proceeds and dies as a
    bare 502 on stage failures.
    """
    cfg = _dead_only_config()
    gateway = _transport()
    client = _client(cfg, gateway, None)  # cold cache: only the failure itself signals

    response = client.post("/v1/deliberate", json={"prompt": "explain the release"})

    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert error["type"] == "no_healthy_candidate"
    assert "No healthy candidate" in error["message"]
    # Every configured candidate is named, with its provider and failure class.
    attempts = error["attempts"]
    assert {a["model"] for a in attempts} == {DEAD_MODEL, DEAD_MODEL_2}
    assert {a["provider"] for a in attempts} == {"deepseek"}
    assert {a["error_class"] for a in attempts} == {"quota"}
    # The block carries its own short TTL → the 503 tells the caller when to retry.
    assert response.headers.get("Retry-After") is not None
    # Exactly ONE provider call was spent discovering this — the dispatcher
    # design call itself; no worker/aggregator/merge stage was attempted.
    assert _calls(gateway) == [DEAD_MODEL_2]


def test_auto_dispatch_quota_dead_raises_no_healthy_candidate_not_budget_error() -> None:
    """Engine level: the bare ``auto`` deliberation raises the classified error."""
    cfg = _dead_only_config()
    engine = Engine(cfg, _transport())

    with pytest.raises(NoHealthyCandidateError) as excinfo:
        asyncio.run(engine.deliberate("hello"))

    assert not isinstance(excinfo.value, BudgetExhaustedError)
    attempts = excinfo.value.attempts
    assert {a["model"] for a in attempts} == {DEAD_MODEL, DEAD_MODEL_2}
    assert all(a["error_class"] == "quota" for a in attempts)
    assert all(a["provider"] == "deepseek" for a in attempts)


def test_quota_dead_dispatcher_call_falls_back_and_records_block() -> None:
    """The design call itself: `{}` fallback contract kept, quota block recorded.

    PERF-2: a failed dispatcher call must still yield a usable fallback outcome
    (`{}` → generic formation, ``source='fallback'``) — for a quota-dead design
    call it must ALSO leave the block that ``_apply_quota_blocked_models``
    consumes, which is what turns the run into the classified 503.
    """
    cfg = _dead_only_config()
    outcome = asyncio.run(Dispatcher(cfg, _transport()).dispatch("task", "auto"))

    assert outcome.result.source == "fallback"
    assert outcome.response.text == "{}"
    assert blocked_models.shared_registry.block_reason(DEAD_MODEL_2) == REASON_QUOTA
    assert blocked_models.shared_registry.is_blocked(DEAD_MODEL_2)
