"""DF-CHIMERA-V2-110: ``allowed_models`` ids are catalog-validated (HTTP 400).

Dogfood run 2026-11-16 (`chimera serve` on :8902) measured the defect this file
pins: ``POST /v1/deliberate`` with ``allowed_models: ["nonexistent/bogus-xyz"]``
returned **HTTP 500, body ``Internal Server Error`` (plain text, no JSON, no
request_id)`` in 7.99 s. ``worker_model`` and ``stage_models`` already rejected
the same class of client typo with an actionable 400, so one of the three
model-selecting fields was an opaque crash.

The contract now: ``allowed_models`` is a POOL RESTRICTION (it remaps every
worker stage to ``allowed_models[0]``), so every id must name a ``models:``
catalog entry. An id that does not is rejected with the same 400 contract as
the sibling override fields — BEFORE the dispatcher runs, so a rejected request
costs zero upstream calls (an ``auto`` dispatch is itself a billed call).
Membership is the only test: a declared-but-disabled entry keeps its shipped
behaviour, so the field never becomes stricter than documented.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import create_app  # noqa: E402
from chimera.config import ChimeraConfig, DeliberationOverrides  # noqa: E402
from chimera.engine import Engine, _apply_allowed_models  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json  # noqa: E402

BOGUS_MODEL = "nonexistent/bogus-xyz"
KNOWN_MODEL = "deepseek/deepseek-v4-flash"


def _resp(text: str, model: str, tok_in: int = 20, tok_out: int = 40) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=tok_in, tokens_output=tok_out)


def _resolving_responder(config: ChimeraConfig):  # type: ignore[no-untyped-def]
    """Responder that resolves every model through the catalog, like production.

    The real gateway starts each call with ``config.get_model(model)`` (an
    unguarded ``KeyError`` for an undeclared id) — that is the exact step that
    produced the plain-text 500. Reproducing it here means the pre-fix failure
    mode is the reported one, not a test-double artefact.
    """

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        config.get_model(model)  # KeyError for an unknown id, as in the gateway
        if response_format is not None:
            return _resp(dispatch_json(), model, 100, 200)
        joined = str(messages)
        if "Upstream outputs" in joined:
            return _resp("[merged]", model, 60, 90)
        return _resp(f"[worker {model}]", model, 20, 40)

    return responder


def _client(config: ChimeraConfig):  # type: ignore[no-untyped-def]
    gateway = FakeGateway(_resolving_responder(config))
    engine = Engine(config, gateway)
    app = create_app(config=config, engine=engine)
    return TestClient(app), gateway


# --------------------------------------------------------------------------- #
# AC1 + AC4: unknown id -> 400 naming it, before any upstream call
# --------------------------------------------------------------------------- #


def test_deliberate_allowed_models_unknown_id_returns_400(config) -> None:  # type: ignore[no-untyped-def]
    """Unknown ``allowed_models`` id -> HTTP 400 whose ``detail`` names it.

    Same contract family as ``worker_model``: FastAPI ``detail`` body (never an
    OpenAI ``error`` object), the offending id quoted, and the ``models:``
    catalog requirement taught. AC4: rejected BEFORE dispatch, so the gateway
    was never called — an ``auto`` dispatch would itself be a billed call.
    """
    client, gateway = _client(config)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "simple", "allowed_models": [BOGUS_MODEL]},
    )
    assert r.status_code == 400, r.text
    assert r.headers["content-type"].startswith("application/json"), r.headers
    body = r.json()
    assert "error" not in body, body
    detail = body["detail"]
    assert isinstance(detail, str), detail
    assert "allowed_models" in detail, detail
    assert BOGUS_MODEL in detail, detail
    assert "unknown model" in detail, detail
    # DF-CHIMERA-V2-61 wording family: the 400 teaches the catalog requirement.
    assert "catalog" in detail, detail
    assert "models:" in detail, detail
    assert gateway.calls == []  # zero upstream calls, zero billing


def test_deliberate_allowed_models_unknown_id_among_valid_returns_400(config) -> None:  # type: ignore[no-untyped-def]
    """A bogus id is rejected even when valid ids accompany it (no partial pool)."""
    client, gateway = _client(config)
    r = client.post(
        "/v1/deliberate",
        json={
            "prompt": "hi",
            "formation": "simple",
            "allowed_models": [KNOWN_MODEL, BOGUS_MODEL],
        },
    )
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert BOGUS_MODEL in detail, detail
    # The valid entry is not blamed for the bogus one.
    assert KNOWN_MODEL not in detail, detail
    assert gateway.calls == []


def test_deliberate_allowed_models_alias_and_canonical_both_validated(config) -> None:  # type: ignore[no-untyped-def]
    """A bogus id in the canonical pool is a 400 even when ``models`` is valid."""
    client, gateway = _client(config)
    r = client.post(
        "/v1/deliberate",
        json={
            "prompt": "hi",
            "formation": "simple",
            "models": [KNOWN_MODEL],
            "allowed_models": [BOGUS_MODEL],
        },
    )
    assert r.status_code == 400, r.text
    assert BOGUS_MODEL in r.json()["detail"], r.json()
    assert gateway.calls == []


# --------------------------------------------------------------------------- #
# AC2: a catalog-declared pool keeps working exactly as today
# --------------------------------------------------------------------------- #


def test_deliberate_allowed_models_known_id_still_restricts_pool(config) -> None:  # type: ignore[no-untyped-def]
    """A known id is NOT made stricter: every worker is remapped into the pool.

    The documented semantics of the field (docs/OPENAI_API.md) are unchanged —
    a one-entry pool puts every worker stage on that entry.
    """
    client, gateway = _client(config)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "simple", "allowed_models": [KNOWN_MODEL]},
    )
    assert r.status_code == 200, r.text
    workers = [s for s in r.json()["trace"]["stages"] if s["kind"] == "worker"]
    assert workers
    assert all(s["model"] == KNOWN_MODEL for s in workers), workers
    assert gateway.calls  # the real success path still deliberates


def test_deliberate_allowed_models_disabled_catalog_entry_accepted(config) -> None:  # type: ignore[no-untyped-def]
    """Membership is the only test: a DECLARED-but-disabled id is not a 400.

    AC2's boundary. ``allowed_models`` never was an enabled-check document, so
    a pool naming a declared entry must not start failing at validation — the
    rest of the engine keeps its shipped behaviour for that id.
    """
    raw = {**CONFIG_DICT, "models": {name: dict(entry) for name, entry in CONFIG_DICT["models"].items()}}
    raw["models"]["deepseek/deepseek-v4-flash"] = {
        **raw["models"][KNOWN_MODEL],
        "enabled": False,
    }
    cfg = ChimeraConfig.model_validate(raw)
    assert cfg.models[KNOWN_MODEL].enabled is False  # premise: declared, disabled

    client, _gateway = _client(cfg)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "simple", "allowed_models": [KNOWN_MODEL]},
    )
    # NOT a validation 400: the id IS in the catalog.
    assert r.status_code != 400, r.text
    assert "allowed_models references unknown model" not in r.text


# --------------------------------------------------------------------------- #
# Engine-level defence: the validation lives at BOTH seams
# --------------------------------------------------------------------------- #


def test_apply_allowed_models_rejects_unknown_id(config) -> None:  # type: ignore[no-untyped-def]
    """``_apply_allowed_models`` itself refuses an unknown id (wording family).

    The API mapping depends on this being a ``ValueError``; a heavier exception
    type would escape the handler chain and become the 500 again.
    """

    class _Dispatch:
        formation = type("_F", (), {"stages": []})()
        dispatch_note = ""

        def worker_prompt_for(self, stage_id):  # type: ignore[no-untyped-def]
            return None

    with pytest.raises(ValueError, match=r"allowed_models references unknown model\(s\)") as excinfo:
        _apply_allowed_models(_Dispatch(), [BOGUS_MODEL], config)  # type: ignore[arg-type]
    assert BOGUS_MODEL in str(excinfo.value)


async def test_engine_deliberate_rejects_unknown_allowed_models_before_dispatch(config) -> None:  # type: ignore[no-untyped-def]
    """The engine rejects before the dispatcher: no gateway call at all.

    This is the surface every caller shares (REST, OpenAI-compat, web UI, CLI,
    MCP). An ``auto`` formation would otherwise pay for a dispatcher call first.
    """
    gateway = FakeGateway(_resolving_responder(config))
    engine = Engine(config, gateway)
    with pytest.raises(ValueError, match="allowed_models"):
        await engine.deliberate(
            "hi",
            "auto",
            overrides=DeliberationOverrides(allowed_models=[BOGUS_MODEL]),
        )
    assert gateway.calls == []


# --------------------------------------------------------------------------- #
# AC3: never a bare plain-text "Internal Server Error"
# --------------------------------------------------------------------------- #


def test_deliberate_unhandled_error_returns_json_envelope(config) -> None:  # type: ignore[no-untyped-def]
    """An unhandled failure is a JSON body with ``detail`` + ``request_id``.

    The reported defect body was the bare plain-text string
    ``Internal Server Error`` — no JSON, no correlation id. A 5xx that still
    happens must stay machine-readable and traceable to the logged traceback.
    """

    class _ExplodingEngine:
        async def deliberate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom: simulated unhandled engine failure")

    app = create_app(config=config, engine=_ExplodingEngine())  # type: ignore[arg-type]
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "simple"})

    assert r.status_code == 500, r.text
    assert r.text != "Internal Server Error"  # not Starlette's plain-text default
    assert r.headers["content-type"].startswith("application/json"), r.headers
    body = r.json()
    assert set(body) >= {"detail", "request_id"}, body
    assert body["detail"] == "Internal Server Error", body
    assert body["request_id"] == r.headers["X-Request-Id"], (body, r.headers)
    # The exception text is not leaked to the caller.
    assert "boom" not in r.text
