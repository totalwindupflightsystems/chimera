"""Chimera configuration loading and validation.

Reads ``chimera.yaml`` into Pydantic v2 models. Environment variables referenced
as ``${VAR}`` in the YAML are substituted from ``os.environ`` at load time.
"""

from __future__ import annotations

import hashlib
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

    @classmethod
    def empty(cls) -> Defaults:
        """A placeholder defaults block for config-less operation (CH-GAP-041)."""
        return cls(
            dispatcher="",
            default_worker="",
            default_aggregator="",
        )


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
    # 8765 is the port every doc (README, INTEGRATION, SECURITY, OPENAI_API,
    # skills/chimera-usage) uses in its curl examples. A bare `chimera serve`
    # with no chimera.yaml must bind there, not silently squat 8000 (CH-GAP-038).
    port: int = 8765
    health_timeout_s: float = 10.0
    """Wall-clock budget for the provider connectivity probe in
    ``_check_providers`` (``/v1/health`` + ``/v1/health/ready``).

    Providers that have not responded within this window are reported as
    ``timeout``.  Default 10.0 s — slow-but-working providers (deepseek,
    openrouter, ...) were previously misreported as unhealthy under the
    hardcoded 3.0 s budget.
    """


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
    progressive: bool = False                     # Enable progressive prompting on worker stages
    wait_messages: list[str] | None = None       # Context msgs fed one-at-a-time before the main prompt
    trigger: str | None = None                   # Final msg requesting actual output (replaces task prompt)
    max_tokens: int | None = None                # Cap output tokens per model call (OpenAI-compat max_tokens)


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


class AutoFormationConfig(BaseModel):
    """Behavior of the default ``auto`` formation (dispatcher-designed DAGs).

    ``restrict_to_credentialed_providers`` (default ``True``) limits the
    dispatcher's model catalog — and the auto worker stages that result —
    to enabled models whose provider has resolved credentials
    (:func:`provider_credential_resolved`).  This prevents a fresh install
    with e.g. only ``DEEPSEEK_API_KEY`` from burning calls on
    guardrail-blocked OpenRouter models (``model_blocked_guardrail`` →
    ``aggregator_partial_inputs``).

    Set to ``False`` to explicitly opt in to the full enabled catalog
    (the pre-restriction behavior).  Named presets and custom DAGs are
    never affected by this switch, and request-level overrides
    (``allowed_models`` / ``worker_model`` / ``stage_models`` /
    ``dispatcher_model`` / ``aggregator_model``) remain authoritative.
    """

    restrict_to_credentialed_providers: bool = True


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
    auto_formation: AutoFormationConfig = Field(default_factory=AutoFormationConfig)
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
                # Resolution order: process env → repo .env (loaded into the
                # process env by ``load_config``) → ~/.hermes/.env fallback.
                provider.api_key = os.environ.get(provider.api_key_env)
                if provider.api_key is None:
                    provider.api_key = _load_hermes_dotenv().get(provider.api_key_env)
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

    def catalog_description(self, *, exclude: set[str] | None = None) -> str:
        """Human-readable model catalog for the dispatcher prompt.

        Disabled models are excluded so the dispatcher never sees them, as
        are any models named in *exclude* (e.g. models currently blocked by
        the guardrail failure registry).
        """
        excluded = exclude or set()
        lines: list[str] = []
        for name, entry in self.enabled_models.items():
            if name in excluded:
                continue
            cats = ", ".join(
                f"{cat}={score:.2f}"
                for cat, score in sorted(entry.categories.items(), key=lambda kv: -kv[1])
            )
            lines.append(
                f"- {name} [provider={entry.provider}, cost_tier={entry.cost_tier}] "
                f"strengths: {cats}"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Credential-derived model usability (DF-CHIMERA-0906-3)
# --------------------------------------------------------------------------- #

def _resolved_credential(
    config: ChimeraConfig, provider_name: str
) -> str | None:
    """The credential string the gateway would use for *provider_name*.

    Mirrors the resolution order documented on
    :func:`provider_credential_resolved` (config shortcut → provider entry →
    F8 Anthropic→OpenRouter fallback) and returns ``None`` when nothing
    resolves.  Never logged, never persisted — the value is only ever turned
    into a fingerprint by :func:`provider_credential_fingerprint`.
    """
    key = config.api_keys.get(provider_name)
    if key:
        return key
    provider = config.providers.get(provider_name)
    if provider is not None and provider.api_key:
        return provider.api_key
    if provider_name == "anthropic":
        # F8: the gateway routes Anthropic models via OpenRouter when no
        # Anthropic key is configured but an OpenRouter key exists.
        or_key = config.api_keys.get("openrouter")
        if or_key:
            return or_key
        or_provider = config.providers.get("openrouter")
        if or_provider is not None and or_provider.api_key:
            return or_provider.api_key
    return None


#: Length of the truncated sha256 hex digest used as a credential
#: fingerprint.  16 hex chars (64 bits) is far more than enough to detect a
#: rotated key while keeping the persisted state file small.
_FINGERPRINT_LEN = 16


def credential_fingerprint(secret: str | None) -> str | None:
    """A non-reversible digest of *secret* (``None`` in → ``None`` out).

    Used to detect "the operator replaced the key" without ever storing,
    logging or comparing the credential itself: the digest is truncated
    sha256 hex and cannot be reversed into the key.
    """
    if not secret:
        return None
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:_FINGERPRINT_LEN]


def provider_credential_fingerprint(
    config: ChimeraConfig, provider_name: str
) -> str | None:
    """Non-reversible fingerprint of *provider_name*'s resolved credential.

    Same resolution order as :func:`provider_credential_resolved`; returns
    ``None`` when no credential resolves.  Recorded alongside a
    credential-class model block so the block self-clears once the provider's
    key changes (DF-CHIMERA-V2-6).
    """
    return credential_fingerprint(_resolved_credential(config, provider_name))


def model_credential_fingerprint(
    config: ChimeraConfig, model_name: str
) -> str | None:
    """Fingerprint of the credential behind *model_name*'s provider.

    ``None`` when the model is not in the catalog (so no provider can be
    resolved) or the provider has no resolved credential.
    """
    entry = config.models.get(model_name)
    if entry is None or not entry.provider:
        return None
    return provider_credential_fingerprint(config, entry.provider)


def provider_credential_resolved(config: ChimeraConfig, provider_name: str) -> bool:
    """True when the config can resolve an API key for *provider_name*.

    This is the canonical, deterministic credential view used for routing
    decisions (default ``auto`` formation filtering).  It mirrors the
    resolution order the gateway uses for its primary key source:

    1. ``config.api_keys[provider_name]`` — env shortcuts / ``${VAR}``
       substitution (``_apply_env_overrides`` mirrors the standard
       ``*_API_KEY`` env vars here at load time).
    2. ``providers[provider_name].api_key`` — resolved from ``api_key_env``
       by the model validator.
    3. F8 Anthropic → OpenRouter fallback: Anthropic models route through
       OpenRouter when only an OpenRouter key is configured.

    Raw ``os.environ`` fallbacks (LiteLLM's own env handling) are
    deliberately NOT consulted here so the answer depends only on the
    loaded config object.  The REST health surface
    (``api.server._provider_has_credentials``) layers those env probes on
    top of this helper for connectivity reporting.

    Presence is all this answers — a *present but invalid* key resolves here
    and is caught on first use by the credential-class model block
    (DF-CHIMERA-V2-6).
    """
    return _resolved_credential(config, provider_name) is not None


def credentialed_enabled_models(config: ChimeraConfig) -> dict[str, ModelEntry]:
    """Enabled catalog models whose provider has resolved credentials.

    These are the models the default ``auto`` formation may assign to
    worker stages when
    ``auto_formation.restrict_to_credentialed_providers`` is on.
    """
    return {
        name: entry
        for name, entry in config.enabled_models.items()
        if provider_credential_resolved(config, entry.provider)
    }


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


def _load_repo_dotenv(config_path: Path) -> None:
    """Load the repo-level ``.env`` next to *config_path* into ``os.environ``.

    Only variables that are NOT already present in the process environment
    are populated, so the real environment keeps precedence
    (``process env > repo .env > ~/.hermes/.env``). Best-effort: a missing
    file or a missing ``python-dotenv`` install is silently ignored, and a
    malformed file logs a warning instead of crashing startup.
    """
    env_path = config_path.resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a transitive dep
        return
    try:
        load_dotenv(env_path, override=False)
    except Exception as exc:  # pragma: no cover - malformed .env
        import logging

        logging.getLogger("chimera.config").warning(
            "failed to load repo .env at %s: %s", env_path, exc
        )


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


def find_example_config_path(start: Path | str | None = None) -> Path:
    """Locate the shipped ``chimera.yaml.example`` bootstrap template.

    Resolution order:
    1. Walk up from ``start`` (default cwd) — covers repo checkouts and
       any directory where the user already keeps a copy.
    2. The wheel-shipped copy inside the installed package
       (CH-GAP-049 force-include: ``chimera/chimera.yaml.example``), so
       ``chimera config init`` works for bare pip installs in an empty dir.
    3. Walk up from this module's own location — covers editable installs,
       where ``__file__`` lives at ``<repo>/src/chimera/config.py`` and the
       checked-in template sits at ``<repo>/chimera.yaml.example``
       (DF-CHIMERA-V2-3).

    Raises ``FileNotFoundError`` when the template cannot be found.
    """
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "chimera.yaml.example"
        if target.is_file():
            return target
    pkg_copy = Path(__file__).resolve().parent / "chimera.yaml.example"
    if pkg_copy.is_file():
        return pkg_copy
    pkg_here = Path(__file__).resolve().parent
    for candidate in [*pkg_here.parents]:
        target = candidate / "chimera.yaml.example"
        if target.is_file():
            return target
    raise FileNotFoundError(
        "chimera.yaml.example not found — copy the template from a chimera-v2 "
        "repo checkout (chimera.yaml.example at the repo root) or reinstall "
        "chimera-deliberation to restore the packaged template."
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
    * ``CHIMERA_AUTO_ALLOW_ALL_CATALOG`` → disables the default auto
      formation's credential-derived catalog restriction
      (``auto_formation.restrict_to_credentialed_providers = False``)
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
    # Load the repo-level ``.env`` (next to ``chimera.yaml``) into the
    # process environment so provider ``api_key_env`` lookups and downstream
    # SDKs see the same credentials regardless of entry point. Only *unset*
    # vars are populated — the real process environment keeps precedence.
    _load_repo_dotenv(config_path)
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
    if _os.environ.get("CHIMERA_AUTO_ALLOW_ALL_CATALOG", "").lower() in ("true", "1"):
        # Explicit opt-in to the full enabled catalog for default auto
        # formation (disables the credential-derived restriction).
        config.auto_formation.restrict_to_credentialed_providers = False

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
    "AutoFormationConfig",
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
    "credential_fingerprint",
    "credentialed_enabled_models",
    "find_config_path",
    "find_example_config_path",
    "load_config",
    "model_credential_fingerprint",
    "provider_credential_fingerprint",
    "provider_credential_resolved",
]
