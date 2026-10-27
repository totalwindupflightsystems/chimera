# README release review — 2026-10-27

Baseline: v0.2.8 (`ba900827c4516ecc699efcb66d24e85aec90e0b9`), published 2026-10-25.
Review tip: `ed8bd3f44efcb7876b4049ea98ac60a9a2a582dc`.
Scope: README.md compared with the post-v0.2.8 source, configuration templates, release workflow, and CLI serialization.

Evidence

- `git rev-list --count v0.2.8..HEAD` → `43` before this review commit.
- `grep -c '^  speed:' chimera.yaml.example` → `1`.
- `grep -n 'probe_mcp_stdio.py --formation=' .github/workflows/ci.yml` → the release workflow probes `simple` and `speed`.
- `.venv/bin/python -m pytest tests/test_release_template_formations.py -q` → `1 passed`.
- `grep -n 'Top-level.*answer_degraded' README.md` → the CLI documentation identifies `answer_degraded` and `answer_error` as top-level fields.
- `src/chimera/cli/main.py` serializes `answer_degraded` and `answer_error` as siblings of `answer` and `trace`; the README example now follows that shape.
- `grep -ci 'gemini-2.5' chimera.yaml.example chimera.yaml.fleet` → `0 0`.
- `curl -s http://localhost:8765/v1/models | jq -r '.data[].id' | grep -i gemini` lists Gemini 3.x IDs and no Gemini 2.5 ID; the README Providers table now names the served Gemini 3.x families.

Corrections made in the same review

1. Moved `answer_degraded` and `answer_error` out of the nested `trace` example object to the top level.
2. Replaced the stale Google provider table entry `Gemini 2.5 Flash` with the Gemini 3.x families present in the catalog.
3. Kept the release-surface review note in README.md, with this artifact as the source-grounded record.

The separate README-8 structure finding remains scoped to its own Build and Limits/Known Gaps sections.
