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

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway  # noqa: E402

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
            assert catalog_entry[field] == getattr(cfg_entry, field), field
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
