import asyncio

from chimera import Engine, LiteLLMGateway, load_config

config = load_config()
engine = Engine(config, LiteLLMGateway(config))
result = asyncio.run(engine.deliberate("Explain quantum computing."))
print(result.answer)  # merged output from multiple models
# --- probe arm (documented nowhere; attribute-path check for DF-CHIMERA-V2-115) ---
print("ATTR_PROBE total_cost:", result.trace.total_cost)
print("ATTR_PROBE request_id:", result.trace.request_id)
print("ATTR_PROBE worker_failures:", result.trace.worker_failures)
