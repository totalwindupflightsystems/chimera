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
    enabled: bool = True
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
    timeout_total_s: float | None = None         # Per-request total timeout (≤ admin ceiling)
    timeout_per_stage_s: float | None = None     # Per-request per-stage timeout


class SelectorConfig(BaseModel):
    """Model selection strategy configuration.

    Controls how the category-weighted selector balances quality vs cost.
    """

    price_sensitivity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "How much cost influences model selection. "
            "0.0 = pure quality (cost ignored). "
            "0.5 = balanced. "
            "1.0 = pure cheapest-that-works."
        ),
    )


class StageTimeoutConfig(BaseModel):
    """Per-stage and end-to-end timeout controls.

    All values in seconds. -1 means unlimited. 0 means use the default.

    Hierarchy:
        1. Code default (DEFAULT_STAGE_TIMEOUT_S = 120)
        2. Admin config ceiling (chimera.yaml ``timeout`` section)
        3. Per-request header (X-Chimera-Timeout), cannot exceed admin ceiling
    """

    total_s: float = 300.0
    """End-to-end wall-clock cap for the entire deliberation. -1 = no limit."""

    per_stage_s: float = 120.0
    """Maximum wall-clock seconds for a single stage (worker/aggregator/auditor)."""

    idle_s: float = 30.0
    """Maximum seconds between tokens before the connection is considered stalled.
    Only enforced when min_tokens_per_second is also set."""

    min_tokens_per_second: float = 0.0
    """If > 0 and a stage hits per_stage_s but is still producing tokens above
    this rate, the stage is allowed to continue. 0 = disabled (strict timeout)."""

    connect_s: float = 10.0
    """TCP / HTTP connect timeout for provider API calls."""

    read_s: float = 30.0
    """Socket read timeout for provider API calls."""

    retry_s: float = 60.0
    """Total wall-clock budget for retries on a single stage."""


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
    selector: SelectorConfig = Field(default_factory=SelectorConfig)
    provider_discovery: bool = True  # auto-discover providers from models.dev
    timeout: StageTimeoutConfig = Field(default_factory=StageTimeoutConfig)
    # Optional soft cap on the *aggregator* prompt size in estimated tokens
    # (~4 chars/token). When the natural prompt would exceed this, the
    # longest worker outputs are truncated (preserving shorter ones)
    # until the prompt fits. ``None`` = no cap, backward compatible.
    # Useful when a deliberation uses many large-output workers feeding
    # an aggregator model with a small context window.
    max_aggregator_context_tokens: int | None = None

    @model_validator(mode="after")
    def _resolve_provider_api_keys(self) -> ChimeraConfig:
        for provider in self.providers.values():
            if provider.api_key is None and provider.api_key_env:
                provider.api_key = os.environ.get(provider.api_key_env)
        return self

    def get_model(self, name: str) -> ModelEntry:
        """Return a model entry, raising ``KeyError`` if unknown."""
        if name not in self.models:
            raise KeyError(f"Unknown model: {name!r}")
        return self.models[name]

    @property
    def enabled_models(self) -> dict[str, ModelEntry]:
        """Return only enabled models from the catalog."""
        return {k: v for k, v in self.models.items() if v.enabled}

    def resolve_model_alias(self, name: str) -> str:
        """Resolve ``"default"`` aliases for aggregator/worker to real model names."""
        if name == "default":
            return self.defaults.default_aggregator
        if name == "default_worker":
            return self.defaults.default_worker
        return name

    def catalog_description(self) -> str:
        """Human-readable model catalog for the dispatcher prompt.

        Disabled models are excluded so the dispatcher never sees them.
        """
        lines: list[str] = []
        for name, entry in self.enabled_models.items():
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)


#: Cached contents of ~/.hermes/.env, loaded once as fallback for env-var
#: substitution when ``os.environ`` does not contain the requested variable.
#: Hermes stores API keys in this file; the Chimera config uses ``${VAR}``
#: placeholders that should resolve from it even when the key is not set in
#: the process environment (e.g. cron sessions).
_hermes_dotenv_cache: dict[str, str] | None = None


def _load_hermes_dotenv() -> dict[str, str]:
    """Parse ``~/.hermes/.env`` into a dict, caching the result."""
    global _hermes_dotenv_cache
    if _hermes_dotenv_cache is not None:
        return _hermes_dotenv_cache
    _hermes_dotenv_cache = {}
    env_path = Path("~/.hermes/.env").expanduser()
    if not env_path.is_file():
        return _hermes_dotenv_cache
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            # Strip surrounding quotes
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            _hermes_dotenv_cache[key] = val
    except OSError:
        _hermes_dotenv_cache = {}
    return _hermes_dotenv_cache


def _substitute_env(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens using ``os.environ``.

    Falls back to ``~/.hermes/.env`` for variables not found in the
    process environment (so API keys stored in Hermes' dotenv file
    resolve correctly even in cron sessions).
    """
    if isinstance(value, str):
        dotenv = _load_hermes_dotenv()
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1)) or dotenv.get(m.group(1), ""),
            value,
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

    Resolution order:
    1. Explicit *path* argument
    2. ``CHIMERA_CONFIG`` environment variable
    3. Walk up from cwd looking for ``chimera.yaml``

    Environment variable tokens (``${VAR}``) are substituted from the
    process environment.

    After YAML loading, env-var overrides are applied so that Docker /
    CI users never need to edit the YAML directly:

    * ``CHIMERA_HOST`` / ``CHIMERA_PORT`` → ``server.host`` / ``server.port``
    * ``CHIMERA_DISPATCHER`` / ``CHIMERA_WORKER`` / ``CHIMERA_AGGREGATOR``
      → ``defaults.*`` model overrides
    * ``CHIMERA_LOG_LEVEL`` → ``observability.log_level``
    * ``CHIMERA_AUTH_ENABLED`` → ``auth.enabled`` (``\"true\"`` / ``\"false\"``)
    * ``CHIMERA_RATE_LIMIT_ENABLED`` → ``rate_limit.enabled``
    * ``DEEPSEEK_KEY`` / ``OPENROUTER_KEY`` / ``ZAI_KEY``
      → ``api_keys.*`` shortcuts
    """
    import os as _os

    if path is not None:
        config_path = Path(path)
    elif _os.environ.get("CHIMERA_CONFIG"):
        config_path = Path(_os.environ["CHIMERA_CONFIG"])
    else:
        config_path = find_config_path()
    raw_text = config_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Config {config_path} did not parse to a mapping")
    raw = _substitute_env(raw)
    config = ChimeraConfig.model_validate(raw)
    _apply_env_overrides(config)
    return config


def _apply_env_overrides(config: ChimeraConfig) -> None:
    """Mutate *config* with environment variable overrides.

    This is the bridge between ``chimera.yaml`` and Docker-style
    12-factor config: every commonly-tweaked knob has a
    ``CHIMERA_*`` env var that takes precedence over the file.

    Also auto-discovers providers from models.dev when
    ``provider_discovery`` is enabled and providers are not
    explicitly configured.
    """
    import os as _os

    # ── Server ──
    if _os.environ.get("CHIMERA_HOST"):
        config.server.host = _os.environ["CHIMERA_HOST"]
    if _os.environ.get("CHIMERA_PORT"):
        config.server.port = int(_os.environ["CHIMERA_PORT"])

    # ── Default models ──
    if _os.environ.get("CHIMERA_DISPATCHER"):
        config.defaults.dispatcher = _os.environ["CHIMERA_DISPATCHER"]
    if _os.environ.get("CHIMERA_WORKER"):
        config.defaults.default_worker = _os.environ["CHIMERA_WORKER"]
    if _os.environ.get("CHIMERA_AGGREGATOR"):
        config.defaults.default_aggregator = _os.environ["CHIMERA_AGGREGATOR"]

    # ── Observability ──
    if _os.environ.get("CHIMERA_LOG_LEVEL"):
        config.observability.log_level = _os.environ["CHIMERA_LOG_LEVEL"]

    # ── Toggles ──
    if _os.environ.get("CHIMERA_AUTH_ENABLED", "").lower() in ("true", "1"):
        config.auth.enabled = True
    if _os.environ.get("CHIMERA_RATE_LIMIT_ENABLED", "").lower() in ("true", "1"):
        config.rate_limit.enabled = True

    # ── API key shortcuts (Docker-friendly names) ──
    for env_var, key_name in (
        ("DEEPSEEK_KEY", "deepseek"),
        ("DEEPSEEK_API_KEY", "deepseek"),
        ("OPENROUTER_KEY", "openrouter"),
        ("OPENROUTER_API_KEY", "openrouter"),
        ("OPENAI_KEY", "openai"),
        ("OPENAI_API_KEY", "openai"),
        ("XAI_KEY", "xai"),
        ("XAI_API_KEY", "xai"),
        ("ZAI_KEY", "zai"),
        ("ZAI_API_KEY", "zai"),
        ("ANTHROPIC_KEY", "anthropic"),
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("GEMINI_KEY", "google"),
        ("GEMINI_API_KEY", "google"),
    ):
        if _os.environ.get(env_var):
            config.api_keys[key_name] = _os.environ[env_var]

    # ── Provider auto-discovery (models.dev) ──
    if config.provider_discovery:
        try:
            from chimera.provider_discovery import discover_providers

            discovered_providers, model_pricing = discover_providers(
                api_keys=dict(config.api_keys),
            )
            # Only add providers that aren't already configured
            for name, pdata in discovered_providers.items():
                if name not in config.providers:
                    from chimera.config import Provider as _Provider
                    config.providers[name] = _Provider(
                        base_url=pdata["base_url"],
                        api_key_env=pdata.get("api_key_env"),
                    )

            # Apply model pricing to existing models
            for model_id, pricing in model_pricing.items():
                entry = config.models.get(model_id)
                if entry is not None:
                    if entry.cost_per_1k_input is None:
                        entry.cost_per_1k_input = pricing["input"]
                    if entry.cost_per_1k_output is None:
                        entry.cost_per_1k_output = pricing["output"]
        except Exception:
            # Discovery is best-effort — never crash on network issues
            pass


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
    "SelectorConfig",
    "ServerConfig",
    "DEFAULT_COST_RATES",
    "find_config_path",
    "load_config",
]
