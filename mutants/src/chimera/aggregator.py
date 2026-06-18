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


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


@dataclass(slots=True)
class StageResult:
    """The outcome of executing one DAG stage (input to the aggregator)."""

    stage_id: str
    model: str
    prompt: str
    response: GatewayResponse
    degraded: bool = False
mutants_x_build_merge_prompt__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_build_merge_prompt__mutmut)
def build_merge_prompt(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_orig(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_1(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = None

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_2(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(None, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_3(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, None)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_4(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_5(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, )

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_6(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = None
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_7(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = None
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_8(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 1
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_9(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = None
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_10(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(None, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_11(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, None)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_12(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_13(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, )
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_14(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count = 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_15(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count -= 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_16(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 2
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_17(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                None
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_18(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                None
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_19(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count >= 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_20(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 1:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_21(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            None,
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_22(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=None,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_23(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=None,
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_24(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=None,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_25(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=None,
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


def x_build_merge_prompt__mutmut_26(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_27(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_28(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_29(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_30(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
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


def x_build_merge_prompt__mutmut_31(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "XXaggregator_partial_inputsXX",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_32(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "AGGREGATOR_PARTIAL_INPUTS",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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


def x_build_merge_prompt__mutmut_33(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) + degraded_count,
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


def x_build_merge_prompt__mutmut_34(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = None

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


def x_build_merge_prompt__mutmut_35(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(None) if blocks else "(no upstream outputs)"

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


def x_build_merge_prompt__mutmut_36(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "XX\n\nXX".join(blocks) if blocks else "(no upstream outputs)"

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


def x_build_merge_prompt__mutmut_37(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "XX(no upstream outputs)XX"

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


def x_build_merge_prompt__mutmut_38(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "(NO UPSTREAM OUTPUTS)"

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


def x_build_merge_prompt__mutmut_39(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "(no upstream outputs)"

    kind_label = None
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


def x_build_merge_prompt__mutmut_40(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "(no upstream outputs)"

    kind_label = stage.kind
    system = None
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


def x_build_merge_prompt__mutmut_41(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "(no upstream outputs)"

    kind_label = stage.kind
    system = (
        f"You are the Chimera {kind_label}. "
        "XXYour job is to produce the single best answer to the user's request XX"
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


def x_build_merge_prompt__mutmut_42(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "(no upstream outputs)"

    kind_label = stage.kind
    system = (
        f"You are the Chimera {kind_label}. "
        "your job is to produce the single best answer to the user's request "
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


def x_build_merge_prompt__mutmut_43(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "(no upstream outputs)"

    kind_label = stage.kind
    system = (
        f"You are the Chimera {kind_label}. "
        "YOUR JOB IS TO PRODUCE THE SINGLE BEST ANSWER TO THE USER'S REQUEST "
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


def x_build_merge_prompt__mutmut_44(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "(no upstream outputs)"

    kind_label = stage.kind
    system = (
        f"You are the Chimera {kind_label}. "
        "Your job is to produce the single best answer to the user's request "
        "XXusing the upstream outputs and the dispatcher's instructions.\nXX"
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


def x_build_merge_prompt__mutmut_45(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "(no upstream outputs)"

    kind_label = stage.kind
    system = (
        f"You are the Chimera {kind_label}. "
        "Your job is to produce the single best answer to the user's request "
        "USING THE UPSTREAM OUTPUTS AND THE DISPATCHER'S INSTRUCTIONS.\n"
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


def x_build_merge_prompt__mutmut_46(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    worker_section = "\n\n".join(blocks) if blocks else "(no upstream outputs)"

    kind_label = stage.kind
    system = (
        f"You are the Chimera {kind_label}. "
        "Your job is to produce the single best answer to the user's request "
        "using the upstream outputs and the dispatcher's instructions.\n"
    )
    user = None
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_47(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        "XX## Your job\nXX"
        "Following the instructions above, combine these into the final answer "
        "for the user. Output only the final answer."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_48(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        "## your job\n"
        "Following the instructions above, combine these into the final answer "
        "for the user. Output only the final answer."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_49(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        "## YOUR JOB\n"
        "Following the instructions above, combine these into the final answer "
        "for the user. Output only the final answer."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_50(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        "XXFollowing the instructions above, combine these into the final answer XX"
        "for the user. Output only the final answer."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_51(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        "following the instructions above, combine these into the final answer "
        "for the user. Output only the final answer."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_52(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        "FOLLOWING THE INSTRUCTIONS ABOVE, COMBINE THESE INTO THE FINAL ANSWER "
        "for the user. Output only the final answer."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_53(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        "XXfor the user. Output only the final answer.XX"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_54(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        "for the user. output only the final answer."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_55(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        "FOR THE USER. OUTPUT ONLY THE FINAL ANSWER."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_56(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"XXroleXX": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_57(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"ROLE": "system", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_58(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"role": "XXsystemXX", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_59(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"role": "SYSTEM", "content": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_60(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"role": "system", "XXcontentXX": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_61(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"role": "system", "CONTENT": system},
        {"role": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_62(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"XXroleXX": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_63(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"ROLE": "user", "content": user},
    ]


def x_build_merge_prompt__mutmut_64(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"role": "XXuserXX", "content": user},
    ]


def x_build_merge_prompt__mutmut_65(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"role": "USER", "content": user},
    ]


def x_build_merge_prompt__mutmut_66(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"role": "user", "XXcontentXX": user},
    ]


def x_build_merge_prompt__mutmut_67(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage."""
    instructions = _stage_instructions(stage, dispatch)

    blocks: list[str] = []
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.degraded:
            degraded_count += 1
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}\n"
                f"Note: This stage failed to produce valid output."
            )
        else:
            blocks.append(
                f"### {dep.stage_id} (model: {dep.model})\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{dep.response.text}"
            )

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
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
        {"role": "user", "CONTENT": user},
    ]

mutants_x_build_merge_prompt__mutmut['_mutmut_orig'] = x_build_merge_prompt__mutmut_orig # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_1'] = x_build_merge_prompt__mutmut_1 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_2'] = x_build_merge_prompt__mutmut_2 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_3'] = x_build_merge_prompt__mutmut_3 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_4'] = x_build_merge_prompt__mutmut_4 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_5'] = x_build_merge_prompt__mutmut_5 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_6'] = x_build_merge_prompt__mutmut_6 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_7'] = x_build_merge_prompt__mutmut_7 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_8'] = x_build_merge_prompt__mutmut_8 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_9'] = x_build_merge_prompt__mutmut_9 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_10'] = x_build_merge_prompt__mutmut_10 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_11'] = x_build_merge_prompt__mutmut_11 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_12'] = x_build_merge_prompt__mutmut_12 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_13'] = x_build_merge_prompt__mutmut_13 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_14'] = x_build_merge_prompt__mutmut_14 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_15'] = x_build_merge_prompt__mutmut_15 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_16'] = x_build_merge_prompt__mutmut_16 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_17'] = x_build_merge_prompt__mutmut_17 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_18'] = x_build_merge_prompt__mutmut_18 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_19'] = x_build_merge_prompt__mutmut_19 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_20'] = x_build_merge_prompt__mutmut_20 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_21'] = x_build_merge_prompt__mutmut_21 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_22'] = x_build_merge_prompt__mutmut_22 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_23'] = x_build_merge_prompt__mutmut_23 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_24'] = x_build_merge_prompt__mutmut_24 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_25'] = x_build_merge_prompt__mutmut_25 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_26'] = x_build_merge_prompt__mutmut_26 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_27'] = x_build_merge_prompt__mutmut_27 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_28'] = x_build_merge_prompt__mutmut_28 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_29'] = x_build_merge_prompt__mutmut_29 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_30'] = x_build_merge_prompt__mutmut_30 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_31'] = x_build_merge_prompt__mutmut_31 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_32'] = x_build_merge_prompt__mutmut_32 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_33'] = x_build_merge_prompt__mutmut_33 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_34'] = x_build_merge_prompt__mutmut_34 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_35'] = x_build_merge_prompt__mutmut_35 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_36'] = x_build_merge_prompt__mutmut_36 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_37'] = x_build_merge_prompt__mutmut_37 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_38'] = x_build_merge_prompt__mutmut_38 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_39'] = x_build_merge_prompt__mutmut_39 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_40'] = x_build_merge_prompt__mutmut_40 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_41'] = x_build_merge_prompt__mutmut_41 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_42'] = x_build_merge_prompt__mutmut_42 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_43'] = x_build_merge_prompt__mutmut_43 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_44'] = x_build_merge_prompt__mutmut_44 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_45'] = x_build_merge_prompt__mutmut_45 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_46'] = x_build_merge_prompt__mutmut_46 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_47'] = x_build_merge_prompt__mutmut_47 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_48'] = x_build_merge_prompt__mutmut_48 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_49'] = x_build_merge_prompt__mutmut_49 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_50'] = x_build_merge_prompt__mutmut_50 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_51'] = x_build_merge_prompt__mutmut_51 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_52'] = x_build_merge_prompt__mutmut_52 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_53'] = x_build_merge_prompt__mutmut_53 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_54'] = x_build_merge_prompt__mutmut_54 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_55'] = x_build_merge_prompt__mutmut_55 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_56'] = x_build_merge_prompt__mutmut_56 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_57'] = x_build_merge_prompt__mutmut_57 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_58'] = x_build_merge_prompt__mutmut_58 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_59'] = x_build_merge_prompt__mutmut_59 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_60'] = x_build_merge_prompt__mutmut_60 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_61'] = x_build_merge_prompt__mutmut_61 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_62'] = x_build_merge_prompt__mutmut_62 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_63'] = x_build_merge_prompt__mutmut_63 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_64'] = x_build_merge_prompt__mutmut_64 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_65'] = x_build_merge_prompt__mutmut_65 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_66'] = x_build_merge_prompt__mutmut_66 # type: ignore # mutmut generated
mutants_x_build_merge_prompt__mutmut['x_build_merge_prompt__mutmut_67'] = x_build_merge_prompt__mutmut_67 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__stage_instructions__mutmut)
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


def x__stage_instructions__mutmut_orig(stage: Stage, dispatch: DispatchResult) -> str:
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


def x__stage_instructions__mutmut_1(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id not in dispatch.stage_instructions:
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


def x__stage_instructions__mutmut_2(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind != "aggregator":
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


def x__stage_instructions__mutmut_3(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "XXaggregatorXX":
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


def x__stage_instructions__mutmut_4(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "AGGREGATOR":
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


def x__stage_instructions__mutmut_5(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions and _default_aggregator_instructions()
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


def x__stage_instructions__mutmut_6(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind != "merge":
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


def x__stage_instructions__mutmut_7(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "XXmergeXX":
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


def x__stage_instructions__mutmut_8(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "MERGE":
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


def x__stage_instructions__mutmut_9(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "merge":
        return (
            "XXMultiple aggregators produced the outputs above. Merge them into one XX"
            "authoritative final answer, preserving the strongest content from each "
            "and resolving any contradictions."
        )
    if stage.kind == "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_10(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "merge":
        return (
            "multiple aggregators produced the outputs above. merge them into one "
            "authoritative final answer, preserving the strongest content from each "
            "and resolving any contradictions."
        )
    if stage.kind == "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_11(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "merge":
        return (
            "MULTIPLE AGGREGATORS PRODUCED THE OUTPUTS ABOVE. MERGE THEM INTO ONE "
            "authoritative final answer, preserving the strongest content from each "
            "and resolving any contradictions."
        )
    if stage.kind == "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_12(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "merge":
        return (
            "Multiple aggregators produced the outputs above. Merge them into one "
            "XXauthoritative final answer, preserving the strongest content from each XX"
            "and resolving any contradictions."
        )
    if stage.kind == "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_13(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "merge":
        return (
            "Multiple aggregators produced the outputs above. Merge them into one "
            "AUTHORITATIVE FINAL ANSWER, PRESERVING THE STRONGEST CONTENT FROM EACH "
            "and resolving any contradictions."
        )
    if stage.kind == "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_14(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "merge":
        return (
            "Multiple aggregators produced the outputs above. Merge them into one "
            "authoritative final answer, preserving the strongest content from each "
            "XXand resolving any contradictions.XX"
        )
    if stage.kind == "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_15(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "merge":
        return (
            "Multiple aggregators produced the outputs above. Merge them into one "
            "authoritative final answer, preserving the strongest content from each "
            "AND RESOLVING ANY CONTRADICTIONS."
        )
    if stage.kind == "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_16(stage: Stage, dispatch: DispatchResult) -> str:
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
    if stage.kind != "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_17(stage: Stage, dispatch: DispatchResult) -> str:
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
    if stage.kind == "XXauditXX":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_18(stage: Stage, dispatch: DispatchResult) -> str:
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
    if stage.kind == "AUDIT":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_19(stage: Stage, dispatch: DispatchResult) -> str:
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
            "XXAudit the upstream answer for correctness, completeness, and safety. XX"
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_20(stage: Stage, dispatch: DispatchResult) -> str:
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
            "audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_21(stage: Stage, dispatch: DispatchResult) -> str:
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
            "AUDIT THE UPSTREAM ANSWER FOR CORRECTNESS, COMPLETENESS, AND SAFETY. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_22(stage: Stage, dispatch: DispatchResult) -> str:
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
            "XXReturn the final, corrected answer (not a critique).XX"
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_23(stage: Stage, dispatch: DispatchResult) -> str:
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
            "return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_24(stage: Stage, dispatch: DispatchResult) -> str:
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
            "RETURN THE FINAL, CORRECTED ANSWER (NOT A CRITIQUE)."
        )
    return "Produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_25(stage: Stage, dispatch: DispatchResult) -> str:
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
    return "XXProduce the final answer from the upstream outputs.XX"


def x__stage_instructions__mutmut_26(stage: Stage, dispatch: DispatchResult) -> str:
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
    return "produce the final answer from the upstream outputs."


def x__stage_instructions__mutmut_27(stage: Stage, dispatch: DispatchResult) -> str:
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
    return "PRODUCE THE FINAL ANSWER FROM THE UPSTREAM OUTPUTS."

mutants_x__stage_instructions__mutmut['_mutmut_orig'] = x__stage_instructions__mutmut_orig # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_1'] = x__stage_instructions__mutmut_1 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_2'] = x__stage_instructions__mutmut_2 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_3'] = x__stage_instructions__mutmut_3 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_4'] = x__stage_instructions__mutmut_4 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_5'] = x__stage_instructions__mutmut_5 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_6'] = x__stage_instructions__mutmut_6 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_7'] = x__stage_instructions__mutmut_7 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_8'] = x__stage_instructions__mutmut_8 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_9'] = x__stage_instructions__mutmut_9 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_10'] = x__stage_instructions__mutmut_10 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_11'] = x__stage_instructions__mutmut_11 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_12'] = x__stage_instructions__mutmut_12 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_13'] = x__stage_instructions__mutmut_13 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_14'] = x__stage_instructions__mutmut_14 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_15'] = x__stage_instructions__mutmut_15 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_16'] = x__stage_instructions__mutmut_16 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_17'] = x__stage_instructions__mutmut_17 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_18'] = x__stage_instructions__mutmut_18 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_19'] = x__stage_instructions__mutmut_19 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_20'] = x__stage_instructions__mutmut_20 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_21'] = x__stage_instructions__mutmut_21 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_22'] = x__stage_instructions__mutmut_22 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_23'] = x__stage_instructions__mutmut_23 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_24'] = x__stage_instructions__mutmut_24 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_25'] = x__stage_instructions__mutmut_25 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_26'] = x__stage_instructions__mutmut_26 # type: ignore # mutmut generated
mutants_x__stage_instructions__mutmut['x__stage_instructions__mutmut_27'] = x__stage_instructions__mutmut_27 # type: ignore # mutmut generated
mutants_x__default_aggregator_instructions__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__default_aggregator_instructions__mutmut)
def _default_aggregator_instructions() -> str:
    return (
        "Merge the worker outputs into a single coherent final answer. "
        "Each worker handled a different part of the task — combine them so the "
        "result fully addresses the user's request."
    )


def x__default_aggregator_instructions__mutmut_orig() -> str:
    return (
        "Merge the worker outputs into a single coherent final answer. "
        "Each worker handled a different part of the task — combine them so the "
        "result fully addresses the user's request."
    )


def x__default_aggregator_instructions__mutmut_1() -> str:
    return (
        "XXMerge the worker outputs into a single coherent final answer. XX"
        "Each worker handled a different part of the task — combine them so the "
        "result fully addresses the user's request."
    )


def x__default_aggregator_instructions__mutmut_2() -> str:
    return (
        "merge the worker outputs into a single coherent final answer. "
        "Each worker handled a different part of the task — combine them so the "
        "result fully addresses the user's request."
    )


def x__default_aggregator_instructions__mutmut_3() -> str:
    return (
        "MERGE THE WORKER OUTPUTS INTO A SINGLE COHERENT FINAL ANSWER. "
        "Each worker handled a different part of the task — combine them so the "
        "result fully addresses the user's request."
    )


def x__default_aggregator_instructions__mutmut_4() -> str:
    return (
        "Merge the worker outputs into a single coherent final answer. "
        "XXEach worker handled a different part of the task — combine them so the XX"
        "result fully addresses the user's request."
    )


def x__default_aggregator_instructions__mutmut_5() -> str:
    return (
        "Merge the worker outputs into a single coherent final answer. "
        "each worker handled a different part of the task — combine them so the "
        "result fully addresses the user's request."
    )


def x__default_aggregator_instructions__mutmut_6() -> str:
    return (
        "Merge the worker outputs into a single coherent final answer. "
        "EACH WORKER HANDLED A DIFFERENT PART OF THE TASK — COMBINE THEM SO THE "
        "result fully addresses the user's request."
    )


def x__default_aggregator_instructions__mutmut_7() -> str:
    return (
        "Merge the worker outputs into a single coherent final answer. "
        "Each worker handled a different part of the task — combine them so the "
        "XXresult fully addresses the user's request.XX"
    )


def x__default_aggregator_instructions__mutmut_8() -> str:
    return (
        "Merge the worker outputs into a single coherent final answer. "
        "Each worker handled a different part of the task — combine them so the "
        "RESULT FULLY ADDRESSES THE USER'S REQUEST."
    )

mutants_x__default_aggregator_instructions__mutmut['_mutmut_orig'] = x__default_aggregator_instructions__mutmut_orig # type: ignore # mutmut generated
mutants_x__default_aggregator_instructions__mutmut['x__default_aggregator_instructions__mutmut_1'] = x__default_aggregator_instructions__mutmut_1 # type: ignore # mutmut generated
mutants_x__default_aggregator_instructions__mutmut['x__default_aggregator_instructions__mutmut_2'] = x__default_aggregator_instructions__mutmut_2 # type: ignore # mutmut generated
mutants_x__default_aggregator_instructions__mutmut['x__default_aggregator_instructions__mutmut_3'] = x__default_aggregator_instructions__mutmut_3 # type: ignore # mutmut generated
mutants_x__default_aggregator_instructions__mutmut['x__default_aggregator_instructions__mutmut_4'] = x__default_aggregator_instructions__mutmut_4 # type: ignore # mutmut generated
mutants_x__default_aggregator_instructions__mutmut['x__default_aggregator_instructions__mutmut_5'] = x__default_aggregator_instructions__mutmut_5 # type: ignore # mutmut generated
mutants_x__default_aggregator_instructions__mutmut['x__default_aggregator_instructions__mutmut_6'] = x__default_aggregator_instructions__mutmut_6 # type: ignore # mutmut generated
mutants_x__default_aggregator_instructions__mutmut['x__default_aggregator_instructions__mutmut_7'] = x__default_aggregator_instructions__mutmut_7 # type: ignore # mutmut generated
mutants_x__default_aggregator_instructions__mutmut['x__default_aggregator_instructions__mutmut_8'] = x__default_aggregator_instructions__mutmut_8 # type: ignore # mutmut generated
mutants_x__what_worker_was_asked__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__what_worker_was_asked__mutmut)
def _what_worker_was_asked(stage_id: str, dispatch: DispatchResult) -> str:
    wp = dispatch.worker_prompt_for(stage_id)
    if wp and wp.prompt:
        return wp.prompt
    return "Solve the user's request."


def x__what_worker_was_asked__mutmut_orig(stage_id: str, dispatch: DispatchResult) -> str:
    wp = dispatch.worker_prompt_for(stage_id)
    if wp and wp.prompt:
        return wp.prompt
    return "Solve the user's request."


def x__what_worker_was_asked__mutmut_1(stage_id: str, dispatch: DispatchResult) -> str:
    wp = None
    if wp and wp.prompt:
        return wp.prompt
    return "Solve the user's request."


def x__what_worker_was_asked__mutmut_2(stage_id: str, dispatch: DispatchResult) -> str:
    wp = dispatch.worker_prompt_for(None)
    if wp and wp.prompt:
        return wp.prompt
    return "Solve the user's request."


def x__what_worker_was_asked__mutmut_3(stage_id: str, dispatch: DispatchResult) -> str:
    wp = dispatch.worker_prompt_for(stage_id)
    if wp or wp.prompt:
        return wp.prompt
    return "Solve the user's request."


def x__what_worker_was_asked__mutmut_4(stage_id: str, dispatch: DispatchResult) -> str:
    wp = dispatch.worker_prompt_for(stage_id)
    if wp and wp.prompt:
        return wp.prompt
    return "XXSolve the user's request.XX"


def x__what_worker_was_asked__mutmut_5(stage_id: str, dispatch: DispatchResult) -> str:
    wp = dispatch.worker_prompt_for(stage_id)
    if wp and wp.prompt:
        return wp.prompt
    return "solve the user's request."


def x__what_worker_was_asked__mutmut_6(stage_id: str, dispatch: DispatchResult) -> str:
    wp = dispatch.worker_prompt_for(stage_id)
    if wp and wp.prompt:
        return wp.prompt
    return "SOLVE THE USER'S REQUEST."

mutants_x__what_worker_was_asked__mutmut['_mutmut_orig'] = x__what_worker_was_asked__mutmut_orig # type: ignore # mutmut generated
mutants_x__what_worker_was_asked__mutmut['x__what_worker_was_asked__mutmut_1'] = x__what_worker_was_asked__mutmut_1 # type: ignore # mutmut generated
mutants_x__what_worker_was_asked__mutmut['x__what_worker_was_asked__mutmut_2'] = x__what_worker_was_asked__mutmut_2 # type: ignore # mutmut generated
mutants_x__what_worker_was_asked__mutmut['x__what_worker_was_asked__mutmut_3'] = x__what_worker_was_asked__mutmut_3 # type: ignore # mutmut generated
mutants_x__what_worker_was_asked__mutmut['x__what_worker_was_asked__mutmut_4'] = x__what_worker_was_asked__mutmut_4 # type: ignore # mutmut generated
mutants_x__what_worker_was_asked__mutmut['x__what_worker_was_asked__mutmut_5'] = x__what_worker_was_asked__mutmut_5 # type: ignore # mutmut generated
mutants_x__what_worker_was_asked__mutmut['x__what_worker_was_asked__mutmut_6'] = x__what_worker_was_asked__mutmut_6 # type: ignore # mutmut generated
mutants_xǁAggregatorǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁAggregatorǁexecute__mutmut: MutantDict = {}  # type: ignore


class Aggregator:
    """Executes a non-worker stage (aggregator / merge / audit).

    When ``output_schema`` is provided, the aggregator uses provider-aware structured
    output to ensure the final response matches the requested schema exactly.
    """

    @_mutmut_mutated(mutants_xǁAggregatorǁ__init____mutmut)
    def __init__(self, config: ChimeraConfig, gateway: Gateway) -> None:
        self.config = config
        self.gateway = gateway

    def xǁAggregatorǁ__init____mutmut_orig(self, config: ChimeraConfig, gateway: Gateway) -> None:
        self.config = config
        self.gateway = gateway

    def xǁAggregatorǁ__init____mutmut_1(self, config: ChimeraConfig, gateway: Gateway) -> None:
        self.config = None
        self.gateway = gateway

    def xǁAggregatorǁ__init____mutmut_2(self, config: ChimeraConfig, gateway: Gateway) -> None:
        self.config = config
        self.gateway = None

    @_mutmut_mutated(mutants_xǁAggregatorǁexecute__mutmut)
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

    async def xǁAggregatorǁexecute__mutmut_orig(
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

    async def xǁAggregatorǁexecute__mutmut_1(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = None
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

    async def xǁAggregatorǁexecute__mutmut_2(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = build_merge_prompt(None, dispatch, dependencies, user_prompt)
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

    async def xǁAggregatorǁexecute__mutmut_3(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = build_merge_prompt(stage, None, dependencies, user_prompt)
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

    async def xǁAggregatorǁexecute__mutmut_4(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = build_merge_prompt(stage, dispatch, None, user_prompt)
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

    async def xǁAggregatorǁexecute__mutmut_5(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = build_merge_prompt(stage, dispatch, dependencies, None)
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

    async def xǁAggregatorǁexecute__mutmut_6(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = build_merge_prompt(dispatch, dependencies, user_prompt)
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

    async def xǁAggregatorǁexecute__mutmut_7(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = build_merge_prompt(stage, dependencies, user_prompt)
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

    async def xǁAggregatorǁexecute__mutmut_8(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = build_merge_prompt(stage, dispatch, user_prompt)
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

    async def xǁAggregatorǁexecute__mutmut_9(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        messages = build_merge_prompt(stage, dispatch, dependencies, )
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

    async def xǁAggregatorǁexecute__mutmut_10(
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
            None,
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

    async def xǁAggregatorǁexecute__mutmut_11(
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
            stage=None,
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

    async def xǁAggregatorǁexecute__mutmut_12(
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
            kind=None,
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

    async def xǁAggregatorǁexecute__mutmut_13(
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
            model=None,
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

    async def xǁAggregatorǁexecute__mutmut_14(
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
            n_inputs=None,
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

    async def xǁAggregatorǁexecute__mutmut_15(
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
            structured=None,
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

    async def xǁAggregatorǁexecute__mutmut_16(
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

    async def xǁAggregatorǁexecute__mutmut_17(
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

    async def xǁAggregatorǁexecute__mutmut_18(
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

    async def xǁAggregatorǁexecute__mutmut_19(
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

    async def xǁAggregatorǁexecute__mutmut_20(
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

    async def xǁAggregatorǁexecute__mutmut_21(
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

    async def xǁAggregatorǁexecute__mutmut_22(
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
            "XXaggregator_executeXX",
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

    async def xǁAggregatorǁexecute__mutmut_23(
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
            "AGGREGATOR_EXECUTE",
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

    async def xǁAggregatorǁexecute__mutmut_24(
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
            structured=output_schema is None,
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

    async def xǁAggregatorǁexecute__mutmut_25(
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
        response_format = ""
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

    async def xǁAggregatorǁexecute__mutmut_26(
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
        if output_schema is None:
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

    async def xǁAggregatorǁexecute__mutmut_27(
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
            response_format = None
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_28(
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
                "XXtypeXX": "json_schema",
                "json_schema": {
                    "name": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_29(
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
                "TYPE": "json_schema",
                "json_schema": {
                    "name": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_30(
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
                "type": "XXjson_schemaXX",
                "json_schema": {
                    "name": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_31(
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
                "type": "JSON_SCHEMA",
                "json_schema": {
                    "name": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_32(
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
                "XXjson_schemaXX": {
                    "name": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_33(
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
                "JSON_SCHEMA": {
                    "name": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_34(
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
                    "XXnameXX": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_35(
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
                    "NAME": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_36(
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
                    "name": "XXchimera_outputXX",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_37(
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
                    "name": "CHIMERA_OUTPUT",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_38(
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
                    "XXstrictXX": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_39(
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
                    "STRICT": True,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_40(
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
                    "strict": False,
                    "schema": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_41(
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
                    "XXschemaXX": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_42(
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
                    "SCHEMA": output_schema,
                },
            }
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_43(
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
            None, messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_44(
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
            stage.model, None, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_45(
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
            stage.model, messages, temperature=None, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_46(
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
            stage.model, messages, temperature=0.2, response_format=None,
        )

    async def xǁAggregatorǁexecute__mutmut_47(
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
            messages, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_48(
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
            stage.model, temperature=0.2, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_49(
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
            stage.model, messages, response_format=response_format,
        )

    async def xǁAggregatorǁexecute__mutmut_50(
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
            stage.model, messages, temperature=0.2, )

    async def xǁAggregatorǁexecute__mutmut_51(
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
            stage.model, messages, temperature=1.2, response_format=response_format,
        )

mutants_xǁAggregatorǁ__init____mutmut['_mutmut_orig'] = Aggregator.xǁAggregatorǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁAggregatorǁ__init____mutmut['xǁAggregatorǁ__init____mutmut_1'] = Aggregator.xǁAggregatorǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁAggregatorǁ__init____mutmut['xǁAggregatorǁ__init____mutmut_2'] = Aggregator.xǁAggregatorǁ__init____mutmut_2 # type: ignore # mutmut generated

mutants_xǁAggregatorǁexecute__mutmut['_mutmut_orig'] = Aggregator.xǁAggregatorǁexecute__mutmut_orig # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_1'] = Aggregator.xǁAggregatorǁexecute__mutmut_1 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_2'] = Aggregator.xǁAggregatorǁexecute__mutmut_2 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_3'] = Aggregator.xǁAggregatorǁexecute__mutmut_3 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_4'] = Aggregator.xǁAggregatorǁexecute__mutmut_4 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_5'] = Aggregator.xǁAggregatorǁexecute__mutmut_5 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_6'] = Aggregator.xǁAggregatorǁexecute__mutmut_6 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_7'] = Aggregator.xǁAggregatorǁexecute__mutmut_7 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_8'] = Aggregator.xǁAggregatorǁexecute__mutmut_8 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_9'] = Aggregator.xǁAggregatorǁexecute__mutmut_9 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_10'] = Aggregator.xǁAggregatorǁexecute__mutmut_10 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_11'] = Aggregator.xǁAggregatorǁexecute__mutmut_11 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_12'] = Aggregator.xǁAggregatorǁexecute__mutmut_12 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_13'] = Aggregator.xǁAggregatorǁexecute__mutmut_13 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_14'] = Aggregator.xǁAggregatorǁexecute__mutmut_14 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_15'] = Aggregator.xǁAggregatorǁexecute__mutmut_15 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_16'] = Aggregator.xǁAggregatorǁexecute__mutmut_16 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_17'] = Aggregator.xǁAggregatorǁexecute__mutmut_17 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_18'] = Aggregator.xǁAggregatorǁexecute__mutmut_18 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_19'] = Aggregator.xǁAggregatorǁexecute__mutmut_19 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_20'] = Aggregator.xǁAggregatorǁexecute__mutmut_20 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_21'] = Aggregator.xǁAggregatorǁexecute__mutmut_21 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_22'] = Aggregator.xǁAggregatorǁexecute__mutmut_22 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_23'] = Aggregator.xǁAggregatorǁexecute__mutmut_23 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_24'] = Aggregator.xǁAggregatorǁexecute__mutmut_24 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_25'] = Aggregator.xǁAggregatorǁexecute__mutmut_25 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_26'] = Aggregator.xǁAggregatorǁexecute__mutmut_26 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_27'] = Aggregator.xǁAggregatorǁexecute__mutmut_27 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_28'] = Aggregator.xǁAggregatorǁexecute__mutmut_28 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_29'] = Aggregator.xǁAggregatorǁexecute__mutmut_29 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_30'] = Aggregator.xǁAggregatorǁexecute__mutmut_30 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_31'] = Aggregator.xǁAggregatorǁexecute__mutmut_31 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_32'] = Aggregator.xǁAggregatorǁexecute__mutmut_32 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_33'] = Aggregator.xǁAggregatorǁexecute__mutmut_33 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_34'] = Aggregator.xǁAggregatorǁexecute__mutmut_34 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_35'] = Aggregator.xǁAggregatorǁexecute__mutmut_35 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_36'] = Aggregator.xǁAggregatorǁexecute__mutmut_36 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_37'] = Aggregator.xǁAggregatorǁexecute__mutmut_37 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_38'] = Aggregator.xǁAggregatorǁexecute__mutmut_38 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_39'] = Aggregator.xǁAggregatorǁexecute__mutmut_39 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_40'] = Aggregator.xǁAggregatorǁexecute__mutmut_40 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_41'] = Aggregator.xǁAggregatorǁexecute__mutmut_41 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_42'] = Aggregator.xǁAggregatorǁexecute__mutmut_42 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_43'] = Aggregator.xǁAggregatorǁexecute__mutmut_43 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_44'] = Aggregator.xǁAggregatorǁexecute__mutmut_44 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_45'] = Aggregator.xǁAggregatorǁexecute__mutmut_45 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_46'] = Aggregator.xǁAggregatorǁexecute__mutmut_46 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_47'] = Aggregator.xǁAggregatorǁexecute__mutmut_47 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_48'] = Aggregator.xǁAggregatorǁexecute__mutmut_48 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_49'] = Aggregator.xǁAggregatorǁexecute__mutmut_49 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_50'] = Aggregator.xǁAggregatorǁexecute__mutmut_50 # type: ignore # mutmut generated
mutants_xǁAggregatorǁexecute__mutmut['xǁAggregatorǁexecute__mutmut_51'] = Aggregator.xǁAggregatorǁexecute__mutmut_51 # type: ignore # mutmut generated


__all__ = ["Aggregator", "StageResult", "build_merge_prompt"]
