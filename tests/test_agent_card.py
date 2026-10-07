"""A2A-style agent discovery: GET /.well-known/agent-card.json (REV-CHIMERA-V2-20261005-2).

The card describes the agent (name/description/version/url from the same
sources /v1/health uses) and lists the MCP tool surface as A2A-style
``skills[]``. Discovery endpoints are public by convention (like /health), so
one test here proves the route answers with auth ENABLED and no credentials —
the negative control for "not behind require_api_key".
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera import __version__  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway  # noqa: E402

AGENT_CARD_PATH = "/.well-known/agent-card.json"

#: MCP tools the card must expose (src/chimera/mcp/server.py surface).
EXPECTED_SKILL_IDS = {"chimera_deliberate", "chimera_formations", "chimera_models"}


def _client(config):  # type: ignore[no-untyped-def]
    engine = Engine(config, FakeGateway())
    app = create_app(config=config, engine=engine)
    return TestClient(app)


def _auth_enabled_config():  # type: ignore[no-untyped-def]
    """CONFIG_DICT with auth enabled (list mode, NO keys configured).

    List mode keeps the check hermetic: ``verify_api_key`` never reads
    ``CHIMERA_API_KEY`` from the ambient environment, so a developer shell
    with that variable exported cannot turn the negative control green.
    An anonymous request is refused 401 before any handler runs.
    """
    cfg_dict = dict(CONFIG_DICT)
    cfg_dict["auth"] = {"enabled": True, "mode": "list", "keys": []}
    from chimera.config import ChimeraConfig

    return ChimeraConfig.model_validate(cfg_dict)


def test_agent_card_shape(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    r = client.get(AGENT_CARD_PATH)
    assert r.status_code == 200
    data = r.json()
    for key in ("name", "description", "version", "url", "capabilities", "skills"):
        assert key in data, f"agent card missing key: {key}"
    assert data["name"] == "chimera"
    assert "deliberation" in data["description"].lower()
    assert data["version"] == __version__


def test_agent_card_url_from_config(config) -> None:  # type: ignore[no-untyped-def]
    """``url`` is the configured server base URL (host/port the server binds)."""
    client = _client(config)
    data = client.get(AGENT_CARD_PATH).json()
    assert data["url"] == f"http://{config.server.host}:{config.server.port}"


def test_agent_card_skills_mirror_mcp_tools(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    data = client.get(AGENT_CARD_PATH).json()
    skills = data["skills"]
    assert isinstance(skills, list) and skills, "skills must be a non-empty list"
    assert {s["id"] for s in skills} == EXPECTED_SKILL_IDS
    for skill in skills:
        assert skill["name"] == skill["id"]
        assert skill["description"].strip(), f"empty description for {skill['id']}"
    deliberate = next(s for s in skills if s["id"] == "chimera_deliberate")
    # Description reuses the tool's own docstring, not a hand-copy.
    assert "multi-model deliberation" in deliberate["description"].lower()


class TestAgentCardOpenWithoutAuth:
    """The discovery endpoint is NOT behind require_api_key."""

    def test_anonymous_200_with_auth_enabled(self) -> None:
        client = _client(_auth_enabled_config())
        r = client.get(AGENT_CARD_PATH)
        assert r.status_code == 200
        assert r.json()["name"] == "chimera"

    def test_anonymous_200_with_ambient_env_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Even a present-but-unpresented env key must not change the verdict:
        # the route takes no credentials at all.
        monkeypatch.setenv("CHIMERA_API_KEY", "ambient-secret")
        client = _client(_auth_enabled_config())
        assert client.get(AGENT_CARD_PATH).status_code == 200

    def test_protected_sibling_still_401(self) -> None:
        """Negative control: the same client IS refused on a keyed route,
        proving the 200 above comes from the open route, not a broken gate."""
        client = _client(_auth_enabled_config())
        r = client.post("/v1/deliberate", json={"prompt": "hello"})
        assert r.status_code == 401
