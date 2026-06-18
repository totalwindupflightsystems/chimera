"""Provider circuit breakers for Chimera.

Protects the system from cascading failures when a model/provider is
consistently failing. Wraps individual model completions with a
state machine:

* **CLOSED** — normal operation; calls proceed.
* **OPEN** — after N consecutive failures; calls are fast-failed.
* **HALF_OPEN** — after recovery_timeout expires; allows 1 test request.

Configuration (chimera.yaml):

.. code-block:: yaml

    circuit_breakers:
      default:
        failure_threshold: 5
        recovery_timeout_s: 30
        half_open_max_requests: 1
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

import structlog

from chimera.config import CircuitBreakerConfig

if TYPE_CHECKING:
    from chimera.gateway import GatewayResponse

log = structlog.get_logger("chimera.circuit_breaker")


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict

class CircuitState(Enum):
    CLOSED = auto()     # Normal
    OPEN = auto()       # Failing — fast-fail
    HALF_OPEN = auto()  # Testing recovery


@dataclass(slots=True)
class ProviderCircuitBreaker:
    """A circuit breaker for one provider/model endpoint.

    Wraps calls through :meth:`call` and automatically transitions
    between CLOSED → OPEN → HALF_OPEN → CLOSED based on failure patterns.
    """

    name: str
    config: CircuitBreakerConfig

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    opened_at: float = 0.0
    half_open_in_flight: int = 0

    # --- Public API ---

    def before_call(self) -> bool:
        """Check if a call should be allowed.

        Returns True if the call may proceed, False if it should be
        fast-failed because the circuit is OPEN.
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.opened_at >= self.config.recovery_timeout_s:
                log.info(
                    "circuit_breaker_half_open", name=self.name,
                    timeout_s=self.config.recovery_timeout_s,
                )
                self.state = CircuitState.HALF_OPEN
                self.half_open_in_flight = 0
            else:
                return False

        # HALF_OPEN — allow up to half_open_max_requests
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_in_flight < self.config.half_open_max_requests:
                self.half_open_in_flight += 1
                return True
            return False

        return True

    def on_success(self) -> None:
        """Record a successful call."""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_in_flight = max(0, self.half_open_in_flight - 1)
            if self.half_open_in_flight == 0:
                log.info("circuit_breaker_closed", name=self.name)
                self.state = CircuitState.CLOSED
        elif self.state == CircuitState.CLOSED:
            pass  # stay closed

    def on_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.monotonic()

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_in_flight = max(0, self.half_open_in_flight - 1)
            if self.half_open_in_flight == 0:
                log.warning(
                    "circuit_breaker_reopened", name=self.name,
                    failure_count=self.failure_count,
                )
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
                return

        if self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
            log.warning(
                "circuit_breaker_opened", name=self.name,
                failure_count=self.failure_count,
                threshold=self.config.failure_threshold,
            )
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
mutants_x_fast_fail_response__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_fast_fail_response__mutmut)
def fast_fail_response(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        model=breaker_name,
        tokens_input=0,
        tokens_output=0,
    )


def x_fast_fail_response__mutmut_orig(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        model=breaker_name,
        tokens_input=0,
        tokens_output=0,
    )


def x_fast_fail_response__mutmut_1(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=None,
        model=breaker_name,
        tokens_input=0,
        tokens_output=0,
    )


def x_fast_fail_response__mutmut_2(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        model=None,
        tokens_input=0,
        tokens_output=0,
    )


def x_fast_fail_response__mutmut_3(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        model=breaker_name,
        tokens_input=None,
        tokens_output=0,
    )


def x_fast_fail_response__mutmut_4(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        model=breaker_name,
        tokens_input=0,
        tokens_output=None,
    )


def x_fast_fail_response__mutmut_5(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        model=breaker_name,
        tokens_input=0,
        tokens_output=0,
    )


def x_fast_fail_response__mutmut_6(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        tokens_input=0,
        tokens_output=0,
    )


def x_fast_fail_response__mutmut_7(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        model=breaker_name,
        tokens_output=0,
    )


def x_fast_fail_response__mutmut_8(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        model=breaker_name,
        tokens_input=0,
        )


def x_fast_fail_response__mutmut_9(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        model=breaker_name,
        tokens_input=1,
        tokens_output=0,
    )


def x_fast_fail_response__mutmut_10(breaker_name: str) -> GatewayResponse:
    """Build a GatewayResponse indicating the circuit is open."""
    from chimera.gateway import GatewayResponse  # noqa: F811

    return GatewayResponse(
        text=f"[circuit open: {breaker_name} is temporarily unavailable]",
        model=breaker_name,
        tokens_input=0,
        tokens_output=1,
    )

mutants_x_fast_fail_response__mutmut['_mutmut_orig'] = x_fast_fail_response__mutmut_orig # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_1'] = x_fast_fail_response__mutmut_1 # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_2'] = x_fast_fail_response__mutmut_2 # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_3'] = x_fast_fail_response__mutmut_3 # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_4'] = x_fast_fail_response__mutmut_4 # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_5'] = x_fast_fail_response__mutmut_5 # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_6'] = x_fast_fail_response__mutmut_6 # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_7'] = x_fast_fail_response__mutmut_7 # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_8'] = x_fast_fail_response__mutmut_8 # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_9'] = x_fast_fail_response__mutmut_9 # type: ignore # mutmut generated
mutants_x_fast_fail_response__mutmut['x_fast_fail_response__mutmut_10'] = x_fast_fail_response__mutmut_10 # type: ignore # mutmut generated
mutants_x_make_circuit_breaker_fast_fail_response__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_make_circuit_breaker_fast_fail_response__mutmut)
def make_circuit_breaker_fast_fail_response(
    breaker_name: str,
) -> GatewayResponse:
    """Create a GatewayResponse for a circuit-open fast-fail.

    The response text indicates the breaker name so callers can
    identify which model was skipped.
    """
    return fast_fail_response(breaker_name)


def x_make_circuit_breaker_fast_fail_response__mutmut_orig(
    breaker_name: str,
) -> GatewayResponse:
    """Create a GatewayResponse for a circuit-open fast-fail.

    The response text indicates the breaker name so callers can
    identify which model was skipped.
    """
    return fast_fail_response(breaker_name)


def x_make_circuit_breaker_fast_fail_response__mutmut_1(
    breaker_name: str,
) -> GatewayResponse:
    """Create a GatewayResponse for a circuit-open fast-fail.

    The response text indicates the breaker name so callers can
    identify which model was skipped.
    """
    return fast_fail_response(None)

mutants_x_make_circuit_breaker_fast_fail_response__mutmut['_mutmut_orig'] = x_make_circuit_breaker_fast_fail_response__mutmut_orig # type: ignore # mutmut generated
mutants_x_make_circuit_breaker_fast_fail_response__mutmut['x_make_circuit_breaker_fast_fail_response__mutmut_1'] = x_make_circuit_breaker_fast_fail_response__mutmut_1 # type: ignore # mutmut generated
