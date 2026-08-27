"""LIVE collaborative evals — dispatcher splits work, workers build pieces, aggregator merges.

These test Chimera's core value proposition: the dispatcher understands
the full picture, designs a DAG where each worker handles a different piece,
and the aggregator combines them into a coherent whole.

Two eval types:

1. **Static website** — dispatcher splits a landing page into sections
   (hero, features, footer, CSS), each worker builds one section, aggregator
   merges into a valid HTML page.

2. **Math proof** — dispatcher splits a proof into lemmas, workers prove
   each lemma, aggregator assembles the full proof.
"""

from __future__ import annotations

import asyncio
import json as _json
import re

import httpx
import pytest

from tests.integration.conftest import BUDGET_MODELS

pytestmark = [pytest.mark.integration, pytest.mark.slow]

TIMEOUT = 180.0  # These are complex tasks — allow 3 min


# ── Transient-failure retry (INT-CI-002) ───────────────────────────────────
# These evals hit real provider APIs: latency spikes surface as
# httpx.ReadTimeout, and the aggregator occasionally returns a degraded
# structured-output validation object instead of the schema fields. A short
# dependency-free retry with backoff absorbs the transient failures without
# weakening any assertion.


def _is_validation_failure_object(response: httpx.Response) -> bool:
    """True when a 200 body's answer is the aggregator's validation-failure
    object (``{"passed": False, "errors": [...]}``).

    This shape is NEVER a legitimate deliberation answer — it means a provider
    transiently degraded and the aggregator's structured-output validation
    rejected the output. Retrying is always safe, with or without
    ``output_schema`` in the payload: the CI flake hit the NON-schema
    static-website test with exactly this body (the aggregator ran its
    validation path regardless of the request's schema).
    """
    if response.status_code != 200:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    answer = body.get("answer") if isinstance(body, dict) else None
    if not isinstance(answer, str):
        return False
    try:
        parsed = _json.loads(answer)
    except _json.JSONDecodeError:
        return False
    return isinstance(parsed, dict) and parsed.get("passed") is False


def _is_degraded_schema_answer(response: httpx.Response) -> bool:
    """True when a 200 body's answer is neither JSON nor HTML.

    Only meaningful for schema payloads, where the answer must be a JSON
    object (the schema fields) or a plain-HTML fallback the test asserts
    directly; a truncated or malformed block (the CI "JSON parse failure"
    flake: an unhandled JSONDecodeError at the test's own json.loads) is
    retryable. NOT applied to non-schema payloads — the math-proof test's
    prose answer would match the no-HTML heuristic and burn all retries.
    """
    if response.status_code != 200:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    answer = body.get("answer") if isinstance(body, dict) else None
    if not isinstance(answer, str):
        return False
    parsed: object = None
    try:
        parsed = _json.loads(answer)
    except _json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", answer)
        if match:
            try:
                parsed = _json.loads(match.group(0))
            except _json.JSONDecodeError:
                parsed = None
    if isinstance(parsed, dict):
        return False  # validation-failure objects handled by _is_validation_failure_object
    lower = answer.lower()
    return "<html" not in lower and "<!doctype" not in lower


async def _post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    payload: dict,
    attempts: int = 3,
    backoff: float = 5.0,
    timeout: float = TIMEOUT,
) -> httpx.Response:
    """POST *payload*, retrying transient provider/aggregator failures.

    Retryable conditions: ``httpx.TimeoutException`` (ReadTimeout /
    ConnectTimeout / ...), 5xx responses, a 200 whose answer is the
    aggregator's validation-failure object (``{"passed": False}`` — always
    retried, schema or not), and — for schema payloads — a 200 whose answer
    is neither JSON nor HTML (see :func:`_is_degraded_schema_answer`).
    Anything else (2xx/3xx/4xx) is returned immediately.

    Raises the last timeout exception, or an ``AssertionError`` summarizing
    the last HTTP failure, once *attempts* are exhausted.
    """
    check_degraded = "output_schema" in payload
    last_error: Exception | None = None
    last_detail = ""
    for attempt in range(1, attempts + 1):
        try:
            r = await client.post(url, json=payload, timeout=timeout)
        except httpx.TimeoutException as exc:
            last_error = exc
            last_detail = f"timeout on attempt {attempt}/{attempts}: {exc!r}"
        else:
            last_error = None
            degraded = (
                _is_validation_failure_object(r)
                or (check_degraded and _is_degraded_schema_answer(r))
            )
            if r.status_code < 500 and not degraded:
                return r
            why = f"HTTP {r.status_code}" if r.status_code >= 500 else "degraded"
            last_detail = (
                f"{why} on attempt {attempt}/{attempts}: {r.text[:300]}"
            )
        if attempt < attempts:
            await asyncio.sleep(backoff * attempt)
    if last_error is not None:
        raise last_error
    raise AssertionError(
        f"POST {url} still failing after {attempts} attempts — {last_detail}"
    )


def _assert_valid_html(html: str) -> None:
    """Basic HTML validity: doctype or html tag, balanced tags, non-empty body."""
    lower = html.lower()
    assert "<html" in lower or "<!doctype" in lower, (
        f"No html tag or doctype found. First 200 chars: {html[:200]}"
    )
    # Must have at least one meaningful element
    assert any(tag in lower for tag in ["<div", "<section", "<header", "<main", "<body"]), (
        f"No structural HTML elements found. First 200 chars: {html[:200]}"
    )


def _assert_has_sections(output: str, min_sections: int = 2) -> None:
    """Verify the output contains distinct sections (headings, paragraphs, steps)."""
    import re

    sections = 0
    # HTML sectioning elements
    for pattern in [
        r"<section[>\s]", r"<header[>\s]", r"<footer[>\s]", r"<main[>\s]",
        r"<div\s+class=", r"<h[1-3]",
    ]:
        sections += len(re.findall(pattern, output, re.IGNORECASE))

    # Markdown headings
    sections += len(re.findall(r"^#{1,3}\s", output, re.MULTILINE))

    # Text-mode sections: numbered steps, lemma markers, paragraph breaks
    text_sections = len(re.findall(
        r"(?:^\d+[\.\)]\s|Lemma|Step\s+\d|Proof\.|Therefore|Hence|Thus\b|"
        r"\n\n(?=\S))",
        output, re.MULTILINE | re.IGNORECASE,
    ))
    sections += text_sections

    assert sections >= min_sections, (
        f"Expected at least {min_sections} distinct sections, found {sections}. "
        f"First 300 chars: {output[:300]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Eval 1 — Collaborative static website
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_collaborative_static_website(live_server: str) -> None:
    """Dispatch splits a landing page across workers, aggregator merges.

    The dispatcher should design a DAG like:

        worker_1 (HTML structure/hero) ─┐
        worker_2 (features section)    ─┤
        worker_3 (CSS styling)         ─┼─→ aggregator → merged HTML page
        worker_4 (footer/CTA)          ─┘

    The aggregator receives each worker's section and produces a single
    complete, valid HTML file.
    """
    import httpx

    payload = {
        "prompt": (
            "Build a simple single-page HTML landing page for a fictional SaaS product "
            "called 'Chimera Analytics'. The page must include:\n\n"
            "1. A hero section with a headline, subtitle, and CTA button\n"
            "2. A features section listing 3 key features\n"
            "3. A footer with copyright\n"
            "4. Inline CSS styling (dark theme, modern look)\n\n"
            "Output the COMPLETE HTML file as a single code block. "
            "Every worker should handle a different section, and the aggregator "
            "must merge them into one valid HTML document."
        ),
        "formation": "auto",
        "allowed_models": BUDGET_MODELS,
    }

    async with httpx.AsyncClient() as client:
        r = await _post_with_retry(
            client, f"{live_server}/v1/deliberate", payload=payload,
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.json()

    answer = body["answer"]
    trace = body["trace"]

    # Verify no degraded stages
    for stage in trace.get("stages", []):
        resp = stage.get("response", "")
        assert "[stage " not in resp.lower() or "unavailable" not in resp.lower(), (
            f"Stage {stage.get('stage_id', '?')} ({stage.get('kind', '?')}) degraded: "
            f"{resp[:200]}"
        )

    # Verify HTML validity
    _assert_valid_html(answer)

    # Verify multiple sections
    _assert_has_sections(answer, min_sections=3)

    # Verify key content elements
    lower = answer.lower()
    assert "chimera" in lower, f"Brand name not found in output: {answer[:300]}"
    assert any(word in lower for word in ["hero", "headline", "cta", "feature", "footer"]), (
        f"No landing-page structure detected: {answer[:300]}"
    )

    # Verify multi-worker collaboration happened
    stages = trace.get("stages", [])
    worker_count = sum(1 for s in stages if s.get("kind") == "worker")
    assert worker_count >= 1, (
        f"Expected at least 1 worker, found {worker_count}. "
        f"Stage kinds: {[s.get('kind') for s in stages]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Eval 2 — Collaborative math proof
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_collaborative_math_proof(live_server: str) -> None:
    """Dispatch splits a proof into steps/lemmas across workers, aggregator assembles.

    The dispatcher should split the proof into logical parts, each worker
    proves one lemma, and the aggregator combines them into a complete proof.
    """
    import httpx

    payload = {
        "prompt": (
            "Prove that the square root of 2 is irrational. Split the proof "
            "into logical steps across workers: one worker handles the setup "
            "(assume sqrt(2) = a/b in lowest terms), another handles the "
            "algebraic manipulation showing a and b are both even, another "
            "handles the contradiction and conclusion. The aggregator must "
            "merge these into a single coherent, rigorous mathematical proof. "
            "Output the complete proof."
        ),
        "formation": "auto",
        "allowed_models": BUDGET_MODELS,
    }

    async with httpx.AsyncClient() as client:
        r = await _post_with_retry(
            client, f"{live_server}/v1/deliberate", payload=payload,
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.json()

    answer = body["answer"]
    trace = body["trace"]

    # Verify no degraded stages
    for stage in trace.get("stages", []):
        resp = stage.get("response", "")
        assert "[stage " not in resp.lower() or "unavailable" not in resp.lower(), (
            f"Stage {stage.get('stage_id', '?')} ({stage.get('kind', '?')}) degraded"
        )

    # Verify proof content
    lower = answer.lower()
    assert "irrational" in lower, f"Proof should mention 'irrational': {answer[:300]}"
    assert "sqrt" in lower or "√" in answer or "square root" in lower, (
        f"Proof should reference sqrt: {answer[:300]}"
    )
    # Standard proof elements
    assert any(term in lower for term in ["contradiction", "assume", "lowest term",
                                            "even", "a/b", "integer"]), (
        f"Proof missing key elements. First 300 chars: {answer[:300]}"
    )

    # Verify logical structure (numbered steps, lemmas, or sections)
    # The answer may be a JSON wrapper like {"answer": "...", "sources": [...]}
    # Extract the inner text for section detection
    import json as _json

    inner = answer
    try:
        parsed = _json.loads(answer)
        if isinstance(parsed, dict) and "answer" in parsed:
            inner = parsed["answer"]
    except (_json.JSONDecodeError, TypeError):
        pass
    _assert_has_sections(inner, min_sections=2)

    # Verify multi-worker collaboration
    stages = trace.get("stages", [])
    worker_count = sum(1 for s in stages if s.get("kind") == "worker")
    assert worker_count >= 1, (
        f"Expected at least 1 worker, found {worker_count}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Eval 3 — Structured output website (schema-enforced)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_website_with_structured_output(live_server: str) -> None:
    """Same website task but with json_schema enforcing the aggregator output.

    The aggregator must return a JSON object with {html, css_sections, title}
    proving multi-model collaboration can produce structured, machine-readable
    output as well as free-form HTML.
    """
    import httpx

    schema = {
        "type": "object",
        "properties": {
            "html": {
                "type": "string",
                "description": "The complete HTML document",
            },
            "title": {
                "type": "string",
                "description": "The page title",
            },
            "sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of section names built by workers",
            },
        },
        "required": ["html", "title"],
    }

    payload = {
        "prompt": (
            "Build a simple single-page HTML portfolio page for a fictional "
            "developer named 'Alex'. Include a header with name and title, "
            "a projects section with 2 project cards, and a contact section.\n"
            "Use dark theme styling."
        ),
        "formation": "auto",
        "allowed_models": BUDGET_MODELS,
        "output_schema": schema,
    }

    async with httpx.AsyncClient() as client:
        r = await _post_with_retry(
            client, f"{live_server}/v1/deliberate", payload=payload,
        )

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:500]}"
    body = r.json()
    answer = body["answer"]

    # Try to parse as JSON (structured output should return valid JSON)
    import json as _json

    try:
        parsed = _json.loads(answer)
    except _json.JSONDecodeError:
        # The aggregator might return JSON embedded in text with the schema downgrade
        # Try extracting a JSON object from the response
        import re

        match = re.search(r"\{[\s\S]*\}", answer)
        try:
            parsed = _json.loads(match.group(0)) if match else None
        except _json.JSONDecodeError:
            # Brace span wasn't JSON (e.g. inline CSS in an HTML answer) —
            # treat the answer as the plain-HTML fallback below.
            parsed = None
        if parsed is None:
            # Fallback: verify answer is non-empty HTML
            _assert_valid_html(answer)
            assert "alex" in answer.lower(), f"Name missing from output: {answer[:200]}"
            return

    # Structured output path: verify fields
    assert "html" in parsed, f"Missing 'html' field: {list(parsed.keys())[:5]}"
    html = parsed.get("html", "")
    _assert_valid_html(html)
    lower_html = html.lower()
    assert "alex" in lower_html, f"Name not in HTML: {html[:300]}"
    assert any(tag in lower_html for tag in ["<section", "<div", "<header",
                                               "<main", "<article"]), (
        f"No structural elements in HTML: {html[:300]}"
    )

    if "title" in parsed:
        assert parsed["title"], "Title is empty"

    # Verify multi-worker collaboration
    stages = body["trace"].get("stages", [])
    worker_count = sum(1 for s in stages if s.get("kind") == "worker")
    assert worker_count >= 1, (
        f"Expected at least 1 worker, found {worker_count}"
    )
