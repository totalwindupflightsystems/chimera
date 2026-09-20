# Vendored static assets

## mermaid.min.js

- Package: `mermaid` (npm), **version 11.17.2**
- File: `dist/mermaid.min.js` from the npm tarball `mermaid-11.17.2.tgz`
  (equivalent to `https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js`)
- License: MIT
- DF-CHIMERA-V2-21: vendored so the web UI renders its DAGs offline and under
  a strict CSP (no third-party script loader). Served by the `/web` surface at
  `GET /web/vendor/mermaid.min.js` (`chimera/web/routes.py`).
- To upgrade: `npm pack mermaid@<version>`, replace this file from the
  tarball's `dist/mermaid.min.js`, update the version here, and re-run
  `tests/test_web_static_assets.py`.
