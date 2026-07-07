"""The Dispatcher — designs the entire deliberation in ONE model call.

Reads the user prompt + the model catalog (with category-weighted scores) and
produces a :class:`DispatchResult`: a formation DAG, a custom prompt for every
worker, and merge instructions for the aggregator.

Two operating modes:
* ``auto`` — the dispatcher designs the DAG structure *and* writes all prompts.
* named preset (``simple`` / ``debate`` / ``audit`` / ...) — the DAG structure is
  derived from the config preset, and the dispatcher writes the per-worker
  prompts and aggregator/audit instructions for that fixed structure.

Either way Chimera makes exactly one dispatcher model call.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic import BaseModel, Field

from chimera.config import ChimeraConfig, FormationPreset
from chimera.gateway import Gateway, GatewayError, GatewayResponse

log = structlog.get_logger("chimera.dispatcher")

#: JSON schema description embedded in the dispatcher prompt.
DISPATCH_SCHEMA_HINT = {
    "formation": {
        "stages": [
            {
                "id": "worker_1",
                "kind": "worker",
                "model": "<model name>",
                "depends_on": [],
                "progressive": False,
                "wait_messages": [],
                "trigger": "",
            }
        ],
        "edges": [["worker_1", "aggregator"]],
    },
    "worker_prompts": [
        {
            "stage_id": "worker_1",
            "model": "<model name>",
            "prompt": "<custom subtask prompt>",
            "expected_output_schema": None,
        }
    ],
    "aggregator_instructions": "<how to merge the worker outputs into the final answer>",
    "stage_instructions": {"<audit/merge stage id>": "<instructions>"},
    "output_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "The final merged answer for the user"},
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Worker IDs that contributed",
            },
        },
        "required": ["answer"],
    },
}


class Stage(BaseModel):
    """A single node in the formation DAG."""

    id: str
    kind: str = "worker"  # worker | aggregator | audit | merge
    model: str
    depends_on: list[str] = Field(default_factory=list)
    progressive: bool = False
    """If True, send wait_messages sequentially before the main prompt.
    The model sees context piece-by-piece and responds to each (responses discarded),
    then gets the trigger message that requests the real output."""
    wait_messages: list[str] = Field(default_factory=list)
    """Context messages fed one-at-a-time before the main prompt. Only used when
    progressive=True. Each message gets a model response that is discarded."""
    trigger: str = ""
    """Final message that requests actual output. If empty, the main task prompt
    serves as the trigger. Only used when progressive=True."""


class FormationDAG(BaseModel):
    """The dispatcher-designed execution graph."""

    stages: list[Stage]
    edges: list[tuple[str, str]] = Field(default_factory=list)

    def stage(self, stage_id: str) -> Stage:
        for s in self.stages:
            if s.id == stage_id:
                return s
        raise KeyError(stage_id)

    def stage_ids(self) -> list[str]:
        return [s.id for s in self.stages]

    def kinds(self) -> set[str]:
        return {s.kind for s in self.stages}

    def terminals(self) -> list[Stage]:
        """Stages that nothing else depends on (the answer producers)."""
        depended = {src for src, _ in self.edges}
        return [s for s in self.stages if s.id not in depended]

    def topo_order(self) -> list[Stage]:
        """Return stages ordered so dependencies come first."""
        by_id = {s.id: s for s in self.stages}
        ordered: list[Stage] = []
        done: set[str] = set()

        def visit(node: Stage, stack: set[str]) -> None:
            if node.id in done:
                return
            if node.id in stack:
                raise ValueError(f"Cycle detected at {node.id}")
            stack.add(node.id)
            for dep in node.depends_on:
                if dep in by_id:
                    visit(by_id[dep], stack)
            stack.discard(node.id)
            done.add(node.id)
            ordered.append(node)

        for s in self.stages:
            visit(s, set())
        return ordered


class WorkerPrompt(BaseModel):
    stage_id: str
    model: str
    prompt: str
    expected_output_schema: dict[str, Any] | None = None


class DispatchResult(BaseModel):
    """What the dispatcher produces in one call."""

    formation: FormationDAG
    worker_prompts: list[WorkerPrompt] = Field(default_factory=list)
    aggregator_instructions: str = ""
    stage_instructions: dict[str, str] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None  # JSON Schema for the final answer
    source: str = "auto"  # auto | preset | fallback

    def worker_prompt_for(self, stage_id: str) -> WorkerPrompt | None:
        for wp in self.worker_prompts:
            if wp.stage_id == stage_id:
                return wp
        return None

    def stage_instruction(self, stage_id: str, kind: str) -> str:
        """Prompt instructions for a non-worker stage."""
        if stage_id in self.stage_instructions:
            return self.stage_instructions[stage_id]
        if kind == "aggregator" and not self.stage_instructions:
            return self.aggregator_instructions
        return ""


@dataclass(slots=True)
class DispatchOutcome:
    """The dispatcher model call result + parsed dispatch plan."""

    result: DispatchResult
    messages: list[dict[str, str]]
    response: GatewayResponse
    latency_ms: int


# --------------------------------------------------------------------------- #
# Preset → DAG construction (deterministic, testable without an LLM)
# --------------------------------------------------------------------------- #


def build_preset_dag(preset: FormationPreset, config: ChimeraConfig) -> FormationDAG:
    """Construct a :class:`FormationDAG` from a config preset.

    Resolution order:
    1. ``preset.dag`` — an explicit client/config-defined DAG. Returned (validated)
       directly. This is the modern path; the legacy ``simple``/``debate``/``audit``
       presets can be redefined this way in config.
    2. ``preset.workers`` / ``aggregator`` — the legacy structural fallback.
    3. Otherwise (e.g. an ``auto`` preset) → ``ValueError``.
    """
    if preset.has_dag and preset.dag is not None:
        return build_dag_from_dict(preset.dag, config)

    if preset.is_auto or preset.workers is None:
        raise ValueError("Cannot build a structural DAG from an auto preset")

    worker_models = _resolve_worker_models(preset, config)
    n_workers = preset.workers
    stages: list[Stage] = []
    edges: list[tuple[str, str]] = []

    worker_ids: list[str] = []
    for i in range(n_workers):
        wid = f"worker_{i + 1}"
        worker_ids.append(wid)
        stages.append(Stage(id=wid, kind="worker", model=worker_models[i % len(worker_models)]))

    aggregator_models = _resolve_aggregator_models(preset, config)
    aggregator_ids: list[str] = []
    for i, jm in enumerate(aggregator_models):
        jid = "aggregator" if i == 0 else f"aggregator_{i + 1}"
        aggregator_ids.append(jid)
        stages.append(Stage(id=jid, kind="aggregator", model=jm, depends_on=list(worker_ids)))
        for wid in worker_ids:
            edges.append((wid, jid))

    if preset.audit:
        audit_model = config.resolve_model_alias(preset.audit)
        stages.append(Stage(id="audit", kind="audit", model=audit_model, depends_on=[aggregator_ids[0]]))
        edges.append((aggregator_ids[0], "audit"))

    if len(aggregator_ids) > 1:
        merge_model = config.defaults.default_aggregator
        merge_id = "merge"
        stages.append(Stage(id=merge_id, kind="merge", model=merge_model, depends_on=list(aggregator_ids)))
        for jid in aggregator_ids:
            edges.append((jid, merge_id))

    dag = FormationDAG(stages=stages, edges=edges)
    _validate_dag(dag, config)
    return dag


def _resolve_worker_models(preset: FormationPreset, config: ChimeraConfig) -> list[str]:
    if preset.worker_models:
        return [config.resolve_model_alias(m) for m in preset.worker_models]
    return [config.defaults.default_worker] * (preset.workers or 1)


def build_dag_from_dict(dag_dict: dict[str, Any], config: ChimeraConfig) -> FormationDAG:
    """Parse a client/config-defined DAG mapping into a validated :class:`FormationDAG`.

    Expected shape::

        {"stages": [{"id", "kind", "model", "depends_on"}, ...], "edges": [["a","b"], ...]}

    Validation (via :func:`_validate_dag`):
    * every ``depends_on`` references a known stage id,
    * every stage ``model`` exists in the catalog (``"default"`` alias resolved),
    * at least one ``worker`` stage,
    * at least one ``aggregator``/``merge``/``audit`` stage,
    * no cycles.
    """
    stages_raw = dag_dict.get("stages") or []
    if not isinstance(stages_raw, list) or not stages_raw:
        raise ValueError("Client DAG must define a non-empty 'stages' list")
    stages: list[Stage] = []
    for s in stages_raw:
        if not isinstance(s, dict) or "id" not in s:
            raise ValueError("Each DAG stage must be a mapping with an 'id'")
        stages.append(
            Stage(
                id=s["id"],
                kind=s.get("kind", "worker"),
                model=config.resolve_model_alias(s.get("model", "")),
                depends_on=list(s.get("depends_on", [])),
                progressive=s.get("progressive", False),
                wait_messages=list(s.get("wait_messages", [])),
                trigger=s.get("trigger", ""),
            )
        )
    edges = [tuple(e) for e in (dag_dict.get("edges") or [])]
    dag = FormationDAG(stages=stages, edges=edges)
    _validate_dag(dag, config)
    return dag


def _resolve_aggregator_models(preset: FormationPreset, config: ChimeraConfig) -> list[str]:
    if preset.aggregators:
        return [config.resolve_model_alias(j) for j in preset.aggregators]
    agg_name = preset.aggregator or "default"
    return [config.resolve_model_alias(agg_name)]


def _has_cycle(dag: FormationDAG) -> bool:
    """Return True if the DAG's dependency graph contains a cycle."""
    by_id = {s.id: s for s in dag.stages}
    state: dict[str, int] = {}  # 0=visiting, 1=done

    def visit(node_id: str) -> bool:
        st = state.get(node_id)
        if st == 1:
            return False
        if st == 0:
            return True
        state[node_id] = 0
        node = by_id.get(node_id)
        if node is not None:
            for dep in node.depends_on:
                if dep in by_id and visit(dep):
                    return True
        state[node_id] = 1
        return False

    return any(visit(s.id) for s in dag.stages)


def _validate_dag(dag: FormationDAG, config: ChimeraConfig) -> None:
    ids = set(dag.stage_ids())
    if len(ids) != len(dag.stages):
        raise ValueError("Formation DAG has duplicate stage ids")
    for stage in dag.stages:
        for dep in stage.depends_on:
            if dep not in ids:
                raise ValueError(f"Stage {stage.id!r} depends on unknown {dep!r}")
        if stage.model not in config.models:
            raise ValueError(f"Stage {stage.id!r} uses unknown model {stage.model!r}")
        entry = config.models[stage.model]
        if not entry.enabled:
            raise ValueError(
                f"Stage {stage.id!r} uses disabled model {stage.model!r}. "
                f"Set enabled: true in chimera.yaml to re-enable it."
            )
    if not any(s.kind == "worker" for s in dag.stages):
        raise ValueError("Formation has no worker stages")
    if not any(s.kind in {"aggregator", "merge", "audit"} for s in dag.stages):
        raise ValueError("Formation has no aggregator/merge/audit stages")
    if _has_cycle(dag):
        raise ValueError("Formation DAG contains a cycle")


# --------------------------------------------------------------------------- #
# Dispatcher prompt construction
# --------------------------------------------------------------------------- #


def build_dispatcher_prompt(
    user_prompt: str,
    config: ChimeraConfig,
    *,
    fixed_dag: FormationDAG | None = None,
) -> list[dict[str, str]]:
    """Build the message list for the dispatcher model call."""
    catalog = config.catalog_description()
    schema_str = json.dumps(DISPATCH_SCHEMA_HINT, indent=2)

    # STRICT worker-prompt rules — prevent empty / verbatim / generic prompts.
    enforcement = (
        "\n## Worker Prompt Rules (STRICT — failures degrade the output)\n"
        "- EVERY entry in worker_prompts[] MUST have a non-empty, specific, "
        "domain-scoped `prompt`.\n"
        "- Do NOT leave worker_prompts[].prompt empty.\n"
        "- Do NOT copy the user's request verbatim into a worker prompt.\n"
        "- Each worker must receive a DISTINCT subtask focused on what THAT model "
        "is best at (per the category weights above).\n"
        "- Each worker_prompts[].stage_id MUST match a formation worker stage id "
        "exactly (case-sensitive)."
    )

    if fixed_dag is None:
        task_block = (
            "You are in AUTO mode. Design the entire formation yourself.\n"
            "1. Analyze the task and the domains it touches "
            "(code, analysis, design, audit, reasoning, ...).\n"
            "2. Pick the best model for each subtask using the category weights above.\n"
            "3. Design a formation DAG: parallel workers, then an aggregator that merges. "
            "You may add an audit stage or multiple aggregators with a merge stage.\n"
            "4. Write a CUSTOM prompt for each worker, scoped to what that model is "
            "good at. Do NOT give every worker the same prompt unless consensus is "
            "required.\n"
            "5. Write aggregator_instructions telling the aggregator exactly what each worker was "
            "asked to do and how to combine their outputs into the final answer.\n"
            "6. Use only models from the catalog. Keep it small: 2-4 workers is ideal.\n"
        )
        formation_block = "Design the `formation` field yourself."
    else:
        task_block = (
            "A fixed formation has already been chosen. Do NOT change the structure.\n"
            "Your only job: write a CUSTOM prompt for each worker and the merge "
            "instructions for the aggregator, tailored to this specific task and to each "
            "model's strengths from the category weights above.\n"
        )
        formation_block = (
            "Use this EXACT formation (return it unchanged in the `formation` field):\n"
            f"{json.dumps(fixed_dag.model_dump(mode='json'), indent=2)}"
        )
        # Surface the exact worker stage ids so the dispatcher addresses them
        # with the correct (case-sensitive) stage_id values.
        worker_ids = [s.id for s in fixed_dag.stages if s.kind == "worker"]
        if worker_ids:
            formation_block += (
                "\nThe worker stage ids you MUST address in worker_prompts[] "
                f"(use these EXACT stage_id values): {worker_ids}"
            )

    system = (
        "You are the Chimera dispatcher. Your job: design (or fill in) a "
        "multi-model deliberation that solves the user's task by splitting it "
        "across models according to their strengths.\n\n"
        f"## Available Models\n{catalog}\n\n"
        f"## Your Task\n{task_block}\n"
        f"{formation_block}\n"
        f"{enforcement}\n\n"
        "## Output\n"
        "Respond with ONLY a JSON object (no markdown fences) matching:\n"
        f"{schema_str}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"User's request:\n{user_prompt}"},
    ]


# --------------------------------------------------------------------------- #
# Output parsing
# --------------------------------------------------------------------------- #


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip())


def _extract_json_object(text: str) -> Any:
    """Pull the first balanced JSON object out of ``text``."""
    cleaned = _strip_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No JSON object found in dispatcher output")
    depth = 0
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : i + 1])
    raise ValueError("Unbalanced JSON object in dispatcher output")


def _normalize_model_name(name: str, config: ChimeraConfig) -> str:
    """Resolve a dispatcher-emitted model name to a known catalog model.

    Dispatcher models sometimes emit partial or differently-cased names
    (e.g. ``claude-sonnet-4`` instead of ``openrouter/anthropic/claude-sonnet-4``).
    Matching strategy, in order:

    * exact match in the catalog → returned as-is,
    * case-insensitive exact match,
    * unique suffix match (``"x/y/foo"`` ends with ``"/foo"``),
    * otherwise the original (unknown models are later replaced by the default).

    The ``"default"`` / ``"default_worker"`` aliases are passed through unchanged
    so :meth:`ChimeraConfig.resolve_model_alias` can handle them upstream.
    """
    cleaned = (name or "").strip()
    if not cleaned or cleaned in {"default", "default_worker"}:
        return cleaned
    models = config.models
    if cleaned in models:
        return cleaned
    lower = cleaned.lower()
    for m in models:
        if m.lower() == lower:
            return m
    # Unique suffix match: dispatcher's name is the tail of a catalog entry.
    candidates = [m for m in models if m.lower().endswith("/" + lower)]
    if len(candidates) == 1:
        return candidates[0]
    return cleaned


def _resolve_and_normalize_model(name: str, config: ChimeraConfig) -> str:
    """Resolve ``default`` aliases then fuzzy-match against the catalog."""
    return _normalize_model_name(config.resolve_model_alias(name), config)


def parse_dispatch_result(
    raw: str | dict[str, Any],
    config: ChimeraConfig,
    *,
    fallback_dag: FormationDAG | None = None,
) -> DispatchResult:
    """Parse dispatcher output into a validated :class:`DispatchResult`.

    If the output is malformed or references unknown models, fall back to
    ``fallback_dag`` (or a minimal 1-worker formation) with templated prompts.
    """
    if isinstance(raw, str):
        # Visible at debug level so malformed/strict-JSON failures can be diagnosed.
        log.debug("dispatcher_raw_output", text=raw)
    data: dict[str, Any]
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = _extract_json_object(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("dispatcher_bad_json", error=str(exc))
            return _fallback_result(config, fallback_dag, user_prompt="")

    try:
        formation_data = data.get("formation") or {}
        stages_raw = formation_data.get("stages") or []
        stages = [
            Stage(
                id=s["id"],
                kind=s.get("kind", "worker"),
                model=_resolve_and_normalize_model(s.get("model", ""), config),
                depends_on=list(s.get("depends_on", [])),
                progressive=s.get("progressive", False),
                wait_messages=list(s.get("wait_messages", [])),
                trigger=s.get("trigger", ""),
            )
            for s in stages_raw
        ]
        edges = [tuple(e) for e in (formation_data.get("edges") or [])]
        formation = FormationDAG(stages=stages, edges=edges)

        worker_prompts = [
            WorkerPrompt(
                stage_id=wp.get("stage_id", ""),
                model=_resolve_and_normalize_model(wp.get("model", ""), config),
                prompt=wp.get("prompt", ""),
                expected_output_schema=wp.get("expected_output_schema"),
            )
            for wp in (data.get("worker_prompts") or [])
        ]
        result = DispatchResult(
            formation=formation,
            worker_prompts=worker_prompts,
            aggregator_instructions=data.get("aggregator_instructions", "") or "",
            stage_instructions=data.get("stage_instructions", {}) or {},
            output_schema=data.get("output_schema"),
            source="auto",
        )
        _normalize_result(result, config)
        _validate_result(result)
        return result
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        log.warning("dispatcher_parse_failed", error=str(exc))
        return _fallback_result(config, fallback_dag, user_prompt="")


def _validate_result(result: DispatchResult) -> None:
    """Raise ``ValueError`` if the dispatch plan is structurally unusable."""
    if not result.formation.stages:
        raise ValueError("dispatch produced no stages")
    if not any(s.kind == "worker" for s in result.formation.stages):
        raise ValueError("dispatch produced no worker stages")
    if not any(s.kind in {"aggregator", "merge", "audit"} for s in result.formation.stages):
        raise ValueError("dispatch produced no aggregator/merge/audit stage")
    ids = set(result.formation.stage_ids())
    for stage in result.formation.stages:
        for dep in stage.depends_on:
            if dep not in ids:
                raise ValueError(f"stage {stage.id!r} depends on unknown {dep!r}")


def _normalize_result(result: DispatchResult, config: ChimeraConfig) -> None:
    """Resolve model aliases, fill missing worker prompts, validate the DAG.

    * Reconciles ``worker_prompts[].stage_id`` against the formation using a
      case-insensitive fallback so dispatcher case mismatches still line up.
    * Honors model locking: when ``lock_aggregator``/``lock_dispatcher`` are set,
      the dispatcher's model choice for those roles is overridden by the
      configured defaults.
    * Emits a ``worker_prompt_templated`` WARNING whenever a worker prompt had
      to be filled from the generic template (the dispatcher left it empty).
    """
    valid_models = set(config.enabled_models.keys())
    lock_agg = config.defaults.lock_aggregator
    lock_disp = config.defaults.lock_dispatcher

    # Fuzzy (case-insensitive) stage_id reconciliation for worker prompts.
    formation_ids = {s.id for s in result.formation.stages}
    lower_to_id = {s.id.lower(): s.id for s in result.formation.stages}
    for wp in result.worker_prompts:
        if wp.stage_id not in formation_ids:
            matched = lower_to_id.get(wp.stage_id.lower())
            if matched is not None:
                wp.stage_id = matched

    for stage in result.formation.stages:
        # Model locking: force configured defaults for locked roles.
        if lock_disp and stage.kind == "dispatcher":
            stage.model = config.defaults.dispatcher
        if lock_agg and stage.kind in {"aggregator", "merge", "audit"}:
            stage.model = config.defaults.default_aggregator

        if stage.model not in valid_models:
            stage.model = (
                config.defaults.default_worker
                if stage.kind == "worker"
                else config.defaults.default_aggregator
            )
        if stage.kind == "worker":
            existing = result.worker_prompt_for(stage.id)
            if existing is None:
                result.worker_prompts.append(
                    WorkerPrompt(stage_id=stage.id, model=stage.model, prompt="")
                )
            elif not existing.prompt:
                existing.model = stage.model
    for wp in result.worker_prompts:
        if not wp.prompt:
            log.warning(
                "worker_prompt_templated",
                stage_id=wp.stage_id,
                reason="empty_or_missing",
            )
            wp.prompt = _templated_worker_prompt(wp.stage_id, config)


def _fallback_result(
    config: ChimeraConfig,
    fallback_dag: FormationDAG | None,
    *,
    user_prompt: str,
) -> DispatchResult:
    """Build a safe 1-worker + 1-aggregator result when parsing fails."""
    if fallback_dag is not None:
        dag = fallback_dag
    else:
        dag = FormationDAG(
            stages=[
                Stage(id="worker_1", kind="worker", model=config.defaults.default_worker),
                Stage(
                    id="aggregator",
                    kind="aggregator",
                    model=config.defaults.default_aggregator,
                    depends_on=["worker_1"],
                ),
            ],
            edges=[("worker_1", "aggregator")],
        )
    worker_prompts = [
        WorkerPrompt(stage_id=s.id, model=s.model, prompt=_templated_worker_prompt(s.id, config))
        for s in dag.stages
        if s.kind == "worker"
    ]
    return DispatchResult(
        formation=dag,
        worker_prompts=worker_prompts,
        aggregator_instructions=(
            "Merge the worker outputs into a single, coherent final answer "
            "for the user's request."
        ),
        stage_instructions={},
        output_schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string", "description": "The final merged answer for the user"},
            },
            "required": ["answer"],
        },
        source="fallback",
    )


def _templated_worker_prompt(stage_id: str, config: ChimeraConfig) -> str:
    return (
        f"You are worker '{stage_id}'. Solve the user's request as completely as you can. "
        "Be precise and concise."
    )


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #


class Dispatcher:
    """Runs the one dispatcher model call and returns a :class:`DispatchResult`."""

    def __init__(self, config: ChimeraConfig, gateway: Gateway) -> None:
        self.config = config
        self.gateway = gateway
        self.model = config.defaults.dispatcher

    async def dispatch(
        self,
        user_prompt: str,
        formation: str = "auto",
        *,
        custom_dag: FormationDAG | None = None,
    ) -> DispatchOutcome:
        """Run the single dispatcher model call.

        When ``custom_dag`` is supplied (a validated client/config-defined DAG),
        the DESIGN phase is skipped: the dispatcher only performs the FILL-IN pass
        (writing per-worker prompts + merge instructions) against that fixed DAG.
        Otherwise the preset (``formation``) or ``auto`` path is used.
        """
        start = time.monotonic()
        if custom_dag is not None:
            messages, response, result = await self._dispatch_custom(user_prompt, custom_dag)
        else:
            preset = self._resolve_preset(formation)
            if preset is not None and not preset.is_auto:
                messages, response, result = await self._dispatch_preset(
                    user_prompt, formation, preset
                )
            else:
                messages, response, result = await self._dispatch_auto(user_prompt)
        latency_ms = int((time.monotonic() - start) * 1000)
        return DispatchOutcome(
            result=result, messages=messages, response=response, latency_ms=latency_ms
        )

    def _resolve_preset(self, formation: str) -> FormationPreset | None:
        if formation not in self.config.formations:
            log.warning("unknown_formation", formation=formation, using="auto")
            return None
        return self.config.formations[formation]

    async def _dispatch_auto(
        self, user_prompt: str
    ) -> tuple[list[dict[str, str]], GatewayResponse, DispatchResult]:
        messages = build_dispatcher_prompt(user_prompt, self.config, fixed_dag=None)
        response = await self._call_dispatcher(messages)
        result = parse_dispatch_result(response.text, self.config, fallback_dag=None)
        log.info(
            "dispatch_auto_done",
            stages=result.formation.stage_ids(),
            source=result.source,
        )
        return messages, response, result

    async def _dispatch_custom(
        self, user_prompt: str, dag: FormationDAG
    ) -> tuple[list[dict[str, str]], GatewayResponse, DispatchResult]:
        """Fill-in pass for a client/config-defined DAG (no design phase)."""
        messages = build_dispatcher_prompt(user_prompt, self.config, fixed_dag=dag)
        response = await self._call_dispatcher(messages)
        result = parse_dispatch_result(response.text, self.config, fallback_dag=dag)
        # Always honor the client-provided structure exactly.
        result.formation = dag
        result.source = "custom"
        log.info(
            "dispatch_custom_done",
            stages=dag.stage_ids(),
        )
        return messages, response, result

    async def _dispatch_preset(
        self, user_prompt: str, formation_name: str, preset: FormationPreset
    ) -> tuple[list[dict[str, str]], GatewayResponse, DispatchResult]:
        dag = build_preset_dag(preset, self.config)
        messages = build_dispatcher_prompt(user_prompt, self.config, fixed_dag=dag)
        response = await self._call_dispatcher(messages)
        result = parse_dispatch_result(response.text, self.config, fallback_dag=dag)
        # Always honor the preset structure exactly.
        result.formation = dag
        result.source = "preset"
        log.info(
            "dispatch_preset_done",
            formation=formation_name,
            stages=dag.stage_ids(),
        )
        return messages, response, result

    async def _call_dispatcher(self, messages: list[dict[str, str]]) -> GatewayResponse:
        try:
            return await self.gateway.complete(
                self.model,
                messages,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
        except GatewayError as exc:
            log.warning("dispatcher_call_failed", error=str(exc), using="fallback")
            return GatewayResponse(text="{}", model=self.model, tokens_input=0, tokens_output=0)


__all__ = [
    "DispatchOutcome",
    "DispatchResult",
    "Dispatcher",
    "FormationDAG",
    "Stage",
    "WorkerPrompt",
    "build_dag_from_dict",
    "build_dispatcher_prompt",
    "build_preset_dag",
    "parse_dispatch_result",
]
