"""bandit-lite: learn model category scores from stored deliberation traces.

DF-CHIMERA-V2-104. A "stored trace" is what Chimera already emits for every run
— the ``{"answer": ..., "trace": ...}`` document from ``chimera --json run`` (or
the ``trace`` field of ``POST /v1/deliberate``) written to disk. Point this
script at a file, a directory of them, or a JSONL stream and it turns the
per-stage evidence those traces already carry into a bounded correction of the
model catalog's category scores. No new instrumentation, no new store: the loop
reads what the engine already records.

Usage::

    # dry run (DEFAULT — prints the proposed deltas, writes NOTHING)
    .venv/bin/python scripts/bandit_lite.py --traces traces/

    # apply the proposed deltas to the live catalog
    .venv/bin/python scripts/bandit_lite.py --traces traces/ --write

    # tighter loop: 1-point steps, 10 samples before moving, keep 5..95
    .venv/bin/python scripts/bandit_lite.py --traces traces/ \
        --step 1 --min-samples 10 --floor 5 --ceiling 95 --write

How an observation is counted
-----------------------------
One *observation* is one LEARNABLE stage span (``kind`` of ``worker`` or
``aggregator`` — the dispatcher's planning call is not an answer, so it is not
scored). Its ``model`` is the span's model id; its *category* is, in precedence
order, the span's own ``category``, the trace's ``category``, or the
top-weighted path :func:`chimera.selector.task_to_paths` derives from the span
prompt. The observation is ACCEPTED unless the evidence says the call failed:

* an explicit ``accepted`` field on the span (a recorded verdict) wins outright;
* ``degraded: true`` on the span;
* the span (by ``stage_id`` or ``model``) appears in the trace's
  ``worker_failures``;
* the response is the engine's degraded placeholder
  (``[stage <id> (<model>) unavailable: ...]``) or is empty/whitespace;
* ``finish_reason == "length"`` — the answer was truncated, so it did not
  deliver what was asked for.

Delta rule
----------
For one ``(model, category)`` pair with ``a`` accepts and ``r`` rejects::

    n     = a + r
    delta = clamp(step * (a - r) / n, -step, +step)     # bounded step
    new   = clamp(score + delta, floor, ceiling)        # floor / ceiling

so a pair moves at most ``--step`` points per run (default 2), and never past
``--floor``/``--ceiling`` (default 1 / 99: a 0 would zero the model out of the
weighted selector and a 100 would claim a perfect score). A pair with fewer than
``--min-samples`` observations (default 5) is a NO-OP — ``n = 0`` and noise-level
``n = 1..4`` never move a catalog score.

Catalog values are percent (0-100), the canonical scale. A catalog written in
the historical 0-1 scale is detected per model and the step/floor/ceiling are
scaled with it, so one run means the same thing in both catalogs.

Category keys are resolved with the SAME precedence the selector uses
(``CategorySelector._resolve_path``): exact path, then parent prefixes, then the
short-form aliases ``code``/``analysis``/``reasoning``/``design``/``audit``
(``chimera.selector.CATEGORY_ALIASES``). Adjusting any other key would change a
number the selector never reads for that task.

Dry run vs write
----------------
The DEFAULT is a dry run: nothing on disk is touched, and the table is the
whole output. The write switch is ``--write``. It rewrites ONLY the matched
score lines — comments, ordering, quoting and every other byte of the catalog
are preserved — then re-parses the result and verifies it before replacing the
file. When a change cannot be located unambiguously the run aborts with nothing
written, because a partially adjusted catalog is worse than no adjustment. The
shipped templates (``*.example``, ``*.docker``, ``*.fleet``) are never valid
write targets.

Exit codes: 0 on success (including "no adjustment needed"), 2 on any input or
write error — one actionable line on stderr, no traceback.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
#: The same src/ pin ``scripts/model_sync.py`` uses: the script must score
#: against THIS checkout's selector, never an editable install from another tree.
sys.path.insert(0, str(REPO_ROOT / "src"))

from chimera.selector import CATEGORY_ALIASES, task_to_paths  # noqa: E402

#: Default movement cap, in catalog points, for one run.
DEFAULT_STEP = 2.0
#: Default observations required before a pair is allowed to move at all.
DEFAULT_MIN_SAMPLES = 5
#: Default bounds: never zero a model out of the selector, never claim perfection.
DEFAULT_FLOOR = 1.0
DEFAULT_CEILING = 99.0
#: The canonical catalog scale (``chimera.config.CATEGORY_SCORE_MAX``).
SCORE_MAX = 100.0
#: Stage kinds whose output is an ANSWER, i.e. evidence about the model's skill.
LEARNABLE_KINDS = frozenset({"worker", "aggregator"})
#: The engine's degraded placeholder text (``Engine._degraded_stage``).
DEGRADED_RESPONSE = re.compile(r"^\[stage .+ unavailable: .+\]$")
#: Catalog filenames that ship in the repo and must never be a write target.
TEMPLATE_SUFFIXES = (".example", ".docker", ".fleet")
#: One score line inside a ``categories:`` block:
#: ``      <path>: <value>   # optional trailing comment``.
SCORE_LINE = re.compile(r"^(?P<lead>\s+(?P<key>[^:#]+):\s*)(?P<val>[^#\s]+)(?P<tail>\s*(?:#.*)?)$")

#: Statuses reported per row. The first four come from the delta math, the last
#: three from catalog resolution.
STATUS_ADJUSTED = "adjusted"
STATUS_NO_CHANGE = "no-change"
STATUS_AT_BOUND = "at-bound"
STATUS_INSUFFICIENT = "insufficient-samples"
STATUS_NOT_IN_CATALOG = "not-in-catalog"
STATUS_NO_CATALOG_KEY = "no-catalog-key"
STATUS_FLOW_MAPPING = "unsupported-flow-mapping"


class BanditError(Exception):
    """An input or write problem worth one actionable line, never a traceback."""


# ═══════════════════════════════════════════════════════════════════════════
#  Reading stored traces
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Observation:
    """One scored stage span: which model answered, in which category, and how."""

    model: str
    category: str
    accepted: bool


@dataclass
class Counts:
    """Acceptance tally for one ``(model, category)`` pair."""

    accepts: int = 0
    rejects: int = 0

    @property
    def n(self) -> int:
        return self.accepts + self.rejects

    @property
    def rate(self) -> float:
        return self.accepts / self.n if self.n else 0.0

    def add(self, other: Counts) -> None:
        self.accepts += other.accepts
        self.rejects += other.rejects


def _iter_documents(path: Path) -> list[Any]:
    """Return the JSON documents stored at *path* (single, list, or JSONL)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BanditError(f"cannot read traces file {path}: {exc.strerror or exc}") from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # JSONL: one document per line. A malformed line is a hard error — a
        # trace that silently disappears would bias the counts it fed.
        docs: list[Any] = []
        for lineno, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                docs.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise BanditError(f"{path}:{lineno}: not JSON ({exc.msg})") from exc
        return docs
    return parsed if isinstance(parsed, list) else [parsed]


def load_trace_paths(paths: Sequence[Path]) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
    """Load every stored trace under *paths*.

    Returns ``(documents, warnings)``. A directory is swept for ``*.json`` /
    ``*.jsonl`` (recursively); a document that carries no ``trace``/``stages``
    payload is reported as a warning and skipped, while an unreadable or
    unparsable file is an error — silently dropping evidence is how a learning
    loop ends up adjusting a score on the runs it happened to parse.
    """
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = raw.expanduser()
        if path.is_dir():
            candidates = sorted(p for p in path.rglob("*") if p.suffix in {".json", ".jsonl"})
        elif path.is_file():
            candidates = [path]
        else:
            raise BanditError(f"--traces path does not exist: {path}")
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(candidate)
    documents: list[tuple[Path, dict[str, Any]]] = []
    warnings: list[str] = []
    for path in files:
        for doc in _iter_documents(path):
            if isinstance(doc, dict) and _payload_of(doc) is not None:
                documents.append((path, doc))
            else:
                warnings.append(f"{path}: no trace payload (no 'trace' or 'stages' key) — skipped")
    return documents, warnings


def _payload_of(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Return the trace mapping inside *doc* (``doc["trace"]`` or *doc* itself)."""
    trace = doc.get("trace")
    if isinstance(trace, dict):
        return trace
    if isinstance(doc.get("stages"), list):
        return doc
    return None


def _failure_keys(payload: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Return the ``(stage_ids, models)`` the trace reports as failed workers.

    ``WorkerFailure`` always carries a ``stage_id``, so a failure names ONE span
    and must never blanket-reject every span of that model — one dropped worker
    is not evidence that the model's other answers were bad. Models are only
    collected for the degenerate entries that have no stage id at all (older or
    hand-written traces), where the span cannot be identified any other way.
    """
    stage_ids: set[str] = set()
    models: set[str] = set()
    failures = payload.get("worker_failures") or []
    if not isinstance(failures, list):
        return stage_ids, models
    for failure in failures:
        if not isinstance(failure, dict):
            continue
        stage_id = failure.get("stage_id")
        if isinstance(stage_id, str) and stage_id:
            stage_ids.add(stage_id)
            continue
        model = failure.get("model")
        if isinstance(model, str) and model:
            models.add(model)
    return stage_ids, models


def classify_stage(
    stage: dict[str, Any],
    *,
    failed_stage_ids: set[str] | None = None,
    failed_models: set[str] | None = None,
) -> tuple[bool, str]:
    """Decide whether *stage* is an acceptance, and name the reason.

    The reason string exists so a caller can tell "the model answered" from
    "there was nothing to judge": every reject has a named cause, and the
    script prints the rejects it decided on rather than a bare count.
    """
    if "accepted" in stage:
        accepted = stage.get("accepted")
        if isinstance(accepted, bool):
            return accepted, "explicit" if accepted else "explicit-reject"
    if stage.get("degraded") is True:
        return False, "degraded-flag"
    stage_id = stage.get("stage_id")
    model = stage.get("model")
    if isinstance(stage_id, str) and stage_id in (failed_stage_ids or set()):
        return False, "worker-failure"
    if isinstance(model, str) and model in (failed_models or set()):
        return False, "worker-failure"
    response = stage.get("response")
    text = response.strip() if isinstance(response, str) else ""
    if not text:
        return False, "empty-response"
    if DEGRADED_RESPONSE.match(text):
        return False, "degraded-placeholder"
    if stage.get("finish_reason") == "length":
        return False, "truncated"
    return True, "answered"


def derive_category(prompt: str) -> str | None:
    """Return the top-weighted selector path for *prompt* (deterministic).

    ``task_to_paths`` normalizes its weights; ties are broken by path name so two
    runs over the same trace can never disagree about the category.
    """
    if not prompt.strip():
        return None
    weights = task_to_paths(prompt)
    if not weights:
        return None
    return max(sorted(weights.items()), key=lambda item: item[1])[0]


def iter_observations(doc: dict[str, Any]) -> Iterator[Observation]:
    """Yield one :class:`Observation` per learnable stage span in *doc*."""
    payload = _payload_of(doc)
    if payload is None:
        return
    failed_stage_ids, failed_models = _failure_keys(payload)
    hints: list[str] = []
    for source in (payload, doc):
        hint = source.get("category")
        if isinstance(hint, str) and hint.strip():
            hints.append(hint.strip())
    stages = payload.get("stages")
    if not isinstance(stages, list):
        return
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if stage.get("kind") not in LEARNABLE_KINDS:
            continue
        model = stage.get("model")
        if not isinstance(model, str) or not model.strip():
            continue
        category = stage.get("category")
        category = category.strip() if isinstance(category, str) and category.strip() else None
        if category is None:
            category = hints[0] if hints else derive_category(str(stage.get("prompt") or ""))
        if category is None:
            continue
        accepted, _reason = classify_stage(
            stage,
            failed_stage_ids=failed_stage_ids,
            failed_models=failed_models,
        )
        yield Observation(model=model.strip(), category=category, accepted=accepted)


def aggregate(observations: Iterable[Observation]) -> dict[tuple[str, str], Counts]:
    """Tally observations into ``{(model, category_hint): Counts}``."""
    tally: dict[tuple[str, str], Counts] = {}
    for obs in observations:
        counts = tally.setdefault((obs.model, obs.category), Counts())
        if obs.accepted:
            counts.accepts += 1
        else:
            counts.rejects += 1
    return tally


# ═══════════════════════════════════════════════════════════════════════════
#  Delta math
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Decision:
    """The delta math for one pair, including WHY it did or did not move."""

    n: int
    accepts: int
    rejects: int
    current: float
    raw_delta: float
    delta: float
    new_score: float
    status: str


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_delta(
    accepts: int,
    rejects: int,
    *,
    current: float,
    step: float = DEFAULT_STEP,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    floor: float = DEFAULT_FLOOR,
    ceiling: float = DEFAULT_CEILING,
) -> Decision:
    """Compute the bounded score delta for one ``(model, category)`` pair.

    ``delta = clamp(step * (accepts - rejects) / n, -step, +step)`` capped by the
    floor/ceiling on the RESULTING score, so ``decision.delta`` is the movement
    that would actually be written. Fewer than *min_samples* observations is a
    NO-OP: the pair is reported with a zero delta and status
    ``insufficient-samples`` instead of being adjusted on noise.
    """
    if step < 0:
        raise BanditError(f"--step must be >= 0 (got {step})")
    if min_samples < 1:
        raise BanditError(f"--min-samples must be >= 1 (got {min_samples})")
    if floor > ceiling:
        raise BanditError(f"--floor ({floor}) must be <= --ceiling ({ceiling})")
    n = accepts + rejects
    if n < min_samples:
        return Decision(
            n=n,
            accepts=accepts,
            rejects=rejects,
            current=current,
            raw_delta=0.0,
            delta=0.0,
            new_score=current,
            status=STATUS_INSUFFICIENT,
        )
    signal = (accepts - rejects) / n  # in [-1, 1]: net acceptance share
    raw_delta = _clamp(step * signal, -step, step)
    target = current + raw_delta
    new_score = _clamp(target, floor, ceiling)
    delta = new_score - current
    if delta == 0.0:
        status = STATUS_AT_BOUND if target != new_score else STATUS_NO_CHANGE
    else:
        status = STATUS_ADJUSTED
    return Decision(
        n=n,
        accepts=accepts,
        rejects=rejects,
        current=current,
        raw_delta=raw_delta,
        delta=delta,
        new_score=new_score,
        status=status,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Catalog resolution + planning
# ═══════════════════════════════════════════════════════════════════════════


def _parent_paths(path: str) -> Iterator[str]:
    """Yield *path*'s parent prefixes, shortest last (selector precedence)."""
    segments = path.split("/")
    while len(segments) > 1:
        segments.pop()
        yield "/".join(segments)


def resolve_catalog_key(categories: dict[str, Any], hint: str) -> str | None:
    """Return the catalog key the selector would read for *hint*, or ``None``.

    Mirrors ``CategorySelector._resolve_path`` exactly — exact path, then parent
    prefixes, then short-form aliases — and closes the loop in both directions,
    because a hint and a catalog entry can each be the short or the long form: a
    long ``technology_code/code_generation/python`` hint lands on a ``code`` key,
    and a ``code`` hint lands on the long path under ``technology_code``.
    Adjusting any other key would move a number the selector never reads.
    """
    if hint in categories:
        return hint
    for parent in _parent_paths(hint):
        if parent in categories:
            return parent
    for target in CATEGORY_ALIASES.get(hint, ()):
        found = _key_under(categories, target)
        if found is not None:
            return found
    for key in sorted(categories):
        for target in CATEGORY_ALIASES.get(key, ()):
            if hint == target or hint.startswith(target + "/"):
                return key
    return None


def _key_under(categories: dict[str, Any], prefix: str) -> str | None:
    """Return *prefix* if the catalog has it (or a path beneath it), else ``None``."""
    if prefix in categories:
        return prefix
    for parent in _parent_paths(prefix):
        if parent in categories:
            return parent
    for key in sorted(categories):
        if key.startswith(prefix + "/"):
            return key
    return None


def model_scale(categories: dict[str, Any]) -> str:
    """Return ``"unit"`` for a 0-1 catalog entry, else ``"percent"``.

    Follows the loader's documented rule (``docs/CONFIG.md``: a catalog whose
    values are all ``<= 1.0`` is read as 0.0-1.0 and rescaled x100 on load), so
    the delta this script writes lands in the scale the file itself uses.
    """
    scores = [value for value in categories.values() if isinstance(value, int | float)]
    if not scores:
        return "percent"
    return "unit" if max(float(score) for score in scores) <= 1.0 else "percent"


def round_for_scale(value: float, scale: str) -> float:
    """Round a score to the precision its scale is written with."""
    return round(value, 4) if scale == "unit" else round(value, 2)


@dataclass(frozen=True)
class Adjustment:
    """One row of the report: a pair, its evidence, and the proposed movement."""

    model: str
    category: str
    counts: Counts
    current: float | None
    raw_delta: float
    delta: float
    new_score: float | None
    status: str
    scale: str = "percent"


def build_plan(
    tally: dict[tuple[str, str], Counts],
    catalog: dict[str, Any],
    *,
    step: float = DEFAULT_STEP,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    floor: float = DEFAULT_FLOOR,
    ceiling: float = DEFAULT_CEILING,
) -> list[Adjustment]:
    """Turn ``(model, hint)`` tallies into catalog-key-level adjustments.

    Resolution happens BEFORE the math so two hints that land on the same
    catalog key (``code`` and ``technology_code/code_generation/python`` both
    resolving to a ``code`` key, say) contribute to ONE delta instead of
    writing two conflicting ones.
    """
    merged: dict[tuple[str, str], Counts] = {}
    unresolved: list[Adjustment] = []
    for (model, hint), counts in sorted(tally.items()):
        entry = catalog.get(model)
        if not isinstance(entry, dict):
            unresolved.append(
                Adjustment(
                    model=model,
                    category=hint,
                    counts=counts,
                    current=None,
                    raw_delta=0.0,
                    delta=0.0,
                    new_score=None,
                    status=STATUS_NOT_IN_CATALOG,
                )
            )
            continue
        categories = entry.get("categories")
        if not isinstance(categories, dict) or not categories:
            unresolved.append(
                Adjustment(
                    model=model,
                    category=hint,
                    counts=counts,
                    current=None,
                    raw_delta=0.0,
                    delta=0.0,
                    new_score=None,
                    status=STATUS_NO_CATALOG_KEY,
                )
            )
            continue
        key = resolve_catalog_key(categories, hint)
        if key is None:
            unresolved.append(
                Adjustment(
                    model=model,
                    category=hint,
                    counts=counts,
                    current=None,
                    raw_delta=0.0,
                    delta=0.0,
                    new_score=None,
                    status=STATUS_NO_CATALOG_KEY,
                )
            )
            continue
        merged.setdefault((model, key), Counts()).add(counts)

    rows: list[Adjustment] = []
    for (model, key), counts in sorted(merged.items()):
        entry = catalog[model]
        categories = entry.get("categories") or {}
        raw = categories.get(key)
        if not isinstance(raw, int | float):
            unresolved.append(
                Adjustment(
                    model=model,
                    category=key,
                    counts=counts,
                    current=None,
                    raw_delta=0.0,
                    delta=0.0,
                    new_score=None,
                    status=STATUS_NO_CATALOG_KEY,
                )
            )
            continue
        scale = model_scale(categories)
        factor = 0.01 if scale == "unit" else 1.0
        decision = compute_delta(
            counts.accepts,
            counts.rejects,
            current=float(raw),
            step=step * factor,
            min_samples=min_samples,
            floor=floor * factor,
            ceiling=ceiling * factor,
        )
        rows.append(
            Adjustment(
                model=model,
                category=key,
                counts=counts,
                current=float(raw),
                raw_delta=decision.raw_delta,
                delta=round_for_scale(decision.delta, scale),
                new_score=round_for_scale(decision.new_score, scale),
                status=decision.status,
                scale=scale,
            )
        )
    rows.extend(unresolved)
    rows.sort(key=lambda row: (row.model, row.category, row.status))
    return rows


# ═══════════════════════════════════════════════════════════════════════════
#  Catalog IO
# ═══════════════════════════════════════════════════════════════════════════


def load_catalog(path: Path) -> tuple[dict[str, Any], str]:
    """Return ``(models_mapping, raw_text)`` for the catalog at *path*."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BanditError(f"cannot read catalog {path}: {exc.strerror or exc}") from exc
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise BanditError(f"catalog {path} is not valid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BanditError(f"catalog {path} is not a YAML mapping")
    models = parsed.get("models")
    if not isinstance(models, dict) or not models:
        raise BanditError(f"catalog {path} has no non-empty 'models:' mapping")
    return models, text


def _format_score(value: float, original: str) -> str:
    """Write *value* in the numeric style the original token used.

    The style is preserved exactly ('88' stays an integer, '0.8' keeps one
    decimal) but never at the cost of the adjustment: a one-decimal unit-scale
    catalog would round a 0.02 step clean away, so the precision widens until
    the written text really carries *value*.
    """
    if "." in original:
        fraction = original.split(".", 1)[1].rstrip("0123456789")
        if fraction:  # exponent or other odd spelling — use a safe default
            return f"{value:.4f}" if abs(value) <= 1.0 else f"{value:.2f}"
        decimals = max(1, len(original.split(".", 1)[1]))
        while decimals < 4 and not math.isclose(round(value, decimals), value, abs_tol=1e-12):
            decimals += 1
        return f"{value:.{decimals}f}"
    if math.isclose(value, round(value), abs_tol=1e-9):
        return str(int(round(value)))
    return f"{value:.2f}"


def rewrite_catalog_text(
    text: str, changes: dict[tuple[str, str], float]
) -> tuple[str, set[tuple[str, str]]]:
    """Rewrite ONLY the score lines named in *changes*.

    Returns ``(new_text, applied)``. Comment-preserving by construction: every
    line that is not a targeted score line is copied through byte-for-byte, so a
    diff of the result is exactly the adjusted numbers. Unsupported shapes (a
    flow-style ``categories: {...}``) are reported in ``applied``'s complement —
    the caller refuses the whole write rather than half-applying it.
    """
    lines = text.splitlines(keepends=True)
    pending = dict(changes)
    applied: set[tuple[str, str]] = set()
    in_models = False
    model_indent: int | None = None
    model: str | None = None
    cats_indent: int | None = None
    flow_models: set[str] = set()
    for index, raw_line in enumerate(lines):
        line = raw_line.rstrip("\r\n")
        newline = raw_line[len(line) :]
        stripped = line.strip()
        if not in_models:
            if stripped == "models:":
                in_models = True
            continue
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            break  # left the models: block
        if model is None:
            if stripped.endswith(":") and (model_indent is None or indent == model_indent):
                model_indent = indent
                model = stripped[:-1].strip().strip("'\"")
            continue
        assert model_indent is not None
        if indent <= model_indent:
            # A sibling key of the model entry (or the next model): re-read this
            # line as a model start without advancing the cursor twice.
            model, cats_indent = None, None
            if stripped.endswith(":"):
                model_indent = indent if model_indent is None else model_indent
                model = stripped[:-1].strip().strip("'\"")
            continue
        if cats_indent is None:
            if stripped.startswith("categories:"):
                remainder = stripped[len("categories:") :].strip()
                if remainder:
                    flow_models.add(model)
                else:
                    cats_indent = indent
            continue
        if indent <= cats_indent:
            cats_indent = None
            if stripped.startswith("categories:"):
                remainder = stripped[len("categories:") :].strip()
                if remainder:
                    flow_models.add(model)
                else:
                    cats_indent = indent
            continue
        match = SCORE_LINE.match(line)
        if match is None:
            continue
        key = match.group("key").strip().strip("'\"")
        target = (model, key)
        if target not in pending:
            continue
        # Rewrite the scalar only: `lead` (indent + key + colon + gap) and `tail`
        # (gap + optional trailing comment) are carried through verbatim, so the
        # adjusted line differs from the original in the number and nothing else.
        token = _format_score(pending[target], match.group("val"))
        lines[index] = f"{match.group('lead')}{token}{match.group('tail')}{newline}"
        applied.add(target)
    if flow_models & {model_id for model_id, _key in pending}:
        raise BanditError(
            "cannot rewrite a flow-style 'categories: {...}' mapping "
            f"({', '.join(sorted(flow_models & {model_id for model_id, _key in pending}))}) — "
            "expand it to a block mapping first"
        )
    return "".join(lines), applied


def write_catalog(path: Path, rows: Sequence[Adjustment]) -> list[str]:
    """Apply *rows* to the catalog at *path*, atomically and verified.

    Returns the ``"model category"`` strings written. Refuses (nothing written)
    when the target is a shipped template, when a change cannot be located
    unambiguously, or when the rewritten file does not parse back to the
    intended scores.
    """
    if path.name.endswith(TEMPLATE_SUFFIXES):
        raise BanditError(
            f"refusing to write {path.name}: shipped template, not a live catalog "
            "(use --catalog to name the local chimera.yaml)"
        )
    changes: dict[tuple[str, str], float] = {}
    for row in rows:
        if row.status != STATUS_ADJUSTED or row.new_score is None:
            continue
        changes[(row.model, row.category)] = row.new_score
    if not changes:
        return []
    models, text = load_catalog(path)
    new_text, applied = rewrite_catalog_text(text, changes)
    missing = sorted(set(changes) - applied)
    if missing:
        names = ", ".join(f"{model}·{key}" for model, key in missing)
        raise BanditError(f"catalog {path}: could not locate the score line(s) for {names} — nothing written")
    try:
        rewritten = yaml.safe_load(new_text)
    except yaml.YAMLError as exc:  # pragma: no cover - defensive: text was re-built in place
        raise BanditError(f"catalog rewrite produced invalid YAML ({exc}) — nothing written") from exc
    _verify_rewrite(models, rewritten, changes, path)
    directory = path.parent if str(path.parent) else Path(".")
    handle, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".bandit-tmp", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(new_text)
        os.replace(tmp_name, path)
    except OSError as exc:
        Path(tmp_name).unlink(missing_ok=True)
        raise BanditError(f"cannot write catalog {path}: {exc.strerror or exc}") from exc
    return [f"{model} {key}" for model, key in sorted(applied)]


def _verify_rewrite(
    before: dict[str, Any],
    after: Any,
    changes: dict[tuple[str, str], float],
    path: Path,
) -> None:
    """Fail loud unless *after* differs from *before* in exactly *changes*."""
    if not isinstance(after, dict):
        raise BanditError(f"catalog {path}: rewrite did not produce a mapping — nothing written")
    after_models = after.get("models")
    if not isinstance(after_models, dict):
        raise BanditError(f"catalog {path}: rewrite lost the 'models:' mapping — nothing written")
    expected: dict[str, dict[str, float]] = {
        model: {key: value for (model_id, key), value in changes.items() if model_id == model}
        for model in {model_id for model_id, _key in changes}
    }
    for model, wanted in expected.items():
        entry = after_models.get(model)
        if not isinstance(entry, dict) or not isinstance(entry.get("categories"), dict):
            raise BanditError(f"catalog {path}: rewrite lost models.{model}.categories — nothing written")
        written = entry["categories"]
        for key, value in wanted.items():
            actual = written.get(key)
            if not isinstance(actual, int | float) or not math.isclose(float(actual), value, abs_tol=1e-9):
                raise BanditError(
                    f"catalog {path}: {model} {key} reads back as {actual!r}, "
                    f"expected {value!r} — nothing written"
                )
        # Every OTHER score in the touched entries must survive untouched.
        original = before[model].get("categories") or {}
        for key, value in original.items():
            if key in wanted:
                continue
            if written.get(key) != value:
                raise BanditError(
                    f"catalog {path}: {model} {key} changed unexpectedly ({value!r} -> "
                    f"{written.get(key)!r}) — nothing written"
                )


# ═══════════════════════════════════════════════════════════════════════════
#  Reporting
# ═══════════════════════════════════════════════════════════════════════════


def _number(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}" if signed else f"{value:.2f}"


def render_table(rows: Sequence[Adjustment]) -> str:
    """Render the adjustment report as a fixed-width table."""
    headers = ("model", "category", "n", "acc", "rej", "rate", "score", "raw", "delta", "new", "status")
    body: list[tuple[str, ...]] = []
    for row in rows:
        body.append(
            (
                row.model,
                row.category,
                str(row.counts.n),
                str(row.counts.accepts),
                str(row.counts.rejects),
                f"{row.counts.rate:.2f}",
                _number(row.current),
                _number(row.raw_delta, signed=True),
                _number(row.delta, signed=True),
                _number(row.new_score),
                row.status,
            )
        )
    widths = [len(header) for header in headers]
    for cells in body:
        for index, cell in enumerate(cells):
            widths[index] = max(widths[index], len(cell))
    lines = ["  ".join(cell.ljust(widths[index]) for index, cell in enumerate(headers)).rstrip()]
    lines.append("  ".join("-" * width for width in widths))
    for cells in body:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells)).rstrip())
    return "\n".join(lines)


def _plan_payload(
    rows: Sequence[Adjustment],
    *,
    mode: str,
    args: argparse.Namespace,
    document_count: int,
    written: Sequence[str],
) -> dict[str, Any]:
    return {
        "mode": mode,
        "write_switch": "--write",
        "step": args.step,
        "min_samples": args.min_samples,
        "floor": args.floor,
        "ceiling": args.ceiling,
        "traces": document_count,
        "written": list(written),
        "pairs": [
            {
                "model": row.model,
                "category": row.category,
                "n": row.counts.n,
                "accepts": row.counts.accepts,
                "rejects": row.counts.rejects,
                "rate": round(row.counts.rate, 6),
                "score": row.current,
                "raw_delta": round(row.raw_delta, 6),
                "delta": row.delta,
                "new_score": row.new_score,
                "status": row.status,
                "scale": row.scale,
            }
            for row in rows
        ],
    }


def _metric_notes(rows: Sequence[Adjustment], document_count: int, written: Sequence[str]) -> str:
    proposed = sum(1 for row in rows if row.status == STATUS_ADJUSTED)
    skipped = sum(1 for row in rows if row.status != STATUS_ADJUSTED)
    return (
        f"{document_count} stored trace(s) -> {len(rows)} (model, category) pair(s): "
        f"{proposed} adjustment(s) proposed, {len(written)} written, {skipped} skipped"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bandit_lite.py",
        description=(
            "Learn model category scores from stored deliberation traces. "
            "DRY RUN BY DEFAULT: prints the proposed per-(model, category) deltas and writes "
            "nothing. Pass --write to apply them to the catalog."
        ),
        epilog=(
            "delta = clamp(step * (accepts - rejects) / n, -step, +step) capped to "
            "[floor, ceiling]; pairs with fewer than --min-samples observations never move. "
            "Category keys are resolved with the selector's own precedence (exact, parent "
            "prefix, short-form alias), so the number written is the number scored."
        ),
    )
    parser.add_argument(
        "--traces",
        nargs="+",
        required=True,
        metavar="PATH",
        help="trace file(s)/director(ies): {'answer','trace'} JSON, a raw trace JSON, or JSONL",
    )
    parser.add_argument(
        "--catalog",
        default=None,
        metavar="PATH",
        help="catalog to read (and, with --write, to adjust); default $CHIMERA_CONFIG or ./chimera.yaml",
    )
    parser.add_argument(
        "--step",
        type=float,
        default=DEFAULT_STEP,
        metavar="POINTS",
        help=f"maximum score movement per run, in catalog points (default {DEFAULT_STEP})",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=DEFAULT_MIN_SAMPLES,
        metavar="N",
        help=f"observations required before a pair may move (default {DEFAULT_MIN_SAMPLES})",
    )
    parser.add_argument(
        "--floor",
        type=float,
        default=DEFAULT_FLOOR,
        metavar="POINTS",
        help=f"lowest score the loop may write (default {DEFAULT_FLOOR})",
    )
    parser.add_argument(
        "--ceiling",
        type=float,
        default=DEFAULT_CEILING,
        metavar="POINTS",
        help=f"highest score the loop may write (default {DEFAULT_CEILING})",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="WRITE the catalog (default is a dry run that touches nothing)",
    )
    parser.add_argument("--json", action="store_true", help="emit the plan as one JSON object")
    return parser


def _resolve_catalog(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("CHIMERA_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path("chimera.yaml")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the learning loop; return a process exit code (0 ok, 2 input error)."""
    args = _build_parser().parse_args(argv)
    try:
        documents, warnings = load_trace_paths([Path(raw) for raw in args.traces])
        if not documents:
            raise BanditError("no stored traces found under " + ", ".join(str(path) for path in args.traces))
        observations: list[Observation] = []
        for _path, doc in documents:
            observations.extend(iter_observations(doc))
        tally = aggregate(observations)
        catalog_path = _resolve_catalog(args.catalog)
        catalog, _text = load_catalog(catalog_path)
        rows = build_plan(
            tally,
            catalog,
            step=args.step,
            min_samples=args.min_samples,
            floor=args.floor,
            ceiling=args.ceiling,
        )
        mode = "write" if args.write else "dry-run"
        written: list[str] = []
        if args.write:
            written = write_catalog(catalog_path, rows)
    except BanditError as exc:
        print(f"bandit-lite: {exc}", file=sys.stderr)
        return 2
    for warning in warnings:
        print(f"bandit-lite: warning: {warning}", file=sys.stderr)
    if args.json:
        print(
            json.dumps(
                _plan_payload(
                    rows,
                    mode=mode,
                    args=args,
                    document_count=len(documents),
                    written=written,
                ),
                indent=2,
            )
        )
        return 0
    banner = (
        f"bandit-lite · mode={mode.upper()}"
        + ("" if args.write else " (nothing written; pass --write to apply)")
        + f" · catalog={catalog_path}"
        + f" · step={args.step} min_samples={args.min_samples} floor={args.floor} ceiling={args.ceiling}"
    )
    print(banner)
    print(render_table(rows))
    print(_metric_notes(rows, len(documents), written))
    if written:
        print("written: " + ", ".join(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
