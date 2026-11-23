#!/bin/bash
# Exact documented stub command from docs/CONFIG.md § Minimal local fixture
# (mirror; README.md:973-976 points readers here). cwd must be the repo root
# so `from tests.test_gateway_custom_base_url import _compat_stub` resolves.
cd /home/kara/chimera-v2
/home/kara/chimera-v2/.venv/bin/python -u -c 'from threading import Event; from tests.test_gateway_custom_base_url import _compat_stub; exec("with _compat_stub(port=18081) as (url, seen):\n    print(url, flush=True)\n    Event().wait()")'
