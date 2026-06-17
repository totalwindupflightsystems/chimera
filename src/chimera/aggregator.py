"""The Aggregator — merges worker outputs using dispatcher-written instructions.

The aggregator is a "dumb executor": it receives the dispatcher's merge instructions
plus each worker's output (and what that worker was asked to do) and produces
the final merged answer. Different stage kinds (``aggregator``, ``merge``, ``audit``)
only differ in how their instructions are sourced; the call is identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from chimera.config import ChimeraConfig
from chimera.dispatcher import DispatchResult, Stage
from chimera.gateway import Gateway, GatewayResponse

if TYPE_CHECKING:
    pass

log = structlog.get_logger("chimera.aggregator")


@dataclass(slots=True)
class StageResult:
    """The outcome of executing one DAG stage (input to the aggregator)."""

    stage_id: str
    model: str
    prompt: str
    response: GatewayResponse


def build_merge_prompt(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        blocks.append(
            f"### {dep.stage_id} (model: {dep.model})\n"
            f"Was asked to: {asked}\n\n"
            f"Output:\n{dep.response.text}"
        )
    worker_section = "\n\n".join(blocks) if blocks else "(no upstream outputs)"

    kind_label = stage.kind
    system = (
        f"You are the Chimera {kind_label}. "
        "Your job is to produce the single best answer to the user's request "
        "using the upstream outputs and the dispatcher's instructions.\n"
    )
    user = (
        f"## Original user request\n{user_prompt}\n\n"
        f"## Dispatcher's instructions for you ({stage.id})\n{instructions}\n\n"
        f"## Upstream outputs\n{worker_section}\n\n"
        "## Your job\n"
        "Following the instructions above, combine these into the final answer "
        "for the user. Output only the final answer."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _stage_instructions(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "merge":
        return (
            "Multiple aggregators produced the outputs above. Merge them into one "
            "authoritative final answer, preserving the strongest content from each "
            "and resolving any contradictions."
        )
    if stage.kind == "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def _default_aggregator_instructions() -> str:
    return (
        "Merge the worker outputs into a single coherent final answer. "
        "Each worker handled a different part of the task — combine them so the "
        "result fully addresses the user's request."
    )


def _what_worker_was_asked(stage_id: str, dispatch: DispatchResult) -> str:
    wp = dispatch.worker_prompt_for(stage_id)
    if wp and wp.prompt:
        return wp.prompt
    return "Solve the user's request."


class Aggregator:
    """Executes a non-worker stage (aggregator / merge / audit).

    When ``output_schema`` is provided, the aggregator uses provider-aware structured
    output to ensure the final response matches the requested schema exactly.
    """

    def __init__(self, config: ChimeraConfig, gateway: Gateway) -> None:
        self.config = config
        self.gateway = gateway

    async def execute(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = build_merge_prompt(stage, dispatch, dependencies, user_prompt)
        log.info(
            "aggregator_execute",
            stage=stage.id,
            kind=stage.kind,
            model=stage.model,
            n_inputs=len(dependencies),
            structured=output_schema is not None,
        )
        response_format = None
        if output_schema is not None:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )


__all__ = ["Aggregator", "StageResult", "build_merge_prompt"]
