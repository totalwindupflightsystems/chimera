# DEPS-008 — Python dependency refresh record (2026-10-01)

Scope: `.venv` had 21 outdated packages (supervisor dep-scan 2026-09-30). Worker refreshed all
in-bounds drift in 4 groups; every landing verified with full suite (1916 passed / 62 skipped /
0 failed), `pip check` clean, `ruff check .` clean.

## Groups landed

1. `de355aa` — minor/patch drift: boto3/botocore 1.43.106, charset-normalizer 3.5.2,
   coverage 7.16.2, cryptography 50.0.2, fastapi 0.142.2, filelock 4.0.8, litellm 1.99.4
   (max of the `<1.100` cap), platformdirs 4.12.2, pyjwt 2.15.1, python-dotenv 1.2.4,
   regex 2026.9.29, ruff 0.16.9, sse-starlette 3.5.0, uvicorn 0.54.0, uvloop 0.23.0.
2. `c9b202a` — openai 2.44.0 -> 2.54.0. **openai 3.x root cause: bound-blocked** — litellm 1.99.4
   declares `openai<3` in its consumer metadata, and litellm itself is held `<1.100` by the
   load-bearing pyproject cap, so 3.x cannot resolve without breaking litellm.
3. `7aec34c` — mcp 1.28.1 -> 1.30.0. **mcp 2.x root cause: bound-blocked** — pyproject.toml caps
   `mcp>=1.0.0,<2.0` in main deps, the full extra, and the mcp extra; DEPS-008 rules forbid
   crossing a bound without removing the cap first (a separate decision, not this row).
4. `ae3fb58` — huggingface-hub 1.32.0 -> 1.33.0. **2.0.0 root cause: bound-blocked** —
   tokenizers' installed wheel metadata declares `huggingface-hub>=0.16.4,<2.0`.

## Remaining outdated census (post-refresh, 2026-10-01)

9 packages remain outdated; every one is either bound-blocked or a transitive/tooling-only
item with no functional impact:

| Package | Current | Latest | Reason not bumped |
|---|---|---|---|
| huggingface_hub | 1.33.0 | 2.0.0 | bound-blocked (tokenizers `<2.0`) |
| importlib_metadata | 8.9.0 | 9.0.1 | transitive; Python 3.11 backport pkg, no impact |
| litellm | 1.99.4 | 1.103.2 | bound-blocked (pyproject `<1.100` cap is load-bearing) |
| mcp | 1.30.0 | 2.2.0 | bound-blocked (pyproject `<2.0` cap) |
| multidict | 6.9.1 | 7.0.0 | transitive (aiohttp); major, no consumer pressure |
| openai | 2.54.0 | 3.22.1 | bound-blocked (litellm requires `openai<3`) |
| pycodestyle | 2.12.1 | 2.15.0 | transitive tooling (pycodestyle via flake8-class lint); no impact |
| pydantic_core | 2.46.5 | 2.49.0 | transitive (pinned by pydantic resolution); no impact |
| pyflakes | 3.2.0 | 4.0.1 | tooling-only; ruff is the repo linter, pyflakes unused directly |

## Re-opening the majors (future decision, not this row)

To take mcp 2.x or openai 3.x, the owning caps must be deliberately lifted and the consumer
call sites verified: remove the `mcp<2` / `litellm<1.100` pyproject caps, then re-verify
litellm gateway paths and the MCP stdio probe (`scripts/probe_mcp_stdio.py`) on the bumped
stack. That is a deliberate consumer-cap decision beyond DEPS-008's "refresh in-bounds only"
contract.
