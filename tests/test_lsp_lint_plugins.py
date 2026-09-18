"""INT-GATE-003: the guard's ``lsp`` lane must ship pylsp's lint backends.

``.gitreins/config.yaml`` enables the ``lsp`` lane with ``lsp_tools: [pylsp]``, so
the lane grades every staged Python file through ``pylsp``. ``python-lsp-server``
advertises its plugins as entry points, and on 1.15.0 the ``pycodestyle`` and
``pyflakes`` entry points are listed — but the *libraries* those plugin modules
import live behind extras. A bare install therefore starts a server that
publishes no diagnostic for anything and prints ``pylsp — clean``: a vacuous
green, indistinguishable from a genuinely clean diff.

Measured on this repo before the fix (repo venv, pylsp 1.15.0 on PATH, i.e. the
state the documented guard command runs in)::

    import pylsp.plugins.pycodestyle_lint  -> ModuleNotFoundError: No module named 'pycodestyle'
    import pylsp.plugins.pyflakes_lint     -> ModuleNotFoundError: No module named 'pyflakes'

So three things have to hold, and each is asserted here because nothing else
enforces it: the dev extra declares the extras, ``uv.lock`` resolves them (the
guard's ``test_command`` is ``uv run pytest``, and CI installs from the lock),
and — whenever the server is installed at all — the plugins actually load and
report a deliberate mistake while a clean file stays clean.

Hermetic by construction: the metadata/lock contracts are offline (stdlib
``tomllib``), and the behavioural probe drives the installed pylsp plugin
functions in-process (no LSP subprocess, no network). The probe skips only when
``pylsp`` itself is absent — a ``.[full]``-only environment, which is why the
``test`` job in ``.github/workflows/ci.yml`` installs ``.[dev,full]``: CI runs
this module, and ``.[full]`` does not carry the dev extra that provides pylsp
(INT-GATE-003 rework; the install is pinned in ``tests/test_release_workflow.py``).
The lane's own enablement (``lsp: true``, ``lsp_tools: [pylsp]``) is asserted in
``tests/test_guard_docs.py``; this module owns the extras that lane needs to do
any work.
"""

from __future__ import annotations

import contextlib
import importlib
from importlib.metadata import entry_points
from pathlib import Path
from types import ModuleType

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"
UVLOCK = REPO / "uv.lock"

#: The LSP server the guard's lane resolves from PATH (``guards.lsp_tools``).
LSP_SERVER = "python-lsp-server"

#: pylsp plugin entry-point names whose backing libraries live behind extras.
LINT_EXTRA_PLUGINS = ("pycodestyle", "pyflakes")

#: The floor the lane was provisioned against — the fix must not lower it.
LSP_MIN = "1.12.0"

#: A file pycodestyle flags (E225 missing whitespace around operator) and
#: pyflakes accepts: the deliberate-mistake half of the probe.
_STYLE_ERROR_SOURCE = "x = 1\ny=2\n"

#: A file both plugins accept: the clean control.
_CLEAN_SOURCE = "\n".join(
    [
        '"""A clean module."""',
        "",
        "",
        "def add(left, right):",
        '    """Return the sum."""',
        "    return left + right",
        "",
    ]
)

#: pyflakes reports an undefined name as an Error (the severity the lane blocks
#: on), so this source is the pyflakes analogue of ``_STYLE_ERROR_SOURCE``.
_UNDEFINED_NAME_SOURCE = "def use():\n    return missing_name\n"

#: Source given, so neither plugin ever opens the file — the path only has to be
#: an absolute one for ``Document`` to derive ``document.path`` from.
_PROBE_PATH = "/tmp/chimera-v2-lsp-plugin-probe/sample.py"


def _dev_requirement() -> Requirement:
    """The ``[project.optional-dependencies].dev`` entry for the LSP server."""
    import tomllib

    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dev = list(data["project"]["optional-dependencies"]["dev"])
    matches = [Requirement(spec) for spec in dev if Requirement(spec).name == LSP_SERVER]
    assert len(matches) == 1, f"expected exactly one {LSP_SERVER} dev requirement, got {matches}"
    return matches[0]


def _locked_packages() -> dict[str, dict]:
    import tomllib

    lock = tomllib.loads(UVLOCK.read_text(encoding="utf-8"))
    return {pkg["name"]: pkg for pkg in lock["package"]}


def _requested_extras(entry: dict) -> list[str]:
    """Extras of a lock entry, tolerating uv's ``extra``/``extras`` spellings.

    uv.lock records ``[project.optional-dependencies]`` entries with the singular
    ``extra`` key, while project ``dependencies`` entries use ``extras``; either
    shape means the same thing here, and a silent rename must not turn this
    contract green.
    """
    return list(entry.get("extra", entry.get("extras", [])))


# ── The declaration ──────────────────────────────────────────────────────── #


def test_dev_extra_requests_the_lint_plugins() -> None:
    """``.[dev]`` must pull the pycodestyle and pyflakes extras behind pylsp."""
    extras = _dev_requirement().extras
    missing = sorted(set(LINT_EXTRA_PLUGINS) - extras)
    assert not missing, (
        f"the dev extra declares {LSP_SERVER} without {missing}: pylsp advertises those "
        f"entry points but cannot import their backends, so the guard's lsp lane "
        f"publishes nothing and reports a vacuous `pylsp — clean`. Required: "
        f"{LSP_SERVER}[{','.join(LINT_EXTRA_PLUGINS)}] (declared extras: {sorted(extras)})"
    )


def test_dev_extra_keeps_the_version_floor() -> None:
    """Adding the extras must not lower the floor the lane was provisioned on."""
    specifier = _dev_requirement().specifier
    assert LSP_MIN in SpecifierSet(str(specifier)), (
        f"{LSP_SERVER}{specifier} no longer allows the LSP server floor {LSP_MIN} — "
        "the lane's tool must stay pinned to at least the version the fix was "
        "verified against"
    )


# ── The lock ─────────────────────────────────────────────────────────────── #


def test_uv_lock_records_the_extras() -> None:
    """The lock must carry the extras, or an installed env cannot resolve them."""
    root = _locked_packages().get("chimera-deliberation")
    assert root is not None, "uv.lock has no chimera-deliberation entry — regenerate with `uv lock`"
    entries = [e for e in root.get("optional-dependencies", {}).get("dev", []) if e["name"] == LSP_SERVER]
    assert len(entries) == 1, f"expected one {LSP_SERVER} entry in the locked dev extra, got {entries}"
    assert sorted(_requested_extras(entries[0])) == sorted(LINT_EXTRA_PLUGINS), (
        f"uv.lock's dev extra requests extras {_requested_extras(entries[0])} instead of "
        f"{list(LINT_EXTRA_PLUGINS)} — pyproject.toml and uv.lock have drifted; re-run `uv lock`"
    )


def test_uv_lock_resolves_the_backing_libraries() -> None:
    """The extras are only real if the lock pins the libraries they install."""
    locked = _locked_packages()
    missing = sorted(set(LINT_EXTRA_PLUGINS) - set(locked))
    assert not missing, (
        f"uv.lock does not resolve {missing}: the extras in pyproject.toml would install "
        f"nothing and the lsp lane would still be vacuous"
    )
    server = locked[LSP_SERVER]["version"]
    assert server in SpecifierSet(str(_dev_requirement().specifier)), (
        f"uv.lock pins {LSP_SERVER}=={server}, outside the declared {_dev_requirement().specifier}"
    )


# ── The plugins, driven for real ─────────────────────────────────────────── #


class _WorkspaceStub:
    """The two attributes pylsp's lint plugins touch on a workspace.

    pycodestyle reads its per-file options from ``workspace._config`` and both
    plugins announce progress through ``workspace.report_progress`` (a context
    manager in the real server). Everything else on ``Workspace`` needs a live
    JSON-RPC server, which is not what this probe is testing.
    """

    class _Config:
        def plugin_settings(self, section: str, document_path: str | None = None) -> dict:
            return {}

    def __init__(self) -> None:
        self._config = self._Config()

    @contextlib.contextmanager
    def report_progress(self, *args: object, **kwargs: object):
        yield


def _load_lint_plugins() -> dict[str, ModuleType]:
    """Import the plugin modules pylsp loads — the step the bare install breaks."""
    pytest.importorskip(
        "pylsp",
        reason=f"{LSP_SERVER} is not installed here (the dev extra provides it; "
        f"CI's unit job installs .[dev,full])",
    )
    modules: dict[str, ModuleType] = {}
    for name in LINT_EXTRA_PLUGINS:
        target = f"pylsp.plugins.{name}_lint"
        try:
            modules[name] = importlib.import_module(target)
        except ModuleNotFoundError as exc:
            pytest.fail(
                f"{target} does not import ({exc}): pylsp lists the {name!r} entry point but its "
                f"backing library is absent, so the guard's lsp lane reports a vacuous "
                f"`pylsp — clean`. Declare and install the extras: "
                f'{LSP_SERVER}[{",".join(LINT_EXTRA_PLUGINS)}] (or `pip install -e ".[dev]"`).'
            )
    return modules


def _lint(plugin: ModuleType, source: str) -> list[dict]:
    """Run one loaded plugin over an in-memory document, as the lane does."""
    from pylsp.workspace import Document

    workspace = _WorkspaceStub()
    document = Document(Path(_PROBE_PATH).as_uri(), workspace, source=source)
    return plugin.pylsp_lint(workspace, document)


def test_entry_points_load_the_loaded_plugins() -> None:
    """The plugins driven below are the ones pylsp itself loads for the lane."""
    modules = _load_lint_plugins()
    by_name = {ep.name: ep for ep in entry_points(group="pylsp")}
    for name, module in modules.items():
        assert name in by_name, (
            f"pylsp does not advertise a {name!r} entry point — the lint backend this "
            f"contract provisions is gone from the server"
        )
        loaded = by_name[name].load()
        assert getattr(loaded, "__name__", None) == module.__name__, (
            f"the {name!r} entry point loads {loaded!r}, not {module.__name__} — the probe "
            f"would be exercising a plugin the server never runs"
        )


def test_pycodestyle_reports_a_deliberate_style_error() -> None:
    """A staged style error must produce diagnostics, not a clean report."""
    diagnostics = _lint(_load_lint_plugins()["pycodestyle"], _STYLE_ERROR_SOURCE)
    assert diagnostics, (
        "pycodestyle published no diagnostic for 'y=2' (E225 missing whitespace around "
        "operator) — the lsp lane would pass this file as clean"
    )
    codes = {d["code"] for d in diagnostics}
    assert "E225" in codes, f"expected E225 for 'y=2', got {sorted(codes)}"
    assert all(d["source"] == "pycodestyle" for d in diagnostics), diagnostics


def test_pycodestyle_leaves_a_clean_file_clean() -> None:
    """Clean control: the probe above is not just 'pycodestyle always reports'."""
    assert _lint(_load_lint_plugins()["pycodestyle"], _CLEAN_SOURCE) == []


def test_pyflakes_reports_an_undefined_name() -> None:
    """The pyflakes half: an Error-severity finding, the one the lane blocks on."""
    from pylsp import lsp

    diagnostics = _lint(_load_lint_plugins()["pyflakes"], _UNDEFINED_NAME_SOURCE)
    assert diagnostics, (
        "pyflakes published no diagnostic for an undefined name — the lsp lane cannot "
        "fail a file that references a name it never defines"
    )
    assert all(d["source"] == "pyflakes" for d in diagnostics), diagnostics
    assert any(d["severity"] == lsp.DiagnosticSeverity.Error for d in diagnostics), (
        f"undefined names must grade as errors (the lane only blocks on error severity), "
        f"got {[d['severity'] for d in diagnostics]}"
    )


def test_pyflakes_leaves_a_clean_file_clean() -> None:
    """Clean control for the pyflakes half."""
    assert _lint(_load_lint_plugins()["pyflakes"], _CLEAN_SOURCE) == []
