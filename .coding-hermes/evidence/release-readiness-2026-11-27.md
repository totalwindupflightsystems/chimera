# Release readiness sweep — 2026-11-27

Target: totalwindupflightsystems/chimera (canonical checkout /home/kara/chimera-v2)
Release remote: github git@github.com:totalwindupflightsystems/chimera.git
Mirror: origin git@gitlab.readydedis.com:totalwindup/chimera.git
Default branch: main
Candidate measured: 90ddc5fb94777d6ece5ecd4af08af23292e116a3
Candidate parity: github/main = origin/main = candidate

Decision: NO CUT. Proposed semver is v0.4.0 (one material feat and no verified breaking change), but the repository version surface is still 0.3.0, the Unreleased changelog is not promoted, no exact-candidate GitReins verdict exists, and the owner authorization for a new release/version is not present. Do not create a tag or GitHub Release.

Census baseline and materiality

Remote v0.3.0 peeled tag commit: 57e298c1d96dc7f90d06f9e31d3c34ec5bdbd9b5; annotated tag object: 917969f7d26f93a2f8af73bb815be1777bdd2126. The tag is reachable from candidate. Range: 57e298c1d96dc7f90d06f9e31d3c34ec5bdbd9b5..90ddc5fb94777d6ece5ecd4af08af23292e116a3.

Counts: 73 commits including merges; 70 non-merge commits. Subject-only conventional categories across non-merges: feat=1, fix=11, chore=14, docs=7, nonconventional=37. No subject `!` breaking marker and no `BREAKING CHANGE:` footer were found. The feat is material product work: a99ede4 adds retry logging/metrics in src/chimera/gateway.py and src/chimera/metrics.py. Product-path commits also include 026e167 (chat timeout), 2bed55f (retry jitter), and 0c1e24f (quota-dead auto dispatch classification). Proposed bump: minor, v0.4.0; not a tag authorization.

Version and release tooling

pyproject.toml and src/chimera/__init__.py both still declare 0.3.0. CHANGELOG.md has a non-empty [Unreleased] section naming the post-0.3.0 fixes. No Makefile release target, GoReleaser file, or scripts/release publisher exists. The repository-owned publication path is .github/workflows/ci.yml: a v* tag builds wheel and sdist, runs the acceptance gate, uploads to PyPI, then runs release verification. Therefore a future authorized cut must use the tag-triggered workflow and must not also run gh release create as a second publisher.

The repository-owned version checker passes for v0.3.0 and refuses v0.3.1 while the tree declares 0.3.0. The existing v0.3.0 acceptance checker refuses because its evidence graded f7cf034 while the tag peels to 57e298c (72 commits apart); new acceptance evidence must be graded at the exact future tag target.

Build evidence

In a detached worktree at the exact candidate, uv build --wheel --sdist succeeded. Artifacts: chimera_deliberation-0.3.0-py3-none-any.whl (1,264,273 bytes, sha256 b07b8acf798d2225d4fa53c9d5341e079bfca81f44a284875e11d7ab61179b9b) and chimera_deliberation-0.3.0.tar.gz (4,463,866 bytes, sha256 814523ee40683ddd78c0bb0357941e0985a5af7ded942d33be970e8e16dd8869). This proves the current 0.3.0 package build path, not readiness for v0.4.0.

CI evidence

GitHub push run 45966810099 is completed/success on the exact candidate 90ddc5fb94777d6ece5ecd4af08af23292e116a3. Jobs: lint success; test (3.11), test (3.12), test (3.13) success; integration success; packaging-smoke success; publish skipped; release-verify skipped because this was a branch push. Scheduled run 46032511339 is also completed/success on the same SHA. Tag workflow publication and release-verify remain untested for the proposed next version.

GitReins and dogfood

No persisted GitReins verdict names the exact candidate. The most recent persisted verdicts grade ancestor commits, including 0ded9dab, 8bf368a, and cc53820; the current .gitreins/verdicts/verdict.json names 49e3805c. This gate is UNVERIFIED, not green.

Latest dogfood evidence is partial, not a fresh full release battery: docs/dogfood/2026-11-26-150341-install-harvest.md records fresh-install/native-tests/lint/Docker-build/upgrade cells but an act setup failure with unattributed cause, skipped Docker deploy/chaos shutdown, and an unverified ci-act cell. The committed dogfood log records one degraded live deliberation against commit c47fbe8, while the live process currently reports 789ff3a. No exact-candidate full dogfood battery is available.

Deployment and posture

Live listener 127.0.0.1:8765 is pid 2126244 running commit 789ff3a and version 0.3.0. 789ff3a is an ancestor of candidate, and the candidate delta over runtime product paths (src, packaging, Docker/config, and CI) is empty; the remaining delta is board/harness/docs evidence. Classify runtime product code as CODE-CURRENT with respect to the candidate, but the process has not been restarted since 2026-11-24 and is not a fresh exact-SHA deployment receipt. /v1/health is degraded: cliproxy missing credentials, hermes queue_full, zai quota exhausted, and openai/xai have no configured models. Existing owner/external row INT-PROV-HEALTH-2026-11-25 owns that issue.

Open release-relevant findings already on the board include QA-CHIMERA-V2-DOCS-1, QA-CHIMERA-V2-46, QA-CHIMERA-V2-47, DF-CHIMERA-V2-111, DF-CHIMERA-V2-111-R2, DF-CHIMERA-V2-114, DF-CHIMERA-V2-121 through DF-CHIMERA-V2-126, DF-CHIMERA-V2-129, DF-CHIMERA-V2-131 through DF-CHIMERA-V2-134, DF-CHIMERA-V2-137, and INT-PROV-HEALTH-2026-11-25. They are existing rows, not duplicated by this sweep.

Required next cut sequence

1. Owner authorizes a v0.4.0 cut on a named candidate SHA.
2. Prepare the version surface and promote [Unreleased] into a complete v0.4.0 changelog/notes section, including a Known issues section sourced from measured open findings.
3. Re-run the release-owned acceptance battery and record the exact candidate SHA.
4. Obtain an exact-candidate GitReins verdict and confirm hosted CI is green on that same SHA.
5. Rebuild and install the candidate artifact in a clean environment.
6. Re-read remote tags and GitHub Releases, then push one annotated v0.4.0 tag; let the tag workflow publish PyPI and release verification. Never force-move an existing tag.

No tag, GitHub Release, PyPI upload, or source/version mutation was performed by this sweep.
