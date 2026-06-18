# Chimera — Multi-Model Deliberation Gateway
#
# Quick start with docker compose (recommended):
#   cp chimera.yaml.example chimera.yaml
#   # Set your keys via env vars (no YAML editing needed):
#   export DEEPSEEK_KEY=sk-... OPENROUTER_KEY=sk-or-v1-... ZAI_KEY=sk-...
#   docker compose up -d
#
# Or without compose:
#   docker build -t chimera .
#   docker run -p 8765:8765 \
#     -e DEEPSEEK_KEY=sk-... \
#     -e OPENROUTER_KEY=sk-or-v1-... \
#     -e ZAI_KEY=sk-... \
#     -v ./chimera.yaml:/etc/chimera/chimera.yaml \
#     chimera
#
# Every common setting has a CHIMERA_* env var:
#   CHIMERA_HOST, CHIMERA_PORT, CHIMERA_DISPATCHER,
#   CHIMERA_WORKER, CHIMERA_AGGREGATOR, CHIMERA_LOG_LEVEL,
#   CHIMERA_AUTH_ENABLED, CHIMERA_RATE_LIMIT_ENABLED

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Chimera"
LABEL org.opencontainers.image.description="Dynamic multi-model deliberation gateway"
LABEL org.opencontainers.image.url="https://github.com/totalwindupflightsystems/chimera"
LABEL org.opencontainers.image.licenses="MIT"

# ── System deps ──────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Install Chimera ──────────────────────────────────────────────────────
# Use the full extra to get CLI, server, MCP, and web UI
RUN pip install --no-cache-dir chimera-deliberation[full]

# ── Runtime setup ────────────────────────────────────────────────────────
RUN mkdir -p /etc/chimera
WORKDIR /etc/chimera

# Default config path — user mounts or overrides via CHIMERA_CONFIG
ENV CHIMERA_CONFIG=/etc/chimera/chimera.yaml

# Expose the default API/web port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8765/v1/health/live || exit 1

# Default: run the API server + web UI
ENTRYPOINT ["chimera"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
