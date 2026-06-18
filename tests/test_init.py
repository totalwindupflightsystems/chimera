"""Tests for src/chimera/__init__.py — public API surface integrity.

Catches the class of bug where a class is renamed (e.g. Judge → Aggregator)
but __all__ isn't updated, causing ImportError for downstream consumers.
"""

from __future__ import annotations

import ast
import importlib


def _parse_init_imports() -> tuple[set[str], list[str]]:
    """Parse src/chimera/__init__.py and return (imported_names, __all__ entries)."""
    with open("src/chimera/__init__.py") as f:
        tree = ast.parse(f.read())

    imported: set[str] = set()
    all_entries: list[str] = []

    for node in ast.walk(tree):
        # Collect direct imports: `from chimera.foo import Bar`
        if isinstance(node, ast.ImportFrom):
            # Skip __future__ imports — they're compiler directives, not public API
            if node.module == "__future__":
                continue
            for alias in node.names:
                name = alias.asname or alias.name
                if not name.startswith("_"):
                    imported.add(name)

        # Collect __all__ entries
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "__all__"
                    and isinstance(node.value, ast.List)
                ):
                    all_entries = [
                        str(e.value)
                        for e in node.value.elts
                        if isinstance(e, ast.Constant)
                    ]

    return imported, all_entries

# Names in __all__ that aren't imports (module-level variables)
_MODULE_LEVEL_ALLOWLIST = {"__version__"}


def test_all_exports_match_imports() -> None:
    """Every name in __all__ must correspond to an actual import in __init__.py.

    Regressions caught: Judge renamed to Aggregator but __all__ still had "Judge"
    (commit f04a1a7 → fixed in 6912992).
    """
    imported, all_entries = _parse_init_imports()

    missing = [name for name in all_entries if name not in imported and name not in _MODULE_LEVEL_ALLOWLIST]
    assert not missing, (
        f"__all__ contains names not imported in __init__.py: {missing}\n"
        f"Imported names: {sorted(imported)}"
    )


def test_imports_are_in_all() -> None:
    """Every public import in __init__.py must be listed in __all__.

    Catches: class imported but forgotten in __all__, making it invisible
    to `from chimera import *` and IDE autocomplete.
    """
    imported, all_entries = _parse_init_imports()

    # __version__ is a module-level str, not an import — handled specially
    not_exported = sorted(imported - set(all_entries))
    assert not not_exported, (
        f"Imported names not in __all__: {not_exported}\n"
        f"Add them to __all__ in src/chimera/__init__.py"
    )


def test_all_names_are_importable() -> None:
    """Every name in __all__ must be importable from chimera at runtime.

    AST parsing catches some issues, but this catches runtime failures
    (e.g. the module path changed but the import statement is stale).
    """
    chimera = importlib.import_module("chimera")
    missing = []
    for name in chimera.__all__:
        if not hasattr(chimera, name):
            missing.append(name)

    assert not missing, (
        f"__all__ names not found on chimera module at runtime: {missing}\n"
        f"These names are in __all__ but not importable."
    )
