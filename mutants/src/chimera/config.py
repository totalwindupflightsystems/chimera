"""Chimera configuration loading and validation.

Reads ``chimera.yaml`` into Pydantic v2 models. Environment variables referenced
as ``${VAR}`` in the YAML are substituted from ``os.environ`` at load time.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")

#: Default per-cost-tier USD rates per 1k tokens (input, output).
DEFAULT_COST_RATES: dict[str, tuple[float, float]] = {
    "budget": (0.00014, 0.00028),
    "standard": (0.0005, 0.0015),
    "premium": (0.003, 0.015),
}


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


class Provider(BaseModel):
    """A provider gateway base URL."""

    base_url: str
    api_key_env: str | None = None
    api_key: str | None = None
mutants_xǁModelEntryǁcost_rate_input__mutmut: MutantDict = {}  # type: ignore
mutants_xǁModelEntryǁcost_rate_output__mutmut: MutantDict = {}  # type: ignore


class ModelEntry(BaseModel):
    """One model in the catalog with weighted category scores."""

    categories: dict[str, float] = Field(default_factory=dict)
    cost_tier: str = "standard"
    provider: str
    cost_per_1k_input: float | None = None
    cost_per_1k_output: float | None = None
    litellm_model: str | None = None

    @_mutmut_mutated(mutants_xǁModelEntryǁcost_rate_input__mutmut)
    def cost_rate_input(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[0]

    def xǁModelEntryǁcost_rate_input__mutmut_orig(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[0]

    def xǁModelEntryǁcost_rate_input__mutmut_1(self) -> float:
        if self.cost_per_1k_input is None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[0]

    def xǁModelEntryǁcost_rate_input__mutmut_2(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(None, DEFAULT_COST_RATES["standard"])[0]

    def xǁModelEntryǁcost_rate_input__mutmut_3(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(self.cost_tier, None)[0]

    def xǁModelEntryǁcost_rate_input__mutmut_4(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(DEFAULT_COST_RATES["standard"])[0]

    def xǁModelEntryǁcost_rate_input__mutmut_5(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(self.cost_tier, )[0]

    def xǁModelEntryǁcost_rate_input__mutmut_6(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["XXstandardXX"])[0]

    def xǁModelEntryǁcost_rate_input__mutmut_7(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["STANDARD"])[0]

    def xǁModelEntryǁcost_rate_input__mutmut_8(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[1]

    @_mutmut_mutated(mutants_xǁModelEntryǁcost_rate_output__mutmut)
    def cost_rate_output(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[1]

    def xǁModelEntryǁcost_rate_output__mutmut_orig(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[1]

    def xǁModelEntryǁcost_rate_output__mutmut_1(self) -> float:
        if self.cost_per_1k_output is None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[1]

    def xǁModelEntryǁcost_rate_output__mutmut_2(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(None, DEFAULT_COST_RATES["standard"])[1]

    def xǁModelEntryǁcost_rate_output__mutmut_3(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(self.cost_tier, None)[1]

    def xǁModelEntryǁcost_rate_output__mutmut_4(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(DEFAULT_COST_RATES["standard"])[1]

    def xǁModelEntryǁcost_rate_output__mutmut_5(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(self.cost_tier, )[1]

    def xǁModelEntryǁcost_rate_output__mutmut_6(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["XXstandardXX"])[1]

    def xǁModelEntryǁcost_rate_output__mutmut_7(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["STANDARD"])[1]

    def xǁModelEntryǁcost_rate_output__mutmut_8(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[2]

mutants_xǁModelEntryǁcost_rate_input__mutmut['_mutmut_orig'] = ModelEntry.xǁModelEntryǁcost_rate_input__mutmut_orig # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_input__mutmut['xǁModelEntryǁcost_rate_input__mutmut_1'] = ModelEntry.xǁModelEntryǁcost_rate_input__mutmut_1 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_input__mutmut['xǁModelEntryǁcost_rate_input__mutmut_2'] = ModelEntry.xǁModelEntryǁcost_rate_input__mutmut_2 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_input__mutmut['xǁModelEntryǁcost_rate_input__mutmut_3'] = ModelEntry.xǁModelEntryǁcost_rate_input__mutmut_3 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_input__mutmut['xǁModelEntryǁcost_rate_input__mutmut_4'] = ModelEntry.xǁModelEntryǁcost_rate_input__mutmut_4 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_input__mutmut['xǁModelEntryǁcost_rate_input__mutmut_5'] = ModelEntry.xǁModelEntryǁcost_rate_input__mutmut_5 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_input__mutmut['xǁModelEntryǁcost_rate_input__mutmut_6'] = ModelEntry.xǁModelEntryǁcost_rate_input__mutmut_6 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_input__mutmut['xǁModelEntryǁcost_rate_input__mutmut_7'] = ModelEntry.xǁModelEntryǁcost_rate_input__mutmut_7 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_input__mutmut['xǁModelEntryǁcost_rate_input__mutmut_8'] = ModelEntry.xǁModelEntryǁcost_rate_input__mutmut_8 # type: ignore # mutmut generated

mutants_xǁModelEntryǁcost_rate_output__mutmut['_mutmut_orig'] = ModelEntry.xǁModelEntryǁcost_rate_output__mutmut_orig # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_output__mutmut['xǁModelEntryǁcost_rate_output__mutmut_1'] = ModelEntry.xǁModelEntryǁcost_rate_output__mutmut_1 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_output__mutmut['xǁModelEntryǁcost_rate_output__mutmut_2'] = ModelEntry.xǁModelEntryǁcost_rate_output__mutmut_2 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_output__mutmut['xǁModelEntryǁcost_rate_output__mutmut_3'] = ModelEntry.xǁModelEntryǁcost_rate_output__mutmut_3 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_output__mutmut['xǁModelEntryǁcost_rate_output__mutmut_4'] = ModelEntry.xǁModelEntryǁcost_rate_output__mutmut_4 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_output__mutmut['xǁModelEntryǁcost_rate_output__mutmut_5'] = ModelEntry.xǁModelEntryǁcost_rate_output__mutmut_5 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_output__mutmut['xǁModelEntryǁcost_rate_output__mutmut_6'] = ModelEntry.xǁModelEntryǁcost_rate_output__mutmut_6 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_output__mutmut['xǁModelEntryǁcost_rate_output__mutmut_7'] = ModelEntry.xǁModelEntryǁcost_rate_output__mutmut_7 # type: ignore # mutmut generated
mutants_xǁModelEntryǁcost_rate_output__mutmut['xǁModelEntryǁcost_rate_output__mutmut_8'] = ModelEntry.xǁModelEntryǁcost_rate_output__mutmut_8 # type: ignore # mutmut generated


class Defaults(BaseModel):
    dispatcher: str
    default_worker: str
    default_aggregator: str
    # When True the dispatcher's model choice for these roles is ignored in
    # favor of the configured default. See ``dispatcher._normalize_result``.
    lock_dispatcher: bool = False
    lock_aggregator: bool = False


class FormationPreset(BaseModel):
    """A named formation template.

    Exactly one of ``mode`` (auto), a worker/aggregator structure, or an explicit
    ``dag`` definition should be set.

    When ``dag`` is provided it is a full client/config-defined DAG (a mapping
    with ``stages`` and ``edges`` keys, matching the runtime DAG shape). It wins
    over the legacy ``workers``/``aggregator`` fields.
    """

    mode: str | None = None
    workers: int | None = None
    worker_models: list[str] | None = None
    aggregator: str | None = None
    aggregators: list[str] | None = None
    merge: str | None = None
    audit: str | None = None
    dag: dict[str, Any] | None = None

    @property
    def is_auto(self) -> bool:
        return self.mode == "auto"

    @property
    def has_dag(self) -> bool:
        return self.dag is not None


class LangfuseConfig(BaseModel):
    enabled: bool = False
    host: str = "https://cloud.langfuse.com"
    public_key: str | None = None
    secret_key: str | None = None


class Observability(BaseModel):
    log_level: str = "info"
    trace_enabled: bool = True
    use_stdout: bool = True
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)


class RetryConfig(BaseModel):
    """Exponential backoff retry policy for provider calls (F7)."""

    max_attempts: int = 3
    base_delay_ms: int = 500
    max_delay_ms: int = 10000
    backoff_multiplier: float = 2.0


class QueueConfig(BaseModel):
    """In-memory request queue / backpressure config (F5)."""

    max_concurrent: int = 10
    max_queue_depth: int = 100


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class AuthKeyEntry(BaseModel):
    """A named API key for list-based authentication."""

    key: str
    name: str = "default"


class AuthConfig(BaseModel):
    """Authentication configuration for the REST API."""

    enabled: bool = False
    mode: str = "env"  # "env" | "list"
    keys: list[AuthKeyEntry] = Field(default_factory=list)


class RateLimitConfig(BaseModel):
    """In-memory token-bucket rate limiting configuration."""

    enabled: bool = False
    requests_per_minute: int = 60
    burst_size: int = 10


class CircuitBreakerConfig(BaseModel):
    """Per-provider circuit breaker configuration."""

    failure_threshold: int = 5
    recovery_timeout_s: int = 30
    half_open_max_requests: int = 1


class DeliberationOverrides(BaseModel):
    """Request-level overrides — maximum flexibility per deliberation call.

    Any field left as None falls back to config defaults.
    These let the caller control which models are allowed, excluded,
    or forced for specific roles without changing the config file.
    """

    allowed_models: list[str] | None = None     # Only these models permitted
    disallowed_models: list[str] | None = None   # Exclude these models
    dispatcher_model: str | None = None          # Force dispatcher model
    aggregator_model: str | None = None               # Force aggregator model
    worker_model: str | None = None              # Force default worker model
    output_schema: dict[str, Any] | None = None  # JSON Schema for final answer
    stage_models: dict[str, str] | None = None   # Per-stage model overrides (stage_id → model)
mutants_xǁChimeraConfigǁget_model__mutmut: MutantDict = {}  # type: ignore
mutants_xǁChimeraConfigǁresolve_model_alias__mutmut: MutantDict = {}  # type: ignore
mutants_xǁChimeraConfigǁcatalog_description__mutmut: MutantDict = {}  # type: ignore


class ChimeraConfig(BaseModel):
    """The full parsed chimera.yaml document."""

    providers: dict[str, Provider] = Field(default_factory=dict)
    models: dict[str, ModelEntry] = Field(default_factory=dict)
    defaults: Defaults
    formations: dict[str, FormationPreset] = Field(default_factory=dict)
    observability: Observability = Field(default_factory=Observability)
    server: ServerConfig = Field(default_factory=ServerConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    circuit_breakers: dict[str, CircuitBreakerConfig] = Field(default_factory=dict)
    api_keys: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _resolve_provider_api_keys(self) -> ChimeraConfig:
        for provider in self.providers.values():
            if provider.api_key is None and provider.api_key_env:
                provider.api_key = os.environ.get(provider.api_key_env)
        return self

    @_mutmut_mutated(mutants_xǁChimeraConfigǁget_model__mutmut)
    def get_model(self, name: str) -> ModelEntry:
        """Return a model entry, raising ``KeyError`` if unknown."""
        if name not in self.models:
            raise KeyError(f"Unknown model: {name!r}")
        return self.models[name]

    def xǁChimeraConfigǁget_model__mutmut_orig(self, name: str) -> ModelEntry:
        """Return a model entry, raising ``KeyError`` if unknown."""
        if name not in self.models:
            raise KeyError(f"Unknown model: {name!r}")
        return self.models[name]

    def xǁChimeraConfigǁget_model__mutmut_1(self, name: str) -> ModelEntry:
        """Return a model entry, raising ``KeyError`` if unknown."""
        if name in self.models:
            raise KeyError(f"Unknown model: {name!r}")
        return self.models[name]

    def xǁChimeraConfigǁget_model__mutmut_2(self, name: str) -> ModelEntry:
        """Return a model entry, raising ``KeyError`` if unknown."""
        if name not in self.models:
            raise KeyError(None)
        return self.models[name]

    @_mutmut_mutated(mutants_xǁChimeraConfigǁresolve_model_alias__mutmut)
    def resolve_model_alias(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name == "default":
            return self.defaults.default_aggregator
        if name == "default_worker":
            return self.defaults.default_worker
        return name

    def xǁChimeraConfigǁresolve_model_alias__mutmut_orig(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name == "default":
            return self.defaults.default_aggregator
        if name == "default_worker":
            return self.defaults.default_worker
        return name

    def xǁChimeraConfigǁresolve_model_alias__mutmut_1(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name != "default":
            return self.defaults.default_aggregator
        if name == "default_worker":
            return self.defaults.default_worker
        return name

    def xǁChimeraConfigǁresolve_model_alias__mutmut_2(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name == "XXdefaultXX":
            return self.defaults.default_aggregator
        if name == "default_worker":
            return self.defaults.default_worker
        return name

    def xǁChimeraConfigǁresolve_model_alias__mutmut_3(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name == "DEFAULT":
            return self.defaults.default_aggregator
        if name == "default_worker":
            return self.defaults.default_worker
        return name

    def xǁChimeraConfigǁresolve_model_alias__mutmut_4(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name == "default":
            return self.defaults.default_aggregator
        if name != "default_worker":
            return self.defaults.default_worker
        return name

    def xǁChimeraConfigǁresolve_model_alias__mutmut_5(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name == "default":
            return self.defaults.default_aggregator
        if name == "XXdefault_workerXX":
            return self.defaults.default_worker
        return name

    def xǁChimeraConfigǁresolve_model_alias__mutmut_6(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name == "default":
            return self.defaults.default_aggregator
        if name == "DEFAULT_WORKER":
            return self.defaults.default_worker
        return name

    @_mutmut_mutated(mutants_xǁChimeraConfigǁcatalog_description__mutmut)
    def catalog_description(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_orig(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_1(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = None
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_2(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = None
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_3(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                None
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_4(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = "XX, XX".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_5(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(None, key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_6(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=None)
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_7(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_8(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), )
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_9(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: None)
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_10(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: +kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_11(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[2])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_12(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[1])
            )
            lines.append(
                None
            )
        return "\n".join(lines)

    def xǁChimeraConfigǁcatalog_description__mutmut_13(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(None)

    def xǁChimeraConfigǁcatalog_description__mutmut_14(self) -> str:
        """Human-readable model catalog for the dispatcher prompt."""
        lines: list[str] = []
        for name, entry in self.models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "XX\nXX".join(lines)

mutants_xǁChimeraConfigǁget_model__mutmut['_mutmut_orig'] = ChimeraConfig.xǁChimeraConfigǁget_model__mutmut_orig # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁget_model__mutmut['xǁChimeraConfigǁget_model__mutmut_1'] = ChimeraConfig.xǁChimeraConfigǁget_model__mutmut_1 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁget_model__mutmut['xǁChimeraConfigǁget_model__mutmut_2'] = ChimeraConfig.xǁChimeraConfigǁget_model__mutmut_2 # type: ignore # mutmut generated

mutants_xǁChimeraConfigǁresolve_model_alias__mutmut['_mutmut_orig'] = ChimeraConfig.xǁChimeraConfigǁresolve_model_alias__mutmut_orig # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁresolve_model_alias__mutmut['xǁChimeraConfigǁresolve_model_alias__mutmut_1'] = ChimeraConfig.xǁChimeraConfigǁresolve_model_alias__mutmut_1 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁresolve_model_alias__mutmut['xǁChimeraConfigǁresolve_model_alias__mutmut_2'] = ChimeraConfig.xǁChimeraConfigǁresolve_model_alias__mutmut_2 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁresolve_model_alias__mutmut['xǁChimeraConfigǁresolve_model_alias__mutmut_3'] = ChimeraConfig.xǁChimeraConfigǁresolve_model_alias__mutmut_3 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁresolve_model_alias__mutmut['xǁChimeraConfigǁresolve_model_alias__mutmut_4'] = ChimeraConfig.xǁChimeraConfigǁresolve_model_alias__mutmut_4 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁresolve_model_alias__mutmut['xǁChimeraConfigǁresolve_model_alias__mutmut_5'] = ChimeraConfig.xǁChimeraConfigǁresolve_model_alias__mutmut_5 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁresolve_model_alias__mutmut['xǁChimeraConfigǁresolve_model_alias__mutmut_6'] = ChimeraConfig.xǁChimeraConfigǁresolve_model_alias__mutmut_6 # type: ignore # mutmut generated

mutants_xǁChimeraConfigǁcatalog_description__mutmut['_mutmut_orig'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_orig # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_1'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_1 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_2'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_2 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_3'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_3 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_4'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_4 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_5'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_5 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_6'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_6 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_7'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_7 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_8'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_8 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_9'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_9 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_10'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_10 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_11'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_11 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_12'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_12 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_13'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_13 # type: ignore # mutmut generated
mutants_xǁChimeraConfigǁcatalog_description__mutmut['xǁChimeraConfigǁcatalog_description__mutmut_14'] = ChimeraConfig.xǁChimeraConfigǁcatalog_description__mutmut_14 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__substitute_env__mutmut)
def _substitute_env(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ""), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_orig(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ""), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_1(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            None, value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_2(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ""), None
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_3(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_4(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ""), )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_5(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: None, value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_6(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(None, ""), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_7(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), None), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_8(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(""), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_9(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_10(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(None), ""), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_11(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(2), ""), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_12(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), "XXXX"), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_13(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ""), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(None) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def x__substitute_env__mutmut_14(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ""), value
        )
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(None) for v in value]
    return value

mutants_x__substitute_env__mutmut['_mutmut_orig'] = x__substitute_env__mutmut_orig # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_1'] = x__substitute_env__mutmut_1 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_2'] = x__substitute_env__mutmut_2 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_3'] = x__substitute_env__mutmut_3 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_4'] = x__substitute_env__mutmut_4 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_5'] = x__substitute_env__mutmut_5 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_6'] = x__substitute_env__mutmut_6 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_7'] = x__substitute_env__mutmut_7 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_8'] = x__substitute_env__mutmut_8 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_9'] = x__substitute_env__mutmut_9 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_10'] = x__substitute_env__mutmut_10 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_11'] = x__substitute_env__mutmut_11 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_12'] = x__substitute_env__mutmut_12 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_13'] = x__substitute_env__mutmut_13 # type: ignore # mutmut generated
mutants_x__substitute_env__mutmut['x__substitute_env__mutmut_14'] = x__substitute_env__mutmut_14 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_find_config_path__mutmut)
def find_config_path(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_orig(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_1(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = None
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_2(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(None).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_3(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start and os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_4(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = None
        if target.is_file():
            return target
    raise FileNotFoundError(
        "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_5(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate * "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_6(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "XXchimera.yamlXX"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_7(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "CHIMERA.YAML"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "No chimera.yaml found. Copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_8(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        None
    )


def x_find_config_path__mutmut_9(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "XXNo chimera.yaml found. Copy chimera.yaml.example to chimera.yaml.XX"
    )


def x_find_config_path__mutmut_10(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "no chimera.yaml found. copy chimera.yaml.example to chimera.yaml."
    )


def x_find_config_path__mutmut_11(start: Path | str | None = None) -> Path:
    """Walk up from ``start`` (default cwd) looking for ``chimera.yaml``."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "NO CHIMERA.YAML FOUND. COPY CHIMERA.YAML.EXAMPLE TO CHIMERA.YAML."
    )

mutants_x_find_config_path__mutmut['_mutmut_orig'] = x_find_config_path__mutmut_orig # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_1'] = x_find_config_path__mutmut_1 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_2'] = x_find_config_path__mutmut_2 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_3'] = x_find_config_path__mutmut_3 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_4'] = x_find_config_path__mutmut_4 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_5'] = x_find_config_path__mutmut_5 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_6'] = x_find_config_path__mutmut_6 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_7'] = x_find_config_path__mutmut_7 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_8'] = x_find_config_path__mutmut_8 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_9'] = x_find_config_path__mutmut_9 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_10'] = x_find_config_path__mutmut_10 # type: ignore # mutmut generated
mutants_x_find_config_path__mutmut['x_find_config_path__mutmut_11'] = x_find_config_path__mutmut_11 # type: ignore # mutmut generated
mutants_x_load_config__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_load_config__mutmut)
def load_config(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_orig(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_1(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = None
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_2(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(None) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_3(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = None
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_4(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding=None)
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_5(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="XXutf-8XX")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_6(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="UTF-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_7(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = None
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_8(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(None)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_9(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_10(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(None)
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_11(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = None
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_12(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(None)
    return ChimeraConfig.model_validate(raw)


def x_load_config__mutmut_13(path: Path | str | None = None) -> ChimeraConfig:
    """Load and validate a Chimera config from YAML.

    If ``path`` is ``None``, searches the working directory and its parents for
    ``chimera.yaml``. Environment variable tokens (``${VAR}``) are substituted
    from the process environment.
    """
    config_path = Path(path) if path else find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    return ChimeraConfig.model_validate(None)

mutants_x_load_config__mutmut['_mutmut_orig'] = x_load_config__mutmut_orig # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_1'] = x_load_config__mutmut_1 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_2'] = x_load_config__mutmut_2 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_3'] = x_load_config__mutmut_3 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_4'] = x_load_config__mutmut_4 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_5'] = x_load_config__mutmut_5 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_6'] = x_load_config__mutmut_6 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_7'] = x_load_config__mutmut_7 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_8'] = x_load_config__mutmut_8 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_9'] = x_load_config__mutmut_9 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_10'] = x_load_config__mutmut_10 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_11'] = x_load_config__mutmut_11 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_12'] = x_load_config__mutmut_12 # type: ignore # mutmut generated
mutants_x_load_config__mutmut['x_load_config__mutmut_13'] = x_load_config__mutmut_13 # type: ignore # mutmut generated


__all__ = [
    "AuthConfig",
    "AuthKeyEntry",
    "ChimeraConfig",
    "CircuitBreakerConfig",
    "Defaults",
    "FormationPreset",
    "LangfuseConfig",
    "ModelEntry",
    "Observability",
    "Provider",
    "QueueConfig",
    "RateLimitConfig",
    "RetryConfig",
    "ServerConfig",
    "DEFAULT_COST_RATES",
    "find_config_path",
    "load_config",
]
