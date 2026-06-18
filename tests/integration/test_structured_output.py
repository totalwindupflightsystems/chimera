"""Structured output tests — json_schema response format on /v1/chat/completions.

Tests the OpenAI-compatible ``response_format`` parameter that instructs the
aggregator to produce JSON matching a provided schema.
"""

from __future__ import annotations

import json

import httpx
import pytest

from tests.integration.conftest import BUDGET_MODELS

pytestmark = [pytest.mark.integration, pytest.mark.slow]

TIMEOUT = 120.0


@pytest.mark.asyncio
async def test_json_schema_chat_completions(live_server: str) -> None:
    """``POST /v1/chat/completions`` with ``response_format: json_schema``.

    Sends a JSON Schema requesting ``{"name": str, "value": int}`` and verifies
    the response content parses as valid JSON matching the schema.

    Uses the ``simple`` formation with budget deepseek models and
    ``allowed_models`` to keep costs minimal.
    """
    json_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "value": {"type": "integer"},
        },
        "required": ["name", "value"],
        "additionalProperties": False,
    }

    payload = {
        "model": "simple",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Return a JSON object with a 'name' field set to 'chimera' "
                    "and a 'value' field set to 42."
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "test_object",
                "schema": json_schema,
                "strict": True,
            },
        },
        "allowed_models": BUDGET_MODELS,
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{live_server}/v1/chat/completions",
            json=payload,
            timeout=TIMEOUT,
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.json()

    # Verify OpenAI-compatible response schema
    assert body["object"] == "chat.completion"
    assert "id" in body
    assert "created" in body
    assert "model" in body

    choices = body["choices"]
    assert len(choices) >= 1
    content = choices[0]["message"]["content"]
    assert content, "Response content is empty"

    # The content should be valid JSON matching the schema
    parsed = json.loads(content)
    assert isinstance(parsed, dict), f"Expected JSON object, got {type(parsed)}: {parsed}"
    assert "name" in parsed, f"Missing 'name' in JSON: {parsed}"
    assert "value" in parsed, f"Missing 'value' in JSON: {parsed}"
    assert isinstance(parsed["name"], str), f"name should be str: {parsed['name']}"
    assert isinstance(parsed["value"], int), f"value should be int: {parsed['value']}"

    # Verify usage stats (nonzero after real API calls)
    usage = body["usage"]
    assert usage["total_tokens"] > 0, f"total_tokens should be nonzero: {usage}"


@pytest.mark.asyncio
async def test_chat_completions_plain(live_server: str) -> None:
    """``POST /v1/chat/completions`` without response_format (plain text).

    Smoke test for the OpenAI-compatible endpoint without structured output.
    """
    payload = {
        "model": "simple",
        "messages": [
            {"role": "user", "content": "Reply with exactly: hello world"},
        ],
        "allowed_models": BUDGET_MODELS,
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{live_server}/v1/chat/completions",
            json=payload,
            timeout=TIMEOUT,
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.json()
    assert body["object"] == "chat.completion"
    content = body["choices"][0]["message"]["content"]
    assert content.strip(), "Response content is empty"
    assert body["usage"]["total_tokens"] > 0
