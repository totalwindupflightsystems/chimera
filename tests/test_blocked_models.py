"""Tests for the guardrail blocked-model registry and dropped-worker surfacing.

Covers the dogfood P2 finding (2026-08-03): a worker on a model blocked by
OpenRouter privacy guardrails failed silently for the user and the
dispatcher kept re-selecting the same blocked model.
"""

from __future__ import annotations

import pytest

from chimera import blocked_models
from chimera.blocked_models import (
    ModelBlockRegistry,
    is_guardrail_error,
    set_shared_registry,
)


@pytest.fixture(autouse=True)
def _fresh_registry():
    """Isolate the process-wide registry per test (and restore it after)."""
    original = blocked_models.shared_registry
    set_shared_registry(ModelBlockRegistry(state_path=None))
    yield
    set_shared_registry(original)


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


# ---------------------------------------------------------------------------
# Registry mechanics
# ---------------------------------------------------------------------------

def test_guardrail_error_detection() -> None:
    assert is_guardrail_error(
        "404 No endpoints available matching your guardrail restrictions "
        "and data policy"
    )
    assert is_guardrail_error("blocked by PRIVACY guardrail")
    assert is_guardrail_error("No endpoints available for this model")
    assert not is_guardrail_error("connection timed out after 30s")
    assert not is_guardrail_error("429 rate limit exceeded")
    assert not is_guardrail_error("500 internal server error")


def test_guardrail_failure_blocks_model() -> None:
    reg = ModelBlockRegistry(state_path=None)
    assert reg.record_failure(
        "openrouter/qwen/qwen3.7-plus",
        "No endpoints available matching your guardrail restrictions",
    )
    assert reg.is_blocked("openrouter/qwen/qwen3.7-plus")
    assert "openrouter/qwen/qwen3.7-plus" in reg.blocked()


def test_block_expires_after_cooldown_without_sleeping() -> None:
    clock = _FakeClock()
    reg = ModelBlockRegistry(cooldown_s=300.0, clock=clock, state_path=None)
    reg.record_failure("model/a", "guardrail rejection")
    assert reg.is_blocked("model/a")
    clock.now += 299.0
    assert reg.is_blocked("model/a")
    clock.now += 2.0  # past the 300s cooldown
    assert not reg.is_blocked("model/a")
    assert "model/a" not in reg.blocked()


def test_non_guardrail_failure_does_not_block() -> None:
    reg = ModelBlockRegistry(state_path=None)
    assert not reg.record_failure("model/a", "timed out after 120s")
    assert not reg.record_failure("model/a", "503 service unavailable")
    assert not reg.record_failure("model/a", "rate limit exceeded (429)")
    assert not reg.is_blocked("model/a")
    assert reg.blocked() == set()


# ---------------------------------------------------------------------------
# Persistence across restarts (DF-CHIMERA-V2-1)
# ---------------------------------------------------------------------------

_GUARDRAIL_ERR = "404 No endpoints available matching your guardrail restrictions"


def _read_state(path) -> dict:  # type: ignore[no-untyped-def]
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def test_record_failure_persists_block_to_disk(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import time

    path = tmp_path / "blocked.json"
    reg = ModelBlockRegistry(state_path=path)
    assert reg.record_failure("openrouter/qwen/qwen3.7-plus", _GUARDRAIL_ERR)
    data = _read_state(path)
    entries = data["blocked_until_epoch"]
    assert set(entries) == {"openrouter/qwen/qwen3.7-plus"}
    # Persisted as a wall-clock expiry ~cooldown seconds into the future.
    epoch = entries["openrouter/qwen/qwen3.7-plus"]
    assert epoch > time.time() + reg.cooldown_s - 60


def test_block_survives_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A new registry instance on the same path still blocks the model —
    no provider call needed, no 300s-only self-heal."""
    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path).record_failure("model/a", _GUARDRAIL_ERR)
    # Simulate a fresh process: brand-new registry, same state file.
    reg2 = ModelBlockRegistry(state_path=path)
    assert reg2.is_blocked("model/a")
    assert "model/a" in reg2.blocked()


def test_block_survives_restart_with_different_clock_base(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Persisted timestamps are wall-clock: a fresh process whose monotonic
    clock has a completely different base still honors the block."""
    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path, clock=_FakeClock(1000.0)).record_failure(
        "model/a", _GUARDRAIL_ERR
    )
    reg2 = ModelBlockRegistry(state_path=path, clock=_FakeClock(0.0))
    assert reg2.is_blocked("model/a")


def test_default_cooldown_is_long_lived() -> None:
    """Guardrail blocks must not self-heal after the old 300s window."""
    from chimera.blocked_models import DEFAULT_BLOCK_COOLDOWN_S

    assert DEFAULT_BLOCK_COOLDOWN_S >= 24.0 * 3600.0


def test_corrupt_state_file_starts_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "blocked.json"
    path.write_text("{ not json !!", encoding="utf-8")
    reg = ModelBlockRegistry(state_path=path)  # must not raise
    assert reg.blocked() == set()
    # And the registry still works (and overwrites the corrupt file).
    assert reg.record_failure("model/a", _GUARDRAIL_ERR)
    assert ModelBlockRegistry(state_path=path).is_blocked("model/a")


def test_missing_state_file_starts_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    reg = ModelBlockRegistry(state_path=tmp_path / "nope" / "blocked.json")
    assert reg.blocked() == set()


def test_expired_entries_pruned_on_load(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json
    import time

    path = tmp_path / "blocked.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "blocked_until_epoch": {
                    "model/expired": time.time() - 10.0,
                    "model/live": time.time() + 3600.0,
                },
            }
        ),
        encoding="utf-8",
    )
    reg = ModelBlockRegistry(state_path=path)
    assert not reg.is_blocked("model/expired")
    assert reg.is_blocked("model/live")
    assert reg.blocked() == {"model/live"}


def test_non_guardrail_failure_writes_no_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "blocked.json"
    reg = ModelBlockRegistry(state_path=path)
    assert not reg.record_failure("model/a", "timed out after 120s")
    assert not reg.record_failure("model/a", "500 internal server error")
    assert not reg.record_failure("model/a", "429 too many requests")
    assert not path.exists()


def test_persistence_disabled_with_none_path() -> None:
    reg = ModelBlockRegistry(state_path=None)
    assert reg.record_failure("model/a", _GUARDRAIL_ERR)
    assert reg._state_path is None


# ---------------------------------------------------------------------------
# Selector / dispatcher exclusion of persisted blocks (zero provider calls)
# ---------------------------------------------------------------------------


class _FakeEntry:
    """Minimal model entry for selector tests (mirrors test_selector)."""

    def __init__(self, categories: dict[str, float]) -> None:
        self.categories = categories
        self.enabled = True


def test_selector_excludes_persisted_block_after_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from chimera.selector import CategorySelector

    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path).record_failure(
        "anthropic/claude-sonnet-4", _GUARDRAIL_ERR
    )
    # Fresh process: new registry instance reloaded from disk.
    set_shared_registry(ModelBlockRegistry(state_path=path))
    models = {
        "anthropic/claude-sonnet-4": _FakeEntry(
            {"technology_code/code_generation/python": 90}
        ),
        "deepseek/deepseek-v4-flash": _FakeEntry(
            {"technology_code/code_generation/python": 88}
        ),
    }
    sel = CategorySelector(models)
    scores = sel.score("Write Python code")
    assert "anthropic/claude-sonnet-4" not in scores
    assert "deepseek/deepseek-v4-flash" in scores
    assert "anthropic/claude-sonnet-4" not in sel.select("Write Python code")


def test_dispatcher_catalog_excludes_persisted_block_after_restart(
    tmp_path, config
) -> None:  # type: ignore[no-untyped-def]
    from chimera.dispatcher import build_dispatcher_prompt

    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path).record_failure(
        "openrouter/qwen/qwen3-coder", _GUARDRAIL_ERR
    )
    # Fresh process: new registry instance reloaded from disk — the catalog
    # exclusion must happen without any provider call being burned.
    set_shared_registry(ModelBlockRegistry(state_path=path))
    system = build_dispatcher_prompt("task", config)[0]["content"]
    assert "openrouter/qwen/qwen3-coder" not in system
    # Healthy models remain visible to the dispatcher.
    assert "deepseek/deepseek-chat" in system


# ---------------------------------------------------------------------------
# Credential-class blocks (DF-CHIMERA-V2-6)
# ---------------------------------------------------------------------------

#: The auth failure copied from the live repro: a worker stage on a
#: present-but-invalid provider key (401, exit 0, single-model answer).
_AUTH_ERR = (
    "litellm.AuthenticationError: AuthenticationError: OpenrouterException - "
    '{"error":{"message":"User not found.","code":401}}'
)

#: The bogus key the live repro exports; must never reach disk or a log line.
_DEAD_KEY = "bogus-invalid-key-for-testing"
_LIVE_KEY = "sk-a-perfectly-valid-key"


def test_credential_error_detection() -> None:
    """AC1: auth-class errors classify; transients and guardrails do not."""
    from chimera.blocked_models import is_credential_error

    assert is_credential_error(_AUTH_ERR)
    assert is_credential_error(
        "openrouter/x call failed: litellm.AuthenticationError: "
        '{"error":{"message":"Missing Authentication header","code":401}}'
    )
    assert is_credential_error("401 Unauthorized")
    assert is_credential_error("Invalid API key provided")
    assert is_credential_error("No auth credentials found")
    assert is_credential_error("litellm.PermissionDeniedError: forbidden")

    assert not is_credential_error("connection timed out after 30s")
    assert not is_credential_error("litellm.RateLimitError: 429 rate limit exceeded")
    assert not is_credential_error("500 internal server error")
    assert not is_credential_error("503 Service Unavailable")
    assert not is_credential_error(
        "404 No endpoints available matching your guardrail restrictions"
    )


def test_credential_failure_blocks_with_reason_and_fingerprint(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """AC1: record_failure() == True, persisted with reason + fingerprint."""
    path = tmp_path / "blocked.json"
    reg = ModelBlockRegistry(state_path=path)
    assert reg.record_failure(
        "openrouter/openai/gpt-5.6-sol", _AUTH_ERR, credential_fingerprint="fp-dead"
    )
    assert reg.is_blocked("openrouter/openai/gpt-5.6-sol")
    assert reg.block_reason("openrouter/openai/gpt-5.6-sol") == "credential"
    assert reg.credential_fingerprint("openrouter/openai/gpt-5.6-sol") == "fp-dead"

    data = _read_state(path)
    assert data["reasons"]["openrouter/openai/gpt-5.6-sol"] == "credential"
    assert data["credential_fingerprints"]["openrouter/openai/gpt-5.6-sol"] == "fp-dead"


def test_transient_failures_still_do_not_block_with_fingerprint() -> None:
    reg = ModelBlockRegistry(state_path=None)
    for transient in (
        "connection timed out after 30s",
        "429 rate limit exceeded",
        "500 internal server error",
    ):
        assert not reg.record_failure(
            "model/a", transient, credential_fingerprint="fp-whatever"
        )
    assert reg.blocked() == set()


def test_guardrail_classification_is_unchanged(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """AC6: guardrail still blocks, keeps its class, stores no fingerprint."""
    reg = ModelBlockRegistry(state_path=tmp_path / "blocked.json")
    assert reg.record_failure(
        "model/g", _GUARDRAIL_ERR, credential_fingerprint="fp-dead"
    )
    assert reg.is_blocked("model/g")
    assert reg.block_reason("model/g") == "guardrail"
    assert reg.credential_fingerprint("model/g") is None
    # A guardrail block is a policy property, not a key property: a different
    # credential must NOT clear it.
    assert reg.is_blocked("model/g", credential_fingerprint="fp-other")


def test_credential_block_survives_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """AC3: durable exclusion — a fresh registry on the same path still blocks."""
    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path).record_failure(
        "openrouter/openai/gpt-5.6-sol", _AUTH_ERR, credential_fingerprint="fp-dead"
    )
    reg2 = ModelBlockRegistry(state_path=path)
    assert reg2.is_blocked("openrouter/openai/gpt-5.6-sol")
    assert reg2.block_reason("openrouter/openai/gpt-5.6-sol") == "credential"
    assert reg2.credential_fingerprint("openrouter/openai/gpt-5.6-sol") == "fp-dead"


def test_replaced_credential_clears_the_block(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """AC4 (self-heal): a changed key makes the block stale and clears it."""
    path = tmp_path / "blocked.json"
    reg = ModelBlockRegistry(state_path=path)
    reg.record_failure("openrouter/x", _AUTH_ERR, credential_fingerprint="fp-dead")

    assert reg.is_blocked("openrouter/x", credential_fingerprint="fp-dead")
    assert not reg.is_blocked("openrouter/x", credential_fingerprint="fp-new")
    assert not reg.is_blocked("openrouter/x")
    assert "openrouter/x" not in reg.blocked()
    assert _read_state(path)["blocked_until_epoch"] == {}

    # Same model, same (still-dead) key recorded afresh → blocked again.
    reg.record_failure("openrouter/x", _AUTH_ERR, credential_fingerprint="fp-new")
    assert reg.is_blocked("openrouter/x", credential_fingerprint="fp-new")
    # No fingerprint argument → unchanged TTL semantics (still blocked).
    assert reg.is_blocked("openrouter/x")


def test_legacy_state_file_still_blocks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Backward compatibility: a pre-V2-6 state file loads as guardrail blocks."""
    import json
    import time

    path = tmp_path / "blocked.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "blocked_until_epoch": {"model/old": time.time() + 3600.0},
            }
        ),
        encoding="utf-8",
    )
    reg = ModelBlockRegistry(state_path=path)
    assert reg.is_blocked("model/old")
    assert reg.block_reason("model/old") == "guardrail"
    assert reg.credential_fingerprint("model/old") is None
    # An entry with no stored fingerprint cannot prove the key changed, so a
    # fingerprint argument must leave it blocked.
    assert reg.is_blocked("model/old", credential_fingerprint="some-other-key")


def test_state_file_never_contains_the_raw_credential(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """AC2: the persisted state carries a digest, never the key; no log leaks it."""
    import json

    import structlog

    from chimera.config import credential_fingerprint

    path = tmp_path / "blocked.json"
    fp = credential_fingerprint(_DEAD_KEY)
    assert fp is not None
    assert _DEAD_KEY not in fp

    reg = ModelBlockRegistry(state_path=path)
    with structlog.testing.capture_logs() as logs:
        assert reg.record_failure("openrouter/x", _AUTH_ERR, credential_fingerprint=fp)

    text = path.read_text(encoding="utf-8")
    assert _DEAD_KEY not in text
    assert fp in text
    # ...and nothing in the emitted log records carries the credential either.
    assert logs, "expected model_blocked_credential to be logged"
    assert any(entry.get("event") == "model_blocked_credential" for entry in logs)
    assert all(
        _DEAD_KEY not in json.dumps(entry, default=str) for entry in logs
    )


# ---------------------------------------------------------------------------
# Credential fingerprints come from the resolved config credential
# ---------------------------------------------------------------------------


def test_provider_credential_fingerprint_resolution() -> None:
    import copy

    from chimera.config import (
        ChimeraConfig,
        credential_fingerprint,
        model_credential_fingerprint,
        provider_credential_fingerprint,
    )
    from tests.conftest import CONFIG_DICT

    cfg = ChimeraConfig.model_validate(copy.deepcopy(CONFIG_DICT))
    # Nothing resolves → no fingerprint (and no false "the key changed" signal).
    assert provider_credential_fingerprint(cfg, "openrouter") is None
    assert provider_credential_fingerprint(cfg, "anthropic") is None
    assert model_credential_fingerprint(cfg, "deepseek/deepseek-chat") is None

    # 1. config.api_keys (env-shortcut mirror) is the first source.
    cfg.api_keys["openrouter"] = _DEAD_KEY
    assert provider_credential_fingerprint(cfg, "openrouter") == (
        credential_fingerprint(_DEAD_KEY)
    )
    assert model_credential_fingerprint(cfg, "deepseek/deepseek-chat") == (
        credential_fingerprint(_DEAD_KEY)
    )

    # 2. providers[x].api_key is the second source …
    cfg2 = ChimeraConfig.model_validate(copy.deepcopy(CONFIG_DICT))
    cfg2.providers["openrouter"].api_key = _LIVE_KEY
    assert provider_credential_fingerprint(cfg2, "openrouter") == (
        credential_fingerprint(_LIVE_KEY)
    )
    # … and F8 (anthropic → openrouter) resolves the same credential.
    assert provider_credential_fingerprint(cfg2, "anthropic") == (
        credential_fingerprint(_LIVE_KEY)
    )

    # Unknown model / provider → None, never an exception.
    assert model_credential_fingerprint(cfg2, "no/such/model") is None
    assert provider_credential_fingerprint(cfg2, "nope") is None

    # The digest is truncated sha256 hex, and a rotated key changes it.
    assert credential_fingerprint(_DEAD_KEY) != credential_fingerprint(_LIVE_KEY)
    assert len(credential_fingerprint(_DEAD_KEY) or "") == 16


def test_dispatcher_catalog_self_heals_after_the_key_changes(config) -> None:  # type: ignore[no-untyped-def]
    """A credential block whose key was replaced must not hide the model."""
    from chimera.config import credential_fingerprint
    from chimera.dispatcher import build_dispatcher_prompt

    model = "openrouter/qwen/qwen3-coder"
    config.api_keys["openrouter"] = _DEAD_KEY
    reg = ModelBlockRegistry(state_path=None)
    reg.record_failure(model, _AUTH_ERR, credential_fingerprint=credential_fingerprint(_DEAD_KEY))
    set_shared_registry(reg)
    assert model not in build_dispatcher_prompt("task", config)[0]["content"]

    # Operator rotates the key → the block no longer applies to this key.
    config.api_keys["openrouter"] = _LIVE_KEY
    assert model in build_dispatcher_prompt("task", config)[0]["content"]
    assert not reg.is_blocked(model)


# ---------------------------------------------------------------------------
# The engine refuses to assign a credential-blocked model to a worker stage
# ---------------------------------------------------------------------------


def _credential_config():  # type: ignore[no-untyped-def]
    """conftest catalog + one dead (openrouter) and one live (zai) credential."""
    import copy

    from chimera.config import ChimeraConfig
    from tests.conftest import CONFIG_DICT

    data = copy.deepcopy(CONFIG_DICT)
    data["api_keys"] = {"openrouter": _DEAD_KEY, "zai": _LIVE_KEY}
    return ChimeraConfig.model_validate(data)


def _preset_responder(payload: str):  # type: ignore[no-untyped-def]
    import json

    from tests.conftest import resp

    def _responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # dispatcher
            return resp(payload, model)
        if "Upstream outputs" in json.dumps(messages):  # aggregator
            return resp(f"[merged answer from {model}]", model)
        return resp(f"[worker output {model}]", model)

    return _responder


async def test_engine_remaps_credential_blocked_worker_model() -> None:
    """AC4: the blocked model (even explicitly overridden) never runs."""
    from chimera.config import (
        DeliberationOverrides,
        credential_fingerprint,
        model_credential_fingerprint,
    )
    from chimera.engine import Engine
    from tests.conftest import FakeGateway, dispatch_json

    cfg = _credential_config()
    blocked = cfg.defaults.default_worker  # catalog provider: openrouter (dead key)
    fallback = cfg.defaults.default_aggregator  # zai → live key
    assert model_credential_fingerprint(cfg, blocked) == credential_fingerprint(_DEAD_KEY)

    reg = ModelBlockRegistry(state_path=None)
    assert reg.record_failure(
        blocked, _AUTH_ERR, credential_fingerprint=model_credential_fingerprint(cfg, blocked)
    )
    set_shared_registry(reg)

    payload = dispatch_json(workers=[("worker_1", blocked), ("worker_2", blocked)])
    gw = FakeGateway(_preset_responder(payload))
    overrides = DeliberationOverrides(stage_models={"worker_1": blocked})
    result = await Engine(cfg, gw).deliberate("task", "simple", overrides=overrides)

    assert [w.model for w in result.trace.workers] == [fallback, fallback]
    assert result.trace.worker_failures == []
    assert result.answer == f"[merged answer from {fallback}]"


async def test_engine_keeps_worker_model_once_the_key_is_replaced() -> None:
    """Self-heal: a rotated credential restores the configured worker model."""
    from chimera.config import credential_fingerprint
    from chimera.engine import Engine
    from tests.conftest import FakeGateway, dispatch_json

    cfg = _credential_config()
    blocked = cfg.defaults.default_worker

    reg = ModelBlockRegistry(state_path=None)
    # Block recorded against a PREVIOUS key — stale for the current config.
    assert reg.record_failure(
        blocked, _AUTH_ERR, credential_fingerprint=credential_fingerprint("old-key")
    )
    set_shared_registry(reg)

    payload = dispatch_json(workers=[("worker_1", blocked), ("worker_2", blocked)])
    gw = FakeGateway(_preset_responder(payload))
    result = await Engine(cfg, gw).deliberate("task", "simple")

    assert [w.model for w in result.trace.workers] == [blocked, blocked]
    # …and the stale entry is cleared rather than left behind.
    assert not reg.is_blocked(blocked)
    assert reg.blocked() == set()


# ---------------------------------------------------------------------------
# Actionable CLI warning (DF-CHIMERA-V2-6, AC5)
# ---------------------------------------------------------------------------


def _failure_result(stage_id: str, model: str, error: str):  # type: ignore[no-untyped-def]
    from types import SimpleNamespace

    trace = SimpleNamespace(
        worker_failures=[
            SimpleNamespace(stage_id=stage_id, model=model, error=error)
        ]
    )
    return SimpleNamespace(trace=trace)


def _render_warnings(result, config) -> str:  # type: ignore[no-untyped-def]
    import io

    from rich.console import Console

    from chimera.cli.main import _print_worker_failures

    buf = io.StringIO()
    _print_worker_failures(result, Console(file=buf, width=200, no_color=True), config)
    return buf.getvalue()


def test_warning_names_provider_env_var_and_model_for_credential_failure(config) -> None:  # type: ignore[no-untyped-def]
    """AC5: the operator is told what to fix, not just that something broke."""
    config.api_keys["openrouter"] = _DEAD_KEY
    model = "openrouter/openai/gpt-5.6-sol"  # not in the fixture catalog → prefix fallback
    text = _render_warnings(_failure_result("worker_1", model, _AUTH_ERR), config)

    assert "worker_1" in text
    assert model in text
    assert "openrouter" in text
    assert "OPENROUTER_API_KEY" in text
    assert "excluded from selection" in text
    assert "User not found" in text  # the raw upstream text is still shown


def test_warning_prefers_the_configured_api_key_env(config) -> None:  # type: ignore[no-untyped-def]
    config.providers["openrouter"].api_key_env = "CUSTOM_OR_KEY"
    text = _render_warnings(
        _failure_result("worker_1", "openrouter/qwen/qwen3-coder", _AUTH_ERR), config
    )
    assert "CUSTOM_OR_KEY" in text
    assert "OPENROUTER_API_KEY" not in text


def test_warning_stays_raw_for_non_credential_failures(config) -> None:  # type: ignore[no-untyped-def]
    """Non-credential failures keep the previous (bounded) raw rendering."""
    text = _render_warnings(
        _failure_result("worker_2", "openrouter/qwen/qwen3-coder", _GUARDRAIL_ERR),
        config,
    )
    assert "worker_2" in text
    assert "guardrail" in text
    assert "API_KEY" not in text
    assert "fix:" not in text


def test_warning_truncates_a_huge_error_text(config) -> None:  # type: ignore[no-untyped-def]
    text = _render_warnings(
        _failure_result("worker_1", "openrouter/qwen/qwen3-coder", "boom " * 200), config
    )
    assert "..." in text
    assert "boom " * 60 not in text


def test_models_command_lists_blocked_models(config_file) -> None:  # type: ignore[no-untyped-def]
    """`chimera models` surfaces the exclusions + remedy (documented workflow)."""
    from click.testing import CliRunner

    from chimera.cli.main import main

    reg = ModelBlockRegistry(state_path=None)
    reg.record_failure(
        "openrouter/qwen/qwen3-coder", _AUTH_ERR, credential_fingerprint="fp-dead"
    )
    set_shared_registry(reg)

    result = CliRunner().invoke(main, ["-c", str(config_file), "models"])
    assert result.exit_code == 0, result.output
    assert "Blocked models" in result.output
    assert "openrouter/qwen/qwen3-coder (credential)" in result.output
    assert "OPENROUTER_API_KEY" in result.output


def test_models_command_is_quiet_when_nothing_is_blocked(config_file) -> None:  # type: ignore[no-untyped-def]
    from click.testing import CliRunner

    from chimera.cli.main import main

    set_shared_registry(ModelBlockRegistry(state_path=None))
    result = CliRunner().invoke(main, ["-c", str(config_file), "models"])
    assert result.exit_code == 0, result.output
    assert "Blocked models" not in result.output
