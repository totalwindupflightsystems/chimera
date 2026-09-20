"""INT-API-004: ``GET /v1/models`` must serve an OpenAI ListModelsResponse.

The route used to return a bare ``{model_id: {...}}`` map. That is not a
ListModelsResponse: the official SDK's ``client.models.list()`` reads
``page.data``, which the map shape leaves ``None``, so the call raised
``TypeError: object of type 'NoneType' has no len()`` and every proxy/UI that
enumerates models through the SDK broke with no hint that the route was
non-standard.

The envelope is the fix (``object`` / ``data`` / ``catalog``). The legacy
keyed map stays reachable as the additive ``catalog`` key, so this file pins
BOTH: the OpenAI shape AND the unchanged chimera field set/values.
"""

from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import _catalog_entry_payload, create_app  # noqa: E402
from chimera.config import DEFAULT_COST_RATES, ChimeraConfig  # noqa: E402
from chimera.engine import Engine, _stage_cost  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway  # noqa: E402

#: The pre-envelope per-model field set. ``data[]`` entries and ``catalog``
#: entries must BOTH carry exactly these keys (data adds the 4 envelope keys).
_LEGACY_FIELDS = (
    "categories",
    "cost_tier",
    "provider",
    "enabled",
    "cost_per_1k_input",
    "cost_per_1k_output",
)
_ENVELOPE_FIELDS = ("id", "object", "created", "owned_by")

#: The two served price fields and the ``ModelEntry`` method the BILLER reads
#: for each (``engine._stage_cost`` calls these exact methods). The served
#: value is the effective rate, so the expected value is the method's return,
#: never the raw config attribute (CH-GAP-055).
_RATE_METHOD = {
    "cost_per_1k_input": "cost_rate_input",
    "cost_per_1k_output": "cost_rate_output",
}


def _client(config):  # type: ignore[no-untyped-def]
    def responder(model, messages, response_format=None, **kw):
        return GatewayResponse(text=f"worker {model}", model=model,
                               tokens_input=1, tokens_output=1)

    app = create_app(config=config, engine=Engine(config, FakeGateway(responder)))
    return TestClient(app)


def _fetch(client):  # type: ignore[no-untyped-def]
    r = client.get("/v1/models")
    assert r.status_code == 200
    return r.json()


# --------------------------------------------------------------------------- #
# Top-level envelope shape
# --------------------------------------------------------------------------- #


def test_models_top_level_is_list_envelope(config) -> None:  # type: ignore[no-untyped-def]
    """Top-level keys are exactly object/data/catalog — no model id leaks out."""
    body = _fetch(_client(config))

    assert set(body) == {"object", "data", "catalog"}, body.keys()
    assert body["object"] == "list"
    assert isinstance(body["data"], list)
    assert isinstance(body["catalog"], dict)
    # The old shape put model ids at the top level; none may remain.
    assert not any(k in body for k in config.models), [
        k for k in config.models if k in body
    ]


def test_models_is_json_serializable_with_no_none_data(config) -> None:  # type: ignore[no-untyped-def]
    """A round-trip must preserve ``data`` as a populated list (SDK premise)."""
    body = _fetch(_client(config))
    round_tripped = json.loads(json.dumps(body))

    assert isinstance(round_tripped["data"], list)
    assert len(round_tripped["data"]) == len(config.models) > 0


# --------------------------------------------------------------------------- #
# data[] entries: OpenAI object shape + chimera fields
# --------------------------------------------------------------------------- #


def test_models_data_entries_are_openai_model_objects(config) -> None:  # type: ignore[no-untyped-def]
    """Every entry has id / object == 'model' / int created / str owned_by."""
    body = _fetch(_client(config))

    assert body["data"], "empty data[] proves nothing"
    for entry in body["data"]:
        assert isinstance(entry, dict)
        assert set(entry) == set(_ENVELOPE_FIELDS) | set(_LEGACY_FIELDS)
        assert isinstance(entry["id"], str) and entry["id"]
        assert entry["object"] == "model"
        assert isinstance(entry["created"], int)
        assert not isinstance(entry["created"], bool)  # bool is an int subclass
        assert isinstance(entry["owned_by"], str) and entry["owned_by"]
        assert set(entry["categories"]) == set(
            config.models[entry["id"]].categories
        )


def test_models_ids_match_catalog_keys_and_config(config) -> None:  # type: ignore[no-untyped-def]
    """data ids == catalog keys == cfg.models keys, same order (dict order)."""
    body = _fetch(_client(config))

    data_ids = [e["id"] for e in body["data"]]
    assert data_ids == list(body["catalog"])
    assert data_ids == list(config.models)
    assert len(data_ids) == len(set(data_ids))  # no duplicate ids


def test_models_data_values_equal_catalog_and_config(config) -> None:  # type: ignore[no-untyped-def]
    """Additive only: data[] and catalog carry the SAME chimera values as today."""
    body = _fetch(_client(config))
    by_id = {e["id"]: e for e in body["data"]}

    for model_id, cfg_entry in config.models.items():
        catalog_entry = body["catalog"][model_id]
        data_entry = by_id[model_id]

        for field in _LEGACY_FIELDS:
            # CH-GAP-055: cost_per_1k_* are served as the EFFECTIVE rate the
            # biller charges (explicit rate when declared, else the entry's
            # cost-tier default), so the expectation for those two fields is
            # the ModelEntry method ``engine._stage_cost`` reads — the raw
            # field is ``None`` for every tier-priced id. Every other legacy
            # field still mirrors the raw config value.
            expected = (
                getattr(cfg_entry, _RATE_METHOD[field])()
                if field in _RATE_METHOD
                else getattr(cfg_entry, field)
            )
            assert catalog_entry[field] == expected, field
            assert data_entry[field] == catalog_entry[field], field

        # owned_by mirrors the configured provider string.
        assert data_entry["owned_by"] == cfg_entry.provider


def test_models_iterating_data_yields_the_legacy_id_set(config) -> None:  # type: ignore[no-untyped-def]
    """Iterating data[] yields the same id SET the old map exposed as keys."""
    client = _client(config)
    body = _fetch(client)

    served = {e["id"] for e in body["data"]}
    assert served == set(body["catalog"])
    assert "deepseek/deepseek-chat" in served  # a known fixture model
    assert body["catalog"]["deepseek/deepseek-chat"]["cost_tier"] == "budget"


# --------------------------------------------------------------------------- #
# CH-GAP-055: the served price is the EFFECTIVE (explicit-else-tier) rate
# --------------------------------------------------------------------------- #

#: Live-null ids measured on the running service 2026-09-19: they declare a
#: ``cost_tier`` and no explicit ``cost_per_1k_*``, and the engine billed them
#: at the tier default while the route served ``null``. Pinned here with the
#: catalog shape the live ``chimera.yaml`` carries (same providers, same
#: tiers) so the fix stays anchored to the real defect, not to a fixture that
#: happens to be convenient.
_LIVE_NULL_IDS = {
    "router9/ds/deepseek-v4-flash": "budget",      # → 0.00014 / 0.00028
    "router9/ds/deepseek-v4-pro": "budget",
    "router9/mmx/MiniMax-M3": "budget",
    "router9/xai/grok-4": "standard",              # → 0.0005 / 0.0015
    "router9/openrouter/x-ai/grok-4.6": "premium",  # → 0.003 / 0.015
}
#: One of the 7 live-null ids plus an explicit-rate id, an unknown-tier id and
#: an id with neither rates nor a declared tier.
_CHGAP055_CONFIG: dict = {
    "providers": {
        "router9": {"base_url": "https://router9.invalid/v1"},
        "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
    },
    "models": {
        # (a) explicit rates declared → explicit must still win
        "deepseek/deepseek-v4-flash": {
            "categories": {"code": 88.0},
            "cost_tier": "budget",
            "provider": "openrouter",
            "cost_per_1k_input": 0.00014,
            "cost_per_1k_output": 0.00028,
        },
        # (b) live-null id: tier declared, no explicit rates
        "router9/ds/deepseek-v4-flash": {
            "categories": {"code": 85.0},
            "cost_tier": "budget",
            "provider": "router9",
        },
        # (b') live-null id on a different tier
        "router9/openrouter/x-ai/grok-4.6": {
            "categories": {"reasoning": 92.0},
            "cost_tier": "premium",
            "provider": "router9",
        },
        # (b'') live-null id on the standard tier
        "router9/xai/grok-4": {
            "categories": {"code": 70.0},
            "cost_tier": "standard",
            "provider": "router9",
        },
        # (b''') the remaining measured null ids, pinned so the whole live set
        # from the defect report stays covered (budget tier, router9 provider).
        "router9/ds/deepseek-v4-pro": {
            "categories": {"code": 90.0, "reasoning": 93.0},
            "cost_tier": "budget",
            "provider": "router9",
        },
        "router9/mmx/MiniMax-M3": {
            "categories": {"code": 80.0},
            "cost_tier": "budget",
            "provider": "router9",
        },
        # (c) neither explicit rates nor a declared tier → "standard" default
        "router9/legacy/model-no-tier": {
            "categories": {"code": 50.0},
            "provider": "router9",
        },
        # (c') a tier DEFAULT_COST_RATES does not know → "standard" default
        "router9/legacy/model-unknown-tier": {
            "categories": {"code": 50.0},
            "cost_tier": "platinum",
            "provider": "router9",
        },
    },
    "defaults": {
        "dispatcher": "deepseek/deepseek-v4-flash",
        "default_worker": "deepseek/deepseek-v4-flash",
        "default_aggregator": "deepseek/deepseek-v4-flash",
    },
    "formations": {"simple": {"workers": 2, "aggregator": "default"}},
}


def _chgap055_config() -> ChimeraConfig:
    return ChimeraConfig.model_validate(copy.deepcopy(_CHGAP055_CONFIG))


def _named(config: ChimeraConfig, model_id: str):  # type: ignore[no-untyped-def]
    """The ``ModelEntry`` behind *model_id*, resolved the way the biller does."""
    return config.get_model(model_id)


def test_served_price_is_never_null_for_a_catalog_entry(config) -> None:  # type: ignore[no-untyped-def]
    """AC1 — every served entry prices, and the number is the BILLED rate."""
    body = _fetch(_client(config))

    assert body["catalog"], "empty catalog proves nothing"
    for model_id, payload in body["catalog"].items():
        entry = _named(config, model_id)
        assert payload["cost_per_1k_input"] is not None, model_id
        assert payload["cost_per_1k_output"] is not None, model_id
        for field, method in _RATE_METHOD.items():
            assert payload[field] == getattr(entry, method)(), (model_id, field)
            assert isinstance(payload[field], float), (model_id, field)


def test_live_null_ids_serve_the_tier_default_they_are_billed_at() -> None:
    """(b) + AC1 — the measured nulls now serve ``DEFAULT_COST_RATES[tier]``."""
    config = _chgap055_config()
    body = _fetch(_client(config))

    assert body["catalog"]["router9/ds/deepseek-v4-flash"]["cost_per_1k_input"] == (
        pytest.approx(0.00014)
    )
    assert body["catalog"]["router9/ds/deepseek-v4-flash"]["cost_per_1k_output"] == (
        pytest.approx(0.00028)
    )

    for model_id, tier in _LIVE_NULL_IDS.items():
        payload = body["catalog"][model_id]
        rate_in, rate_out = DEFAULT_COST_RATES[tier]
        assert payload["cost_tier"] == tier
        assert payload["cost_per_1k_input"] == pytest.approx(rate_in), model_id
        assert payload["cost_per_1k_output"] == pytest.approx(rate_out), model_id
        # Premise: the config really declares no explicit rate on these ids,
        # so the served number can only come from the tier fallback.
        entry = _named(config, model_id)
        assert entry.cost_per_1k_input is None, model_id
        assert entry.cost_per_1k_output is None, model_id


def test_explicit_rates_still_win_over_the_tier_default() -> None:
    """(a) + AC2 — a declared rate is served verbatim, tier never overrides it."""
    config = _chgap055_config()
    body = _fetch(_client(config))
    entry = _named(config, "deepseek/deepseek-v4-flash")

    # Premise: this one DECLARES rates (and declares the budget ones, so a
    # mis-wired fallback would silently produce the same numbers).
    assert entry.cost_per_1k_input == 0.00014
    assert entry.cost_per_1k_output == 0.00028
    # …so prove the win with a differing pair, on a copy the route actually serves.
    config.models["deepseek/deepseek-v4-flash"].cost_per_1k_input = 0.0099
    config.models["deepseek/deepseek-v4-flash"].cost_per_1k_output = 0.0299
    body = _fetch(_client(config))

    assert body["catalog"]["deepseek/deepseek-v4-flash"]["cost_per_1k_input"] == (
        pytest.approx(0.0099)
    )
    assert body["catalog"]["deepseek/deepseek-v4-flash"]["cost_per_1k_output"] == (
        pytest.approx(0.0299)
    )
    assert body["catalog"]["deepseek/deepseek-v4-flash"]["cost_per_1k_input"] == (
        pytest.approx(entry.cost_rate_input())
    )
    _ = entry


def test_missing_or_unknown_tier_falls_back_to_standard() -> None:
    """(c) — neither rates nor a usable tier → the documented standard default."""
    config = _chgap055_config()
    body = _fetch(_client(config))
    standard_in, standard_out = DEFAULT_COST_RATES["standard"]

    neither = body["catalog"]["router9/legacy/model-no-tier"]
    assert neither["cost_tier"] == "standard"
    assert neither["cost_per_1k_input"] == pytest.approx(standard_in)
    assert neither["cost_per_1k_output"] == pytest.approx(standard_out)

    unknown = body["catalog"]["router9/legacy/model-unknown-tier"]
    assert unknown["cost_tier"] == "platinum"  # the declared label is served…
    assert unknown["cost_per_1k_input"] == pytest.approx(standard_in)  # …billed
    assert unknown["cost_per_1k_output"] == pytest.approx(standard_out)


def test_served_price_equals_the_billed_price_via_engine_stage_cost() -> None:
    """CH-GAP-055's actual contract: served rate == ``engine._stage_cost`` rate.

    The served number is only correct if it is what the biller charges, so
    drive the real billing helper (the one ``engine._stage_cost`` uses to turn
    rates + tokens into dollars) for every served id and assert the served
    rate reproduces it exactly. This is the cross-check that would have caught
    the original defect: pre-fix the route served ``None`` for these ids while
    ``_stage_cost`` charged the tier rate.
    """
    config = _chgap055_config()
    body = _fetch(_client(config))

    for model_id, payload in body["catalog"].items():
        charged = _stage_cost(model_id, config, tokens_input=1000, tokens_output=1000)
        served = (
            payload["cost_per_1k_input"] * 1000 / 1000.0
            + payload["cost_per_1k_output"] * 1000 / 1000.0
        )
        assert served == pytest.approx(charged), model_id
        assert charged > 0.0, model_id


def test_catalog_entry_payload_prices_every_shape(config) -> None:  # type: ignore[no-untyped-def]
    """Unit level of the same contract: the payload helper itself never nulls."""
    for model_id, entry in config.models.items():
        payload = _catalog_entry_payload(entry)
        assert payload["cost_per_1k_input"] == entry.cost_rate_input(), model_id
        assert payload["cost_per_1k_output"] == entry.cost_rate_output(), model_id
        assert payload["cost_per_1k_input"] is not None, model_id
        assert payload["cost_per_1k_output"] is not None, model_id


def test_shared_fixture_catalog_prices_through_the_route(config) -> None:  # type: ignore[no-untyped-def]
    """The repo-wide ``config`` fixture (no explicit rates anywhere) prices too."""
    body = _fetch(_client(config))

    explicit_free = [
        model_id
        for model_id, entry in config.models.items()
        if entry.cost_per_1k_input is None
    ]
    assert explicit_free, (
        "fixture premise: at least one model must declare no explicit rate, "
        "or this test cannot observe the fallback"
    )
    for model_id in explicit_free:
        entry = config.models[model_id]
        payload = body["catalog"][model_id]
        tier = entry.cost_tier
        assert payload["cost_per_1k_input"] == DEFAULT_COST_RATES[tier][0], model_id
        assert payload["cost_per_1k_output"] == DEFAULT_COST_RATES[tier][1], model_id


def test_shared_fixture_sanity_check_matches_config_dict() -> None:
    """Premise guard: the imported shared fixture still has no explicit rates.

    ``CONFIG_DICT`` is imported only so a future edit that starts declaring
    explicit rates there fails loudly here instead of silently weakening the
    fallback coverage above.
    """
    for model_id, raw in CONFIG_DICT["models"].items():
        assert raw.get("cost_per_1k_input") is None, model_id
        assert raw.get("cost_per_1k_output") is None, model_id
