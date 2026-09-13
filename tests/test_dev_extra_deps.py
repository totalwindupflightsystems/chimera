"""Dev-extra packaging contract — the documented install must be enough to collect tests.

``AGENTS.md`` tells contributors to run ``pip install -e ".[dev]"`` and then
pytest. Test collection imports the FastAPI app (``tests/test_engine_coverage.py``
-> ``chimera.api.server`` -> ``fastapi``), so a ``dev`` extra without the
server/web runtime pins dies before a single test runs:

    ModuleNotFoundError: No module named 'fastapi'

That is the QA-CHIMERA-001 class of bug: the documented developer entry point
does not satisfy the repository's own test suite.

Offline only: stdlib ``tomllib`` + ``ast`` — no network, no imports of chimera
itself (so the contract holds even in an environment where the app deps are
missing, which is exactly the environment being described).
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_SRC_ROOT = _REPO_ROOT / "src"

#: The documented contributor command is expected to collect this file.
_COLLECTION_TARGET = Path(__file__).resolve().parent / "test_engine_coverage.py"

#: Local import roots -> filesystem root, so the walk can follow first-party imports.
_LOCAL_ROOTS = {"chimera": _SRC_ROOT, "tests": _REPO_ROOT}

#: Import name -> distribution name, for the few places where they differ.
_DIST_ALIASES = {"yaml": "pyyaml"}

#: Exact constraints the server/web extras ship; the dev extra must reuse them
#: rather than inventing a second, drifting set.
_SERVER_RUNTIME_SPECS = {"server": ["fastapi>=0.115.0", "uvicorn[standard]>=0.30.0"]}

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _pyproject() -> dict:
    with open(_PYPROJECT, "rb") as fh:
        return tomllib.load(fh)


def _canonical(name: str) -> str:
    """Normalize a distribution name to its PEP 503 form."""
    return name.strip().lower().replace("_", "-").replace(".", "-")


def _spec_name(spec: str) -> str:
    """Distribution name of a PEP 508 requirement string (extras/version stripped)."""
    match = _NAME_RE.match(spec.strip())
    assert match, f"unparseable requirement: {spec!r}"
    return _canonical(match.group(0))


def _declared_names(specs: list[str]) -> set[str]:
    return {_spec_name(spec) for spec in specs}


def _base_specs() -> list[str]:
    return list(_pyproject()["project"]["dependencies"])


def _extra_specs(extra: str) -> list[str]:
    return list(_pyproject()["project"]["optional-dependencies"][extra])


def _handles_import_error(handler: ast.ExceptHandler) -> bool:
    """True when the handler treats the guarded import as optional."""
    if handler.type is None:  # bare except
        return True
    nodes = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for node in nodes:
        if isinstance(node, ast.Name) and node.id in {"ImportError", "ModuleNotFoundError"}:
            return True
        if isinstance(node, ast.Attribute) and node.attr in {"ImportError", "ModuleNotFoundError"}:
            return True
    return False


def _is_type_checking(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _walk_module_level(stmts: list[ast.stmt], out: set[str], optional: bool) -> None:
    """Collect imports that execute at import time.

    Nested imports inside function/class bodies are lazy (a ``pytest
    --collect-only`` never runs them) and imports guarded by
    ``except ImportError`` are optional by construction, so both are skipped.
    """
    for node in stmts:
        if isinstance(node, ast.Import):
            if not optional:
                out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not optional and node.level == 0 and node.module:
                out.add(node.module)
        elif isinstance(node, ast.Try):
            guarded = any(_handles_import_error(handler) for handler in node.handlers)
            _walk_module_level(node.body, out, optional or guarded)
            _walk_module_level(node.orelse, out, optional)
            _walk_module_level(node.finalbody, out, optional)
        elif isinstance(node, ast.If):
            if _is_type_checking(node):
                continue
            _walk_module_level(node.body, out, optional)
            _walk_module_level(node.orelse, out, optional)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            _walk_module_level(node.body, out, optional)
            _walk_module_level(getattr(node, "orelse", []), out, optional)
        elif isinstance(node, ast.Match):
            for case in node.cases:
                _walk_module_level(case.body, out, optional)


def _imported_modules(path: Path) -> set[str]:
    """Every dotted module imported at import time by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    _walk_module_level(tree.body, modules, optional=False)
    return modules


def _resolve_local(dotted: str) -> list[Path]:
    """Files under the repo that implement ``dotted`` (module and/or its packages)."""
    parts = dotted.split(".")
    root = _LOCAL_ROOTS.get(parts[0])
    if root is None:
        return []
    found: list[Path] = []
    for depth in range(len(parts), 0, -1):
        rel = Path(*parts[:depth])
        for candidate in (root / rel.with_suffix(".py"), root / rel / "__init__.py"):
            if candidate.is_file():
                found.append(candidate)
    return found


def _third_party_imports(target: Path) -> set[str]:
    """Third-party top-level imports reachable from ``target`` through local code.

    Importing a module executes its module-level imports, so the closure over
    first-party files is what a plain ``pytest --collect-only`` actually needs.
    """
    stack = [target]
    seen: set[Path] = set()
    third_party: set[str] = set()
    while stack:
        path = stack.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        for dotted in _imported_modules(path):
            root = dotted.split(".")[0]
            local = _resolve_local(dotted)
            if local:
                stack.extend(local)
                continue
            if root in sys.stdlib_module_names or root.startswith("_"):
                continue
            third_party.add(_DIST_ALIASES.get(root, root))
    return {_canonical(name) for name in third_party}


# ── The contract: the dev extra carries the app runtime ───────────────────── #


def test_dev_extra_includes_fastapi() -> None:
    """``.[dev]`` alone must provide FastAPI — collection imports the app."""
    assert "fastapi" in _declared_names(_extra_specs("dev")), (
        "the dev extra must declare fastapi: tests/test_engine_coverage.py imports "
        "chimera.api.server, so `pip install -e \".[dev]\"` would fail collection"
    )


def test_dev_extra_includes_uvicorn() -> None:
    """``.[dev]`` must also provide Uvicorn, matching the server/web extras."""
    assert "uvicorn" in _declared_names(_extra_specs("dev")), (
        "the dev extra must declare uvicorn[standard]: the documented dev install "
        "should match the extras used to run the server"
    )


def test_dev_extra_reuses_server_extra_pins() -> None:
    """The dev extra reuses the server extra's exact specifiers — no drift."""
    dev_specs = _extra_specs("dev")
    for spec in _SERVER_RUNTIME_SPECS["server"]:
        assert spec in dev_specs, f"dev extra must carry the exact spec {spec!r}"


def test_collection_target_still_needs_the_fastapi_app() -> None:
    """Premise guard: the file this contract protects really pulls in FastAPI.

    If tests/test_engine_coverage.py ever stops importing the app server, the
    coverage assertion below would pass vacuously — fail loudly instead so the
    contract is re-derived rather than silently abandoned.
    """
    assert "fastapi" in _third_party_imports(_COLLECTION_TARGET), (
        "tests/test_engine_coverage.py no longer reaches fastapi; re-derive the "
        "dev-extra contract from whatever the suite now imports"
    )


def test_dev_extra_covers_collection_target_imports() -> None:
    """Every third-party import needed to collect the target is in base or dev."""
    required = _third_party_imports(_COLLECTION_TARGET)
    available = _declared_names(_base_specs()) | _declared_names(_extra_specs("dev"))
    missing = sorted(required - available)
    assert not missing, (
        f"`pip install -e \".[dev]\"` would be missing {missing} needed to collect "
        f"{_COLLECTION_TARGET.name}; declare them in the dev extra (found: {sorted(required)})"
    )
