"""RED-check the version-field removal: assert the saved state file has NO version key."""

import json
import time

from chimera.blocked_models import ModelBlockRegistry


def test_state_file_has_no_version_field(tmp_path) -> None:
    path = tmp_path / "blocked.json"
    reg = ModelBlockRegistry(state_path=path, clock=lambda: 100.0)
    reg.record_failure("model/x", "Error code: 401 - invalid api key")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "version" not in data, f"version field still written: {sorted(data)}"
    assert "blocked_until_epoch" in data


def test_loader_ignores_legacy_version_field(tmp_path) -> None:
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
