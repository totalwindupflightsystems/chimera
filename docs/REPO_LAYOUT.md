# Repository layout

What is tracked at the repository root and what is deliberately local-only. The
package/test tree itself is described in `AGENTS.md` under *Project Structure*;
this page covers the root entries and the exceptions a reader cannot infer from
a directory listing (CLN-1).

## Tracked root entries

| Entry | Contents |
|-------|----------|
| `src/` | The `chimera` package (engine, dispatcher, aggregator, api/, web/, cli/) |
| `tests/` | pytest suite — flat `test_*.py`, plus `integration/` and `compat/` |
| `scripts/` | Ops helpers: `smoke_live.py`, `push_remotes.py`, `model_sync.py`, … |
| `docs/` | Guides + the docs index (`docs/README.md`) |
| `specs/` | Design specs |
| `skills/` | Bundled skill definitions |
| `bin/` | MCP shims (`chimera-mcp-hermes`, `chimera-mcp-wrapper`) |
| `.github/` | CI workflow, issue/PR templates |
| `.gitreins/` | Quality-harness config, guard logs, verdict history |
| `.coding-hermes/` | Coding-hermes board (`board/*.jsonl`) and tick log |
| `.memory-bank/` | Project context docs (brief, tech/active context, progress) |
| `.vfs/` | Hilo manifest (`.vfs/graph/` is local cache and is gitignored) |
| `.actrc` | `act` local-CI runner config (runner-image pin) |
| `.gitleaks.toml` | Secret-scanning config |
| `.gitignore` | Ignore rules |
| `Dockerfile`, `Dockerfile.dev`, `docker-compose.yml` | Container builds |
| `pyproject.toml`, `uv.lock` | Packaging and the locked dependency set |
| `chimera.yaml.example`, `chimera.yaml.docker` | Shipped config templates |
| `AGENTS.md`, `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE` | Project documentation |

## Intentional exceptions

- **`chimera.yaml` is untracked and gitignored** (DF-CHIMERA-0916B-4). The
  systemd unit points `Environment=CHIMERA_CONFIG` at the repo-root path, so the
  live file stays on disk here; a fresh clone has none and needs
  `chimera config init` before `chimera serve` will boot.
- **`chimera.yaml.docker` and `chimera.yaml.example` are tracked** because the
  wheel force-includes both
  (`pyproject.toml` → `[tool.hatch.build.targets.wheel.force-include]`), so a
  release build needs them present in the checkout.
- **`.vfs/`, `.gitreins/`, `.coding-hermes/` and `.memory-bank/` are tracked
  harness state**, not junk: their config, board, manifest and history files are
  versioned on purpose. The derived caches *below* them (`.vfs/graph/`,
  `.gitreins/logs/`, `.gitreins/history/`) are gitignored and rebuildable.
- **No `_foreman_*.py` scratch files belong at the root.** Four tracked 33-byte
  foreman run leftovers (the `_foreman_` prefix with `check_duckbrain`,
  `check_scheduler`, `set_cooldown` and `verify_cooldown` suffixes — named
  pattern-first here on purpose, so `git grep` for the removed paths stays empty
  at HEAD) were deleted by CLN-1; keep foreman/fleet run scratch outside the
  repo. `tests/test_repo_hygiene.py` fails if one is tracked again.

## Ignore-rule policy

`.gitignore` lists the **class** an artifact belongs to (`.vfs/graph/`,
`.gitreins/logs/`, `dagger.db*`) rather than one live filename per artifact, so
a new cache file cannot reintroduce an untracked entry in `git status`. When a
new artifact class appears, add the class rule — not the filename.
