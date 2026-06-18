"""Session manager and context pipe for the web interface.

The web UI wraps the core Engine with session-scoped state so multi-turn
conversations can carry forward dispatcher choices, worker outputs, and
aggregator results into the next deliberation's context.

**Important:** this is a *wrapper* over the existing stateless API.
The core Engine, CLI, normal REST API, and MCP surface remain fully
stateless.  Only the web routes inject session context.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class Turn:
    """One complete deliberation turn in a session."""

    user_prompt: str
    answer: str
    formation: str
    dispatch_model: str
    worker_models: list[str] = field(default_factory=list)
    aggregator_model: str = ""
    total_tokens: int = 0
    total_cost: float = 0.0
    timestamp: float = 0.0

    def context_snippet(self) -> str:
        """A compact summary for injection into the next turn's dispatcher prompt."""
        workers = ", ".join(self.worker_models) if self.worker_models else "unknown"
        return (
            f"**Turn**: User asked: {self.user_prompt[:200]}\n"
            f"**Dispatch**: formation={self.formation}, "
            f"workers=[{workers}], aggregator={self.aggregator_model}\n"
            f"**Result**: {self.answer[:300]}\n"
        )


@dataclass(slots=True)
class Session:
    """A web UI session — holds turn history and builds context for the next call."""

    session_id: str
    created_at: float
    turns: list[Turn] = field(default_factory=list)
    max_context_turns: int = 10  # Only inject the last N turns
    #: SSE events from the most recent deliberation, stored for replay
    #: to late-connecting subscribers (race-condition guard).
    last_sse_events: list[tuple[str, dict]] = field(default_factory=list)

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def add_turn(self, turn: Turn) -> None:
        self.turns.append(turn)

    def build_context_preamble(self) -> str:
        """Build the context preamble injected before the current user prompt.

        Injects a summary of recent turns so the dispatcher can design the
        DAG with full awareness of what came before — which models were used,
        what formations worked, what the previous answers were.
        """
        relevant = self.turns[-self.max_context_turns :]
        if not relevant:
            return ""

        parts = ["## Conversation history (previous turns in this session)"]
        for i, turn in enumerate(relevant, 1):
            parts.append(f"### Turn {i}\n{turn.context_snippet()}")

        parts.append(
            "## Current turn\n"
            "The user's new request follows. Use the history above to inform "
            "your DAG design — prefer formations and models that worked well."
        )
        return "\n".join(parts)

    def augmented_prompt(self, user_prompt: str) -> str:
        """Return the user's prompt with context preamble prepended."""
        preamble = self.build_context_preamble()
        if not preamble:
            return user_prompt
        return f"{preamble}\n\n{user_prompt}"


class SessionManager:
    """Thread-safe in-memory session store.

    Sessions live for the lifetime of the server process.  A production
    deployment would use Redis, but in-memory is correct for the single-node
    use case Chimera targets.
    """

    def __init__(self) -> None:
        import time

        self._sessions: dict[str, Session] = {}
        self._created_at = time.monotonic()

    def create(self) -> Session:
        import time

        sid = uuid.uuid4().hex[:12]
        session = Session(session_id=sid, created_at=time.time())
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    @property
    def session_count(self) -> int:
        return len(self._sessions)
