# Chimera — Multi-Model Deliberation Gateway
#
# Usage:
#   docker build -t chimera .
#   cp chimera.yaml.example chimera.yaml
#   # Add your API keys to chimera.yaml
#   docker run -p 8765:8765 -v ./chimera.yaml:/etc/chimera/chimera.yaml chimera
#
# Or with env vars:
#   docker run -p 8765:8765 \
#     -e DEEPSEEK_KEY=sk-... \
#     -e OPENROUTER_KEY=sk-or-v1-... \
#     -v ./chimera.yaml:/etc/chimera/chimera.yaml \
#     chimera

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
