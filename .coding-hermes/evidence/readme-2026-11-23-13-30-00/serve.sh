#!/bin/bash
# Documented serve leg: README fixture recipe -> docs/CONFIG.md § minimal-local-fixture.
# serve binds 18082 (fixture port+1 per the doc's separation rule).
export CHIMERA_LOCAL_FIXTURE_KEY=local-fixture-only
exec /home/kara/chimera-v2/.venv/bin/chimera --config /home/kara/.hermes/stand-in/readme/chimera-v2/run/e2e/local-fixture.yaml serve --host 127.0.0.1 --port 18082
