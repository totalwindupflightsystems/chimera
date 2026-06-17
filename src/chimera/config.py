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


class Provider(BaseModel):
    """A provider gateway base URL."""

    base_url: str
    api_key_env: str | None = None
    api_key: str | None = None


class ModelEntry(BaseModel):
    """One model in the catalog with weighted category scores."""

    categories: dict[str, float] = Field(default_factory=dict)
    cost_tier: str = "standard"
    provider: str
    cost_per_1k_input: float | None = None
    cost_per_1k_output: float | None = None
    litellm_model: str | None = None

    def cost_rate_input(self) -> float:
        if self.cost_per_1k_input is not None:
            return self.cost_per_1k_input
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[0]

    def cost_rate_output(self) -> float:
        if self.cost_per_1k_output is not None:
            return self.cost_per_1k_output
        return DEFAULT_COST_RATES.get(self.cost_tier, DEFAULT_COST_RATES["standard"])[1]


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


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


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


class ChimeraConfig(BaseModel):
    """The full parsed chimera.yaml document."""

    providers: dict[str, Provider] = Field(default_factory=dict)
    models: dict[str, ModelEntry] = Field(default_factory=dict)
    defaults: Defaults
    formations: dict[str, FormationPreset] = Field(default_factory=dict)
    observability: Observability = Field(default_factory=Observability)
    server: ServerConfig = Field(default_factory=ServerConfig)
    api_keys: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _resolve_provider_api_keys(self) -> "ChimeraConfig":
        for provider in self.providers.values():
            if provider.api_key is None and provider.api_key_env:
                provider.api_key = os.environ.get(provider.api_key_env)
        return self

    def get_model(self, name: str) -> ModelEntry:
        """Return a model entry, raising ``KeyError`` if unknown."""
        if name not in self.models:
            raise KeyError(f"Unknown model: {name!r}")
        return self.models[name]

    def resolve_model_alias(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name == "default":
            return self.defaults.default_aggregator
        if name == "default_worker":
            return self.defaults.default_worker
        return name

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


__all__ = [
    "ChimeraConfig",
    "Defaults",
    "FormationPreset",
    "LangfuseConfig",
    "ModelEntry",
    "Observability",
    "Provider",
    "ServerConfig",
    "DEFAULT_COST_RATES",
    "find_config_path",
    "load_config",
]
