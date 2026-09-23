"""DF-CHIMERA-V2-43 — one completed turn renders its answer bubble exactly ONCE.

The defect, measured on the deployed :8765: a live turn painted the same answer
bubble TWICE with divergent stage counts.  Two live paths call
``addMessageBubble`` for one turn:

* the ``deliberation_done`` SSE listener — bubble #1, whose stats are built from
  a synthetic ``new Array(data.stage_count || 1).fill({})`` stages array, and
* the ``POST /web/sessions/{id}/chat`` response handler — bubble #2, carrying
  the real ``data.trace``.

The server broadcasts ``deliberation_done`` and closes the session's streams,
then the POST resolves, so in live mode BOTH run for the same turn and the user
sees one answer twice (first copy reporting the synthetic count, second the
trace's).  The live payload does not even carry ``stage_count`` — only
``dag_designed`` does (``web/routes.py``) — which is exactly how the two copies
came to disagree.

The fix is a per-turn render guard on the SPA side: the first renderer marks the
turn, the second sees the mark and skips its ``addMessageBubble`` (first renderer
wins, in either arrival order), and ``sendMessage()`` resets the guard so the
next turn renders its own bubble.  Both handlers keep their stats-tile updates —
those are idempotent value-sets — and the loser keeps its ``loadHistory()``
sidebar refresh.

Structural, like its siblings (``test_spa_stage_listeners.py``,
``test_web_sse_live.py``, ``test_web_sse_replay.py``): the shipped
``static/index.html`` is read as text and asserted on, so deleting the guard —
or leaving a bubble call outside it — fails here instead of shipping a
duplicate-render window.  Hermetic: no server, no network, no provider keys.
"""

from __future__ import annotations

import pathlib
import re

import pytest

HTML_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "src" / "chimera" / "web" / "static" / "index.html"
)

#: The marker the two renderers share.  Named once here; the tests below prove
#: the SPA itself declares exactly this one variable and compares it the same
#: way at both call sites.
MARKER = "lastRenderedTurn"

#: The guard, verbatim: the marker compared against the turn the payload carries
#: (both handlers read the server's ``turn_number``).  ``!==`` and not ``===`` is
#: load-bearing — with the marker unset (``null``) it must let the FIRST renderer
#: through, and a page-load replay renders with the marker still unset.
GUARD = f"if ({MARKER} !== data.turn_number) {{"

#: The bubble calls as they ship, per path — kept verbatim so a "fix" that drops
#: the real trace (or the mermaid) from either renderer cannot pass.
SSE_BUBBLE = "addMessageBubble(data.answer, data.turn_number, currentMermaid, {"
POST_BUBBLE = "addMessageBubble(data.answer, data.turn_number, data.mermaid, data.trace)"


@pytest.fixture(scope="module")
def spa_source() -> str:
    assert HTML_PATH.is_file(), f"shipped SPA missing: {HTML_PATH}"
    return HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def spa_code(spa_source: str) -> str:
    """The SPA with full-line ``//`` comments removed.

    The guards are asserted by counting occurrences of the marker; comments
    legitimately *describe* the marker, so they must not count as uses.  Only
    full-line comments are stripped: a naive ``//`` strip would cut any string
    containing a URL.
    """
    return re.sub(r"(?m)^[ \t]*//.*$", "", spa_source)


def _js_function(source: str, declaration: str) -> str:
    """The text of a shipped JS function, from its declaration to its last brace.

    Brace-matched rather than section-sliced, so the assertion window is exactly
    the function's own body — a statement that merely sits NEAR it in the file
    cannot satisfy a check, and a sibling's function cannot break one.
    """
    start = source.index(declaration)
    brace = source.index("{", start + len(declaration))
    depth = 0
    for i in range(brace, len(source)):
        char = source[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"unbalanced braces after {declaration!r}")


def _braced_block(source: str, brace_at: int) -> tuple[int, int]:
    """``(start, end)`` inclusive of the brace-matched block opened at ``brace_at``."""
    assert source[brace_at] == "{", f"not a block opener at {brace_at}: {source[brace_at]!r}"
    depth = 0
    for i in range(brace_at, len(source)):
        char = source[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return brace_at, i
    raise AssertionError("unbalanced braces in the SPA source")


def _guard_blocks(code: str) -> list[tuple[int, int]]:
    """Every ``if (marker !== data.turn_number) { … }`` block, brace-matched."""
    return [_braced_block(code, match.end() - 1) for match in re.finditer(re.escape(GUARD), code)]


def _bubble_call_offsets(code: str) -> list[int]:
    """Offsets of ``addMessageBubble(<args>)`` CALLS — the definition excluded."""
    offsets = [m.start() for m in re.finditer(r"addMessageBubble\(", code)]
    return [off for off in offsets if not code[:off].rstrip().endswith("function")]


def _sse_handler(spa_source: str) -> str:
    return _js_function(spa_source, "eventSource.addEventListener('deliberation_done'")


# ---------------------------------------------------------------------------
# A1 — both call sites participate in ONE per-turn guard (first renderer wins)
# ---------------------------------------------------------------------------


def test_guard_is_checked_and_set_in_the_post_handler_before_rendering(spa_code: str) -> None:
    """The POST response handler must not paint a bubble the SSE path already painted.

    This is the second half of the duplicate: after the live
    ``deliberation_done`` renders bubble #1, the resolving POST rendered bubble
    #2 — the real ``data.trace`` copy — right underneath it.
    """
    body = _js_function(spa_code, "async function sendMessage()")

    assert GUARD in body, (
        "the POST /chat handler renders its bubble behind no guard — it will "
        "paint a second copy of a turn the SSE path already rendered"
    )
    guard_start, guard_end = _braced_block(body, body.index(GUARD) + len(GUARD) - 1)
    guarded = body[guard_start : guard_end + 1]
    assert POST_BUBBLE in guarded, (
        "the POST handler's addMessageBubble(…, data.trace) is outside the "
        "per-turn guard — that is the duplicate-render window"
    )
    assert f"{MARKER} = data.turn_number;" in guarded, (
        "the POST handler must MARK the turn it rendered, or the SSE path that "
        "arrives late has nothing to consult"
    )
    # The mark is set before the render, never after: a throw inside the render
    # must not leave the turn looking unrendered to the other path.
    assert guarded.index(f"{MARKER} = data.turn_number;") < guarded.index(POST_BUBBLE)
    # The real trace (and the mermaid it renders) survive the move.
    assert "data.mermaid" in body and "data.trace" in body


def test_guard_is_set_in_the_deliberation_done_handler_before_rendering(spa_source: str) -> None:
    """The SSE half of the pair: bubble #1 marks the turn as it renders it.

    Without the mark here the POST path cannot know a bubble exists, and the
    duplicate returns.
    """
    body = _sse_handler(spa_source)

    assert GUARD in body, (
        "the deliberation_done listener renders its bubble behind no guard — it "
        "cannot tell the POST path (or a replayed stream) that the turn is drawn"
    )
    guard_start, guard_end = _braced_block(body, body.index(GUARD) + len(GUARD) - 1)
    guarded = body[guard_start : guard_end + 1]
    assert SSE_BUBBLE in guarded, (
        "the SSE bubble call must sit inside the guard — outside it, it overwrites "
        "or duplicates whatever the POST path rendered"
    )
    assert f"{MARKER} = data.turn_number;" in guarded
    assert guarded.index(f"{MARKER} = data.turn_number;") < guarded.index(SSE_BUBBLE)
    # The synthetic stats payload is untouched (kept, not replaced).
    assert "new Array(data.stage_count || 1).fill({})" in guarded


def test_the_two_call_sites_share_one_marker_and_the_same_comparison(spa_code: str) -> None:
    """One marker variable, one comparison — a per-tag flag pair would not compose.

    Two markers (or a ``===`` on one side and a ``!==`` on the other) leave a
    window where both paths decide they are the renderer.
    """
    assert spa_code.count(MARKER) == 6, (
        "the marker must appear exactly at its 6 documented uses — declaration, "
        f"one compare+set per call site, one reset per send; found {spa_code.count(MARKER)}"
    )
    assert spa_code.count(f"let {MARKER} = null;") == 1, "the marker must be declared exactly once"
    assert spa_code.count(GUARD) == 2, (
        "both renderers must compare the marker the same way (one guard per site)"
    )
    assert spa_code.count(f"{MARKER} = null;") == 2, (
        "exactly one reset besides the initialiser (in sendMessage)"
    )
    assert spa_code.count(f"{MARKER} = data.turn_number;") == 2, (
        "each renderer marks the turn it rendered, exactly once"
    )
    assert spa_code.count(f"{MARKER} === data.turn_number") == 0, (
        "an equality guard would block the FIRST renderer (the marker starts null)"
    )


# ---------------------------------------------------------------------------
# A2 — reset on send, so consecutive turns each render their own bubble
# ---------------------------------------------------------------------------


def test_send_message_resets_the_guard_before_the_next_turn_is_sent(spa_code: str) -> None:
    """A latched guard would silently swallow every turn after the first."""
    body = _js_function(spa_code, "async function sendMessage()")

    assert f"{MARKER} = null;" in body, (
        "sendMessage() must clear the per-turn guard, or the turn after the "
        "guarded one renders no bubble at all"
    )
    send_call = "await apiFetch(" if "await apiFetch(" in body else "await fetch("
    assert send_call in body
    assert body.index(f"{MARKER} = null;") < body.index(send_call), (
        "the guard must be cleared when the turn STARTS, not after its response"
    )
    # It rides with the other per-turn reset, so the two cannot drift apart.
    assert body.index("deliberationComplete = false") < body.index(f"{MARKER} = null;")


# ---------------------------------------------------------------------------
# A3 — replay and non-SSE flows keep rendering exactly one bubble, untouched
# ---------------------------------------------------------------------------


def test_guard_starts_unset_so_replay_and_post_only_flows_still_render(spa_code: str) -> None:
    """Nothing renders on a page load or a POST-only turn if the guard starts set.

    A page-load replay is the one flow that reaches ``deliberation_done`` with no
    POST behind it, and a POST-only turn is one whose stream delivered no
    ``deliberation_done`` — both must render their bubble, so the marker starts
    ``null`` and the compare is an inequality.
    """
    assert f"let {MARKER} = null;" in spa_code, (
        "the marker must start unset: a page-load replay (no POST) and a "
        "POST-only turn both have to render their bubble"
    )
    assert GUARD in spa_code


def test_deliberation_done_terminal_bookkeeping_stays_outside_the_guard(spa_source: str) -> None:
    """The guard wraps the BUBBLE only — closing the stream and the sidebar stay.

    The replay/reconnect contract (DF-CHIMERA-V2-19 / -29) lives in the same
    handler: ``endStream``-style teardown, ``loadHistory()``, the status line and
    the re-enabled send button must keep running on a replay, where the bubble is
    the only thing the guard may decide.
    """
    body = _sse_handler(spa_source)
    guard_start, guard_end = _braced_block(body, body.index(GUARD) + len(GUARD) - 1)

    for statement in ("loadHistory();", "'dag-live-indicator'", "sseLiveMode", "eventSource.close()"):
        at = body.index(statement)
        assert not (guard_start <= at <= guard_end), (
            f"{statement!r} was moved inside the render guard — the terminal "
            "bookkeeping of a replay must stay unconditional"
        )
    # The terminal marker listener of the replay path is untouched (DF-19).
    replay = _js_function(spa_source, "eventSource.addEventListener('replay_done'")
    assert "endStream(" in replay


# ---------------------------------------------------------------------------
# A4 — no duplicate-render window survives: every bubble call is guarded
# ---------------------------------------------------------------------------


def test_exactly_two_bubble_call_sites_and_both_are_behind_the_guard(spa_code: str) -> None:
    """Structural proof of "exactly one path renders a given turn".

    Both live call sites must be inside a guard block, and no third call site may
    exist unguarded — the definition is not a call site and is allowed to sit
    anywhere.
    """
    calls = _bubble_call_offsets(spa_code)
    assert len(calls) == 2, f"expected the two known bubble call sites (SSE + POST), found {len(calls)}"

    blocks = _guard_blocks(spa_code)
    assert len(blocks) == 2, f"expected one guard per call site, found {len(blocks)}"

    for call_at in calls:
        enclosing = [b for b in blocks if b[0] <= call_at <= b[1]]
        assert len(enclosing) == 1, (
            f"the addMessageBubble call at byte {call_at} is not inside exactly one "
            "per-turn guard — an unguarded call site can render a duplicate"
        )

    # And each guard holds exactly one of them (they cannot shadow each other).
    for block in blocks:
        inside = [c for c in calls if block[0] <= c <= block[1]]
        assert len(inside) == 1, f"guard {block} contains {len(inside)} bubble calls"


def test_stats_tile_updates_stay_unconditional_on_both_paths(spa_code: str) -> None:
    """The tile updates are idempotent value-sets — both paths keep them.

    Only the bubble is guarded: dropping the stats updates on the losing path
    would leave the tiles showing a stale total whenever the paths disagree.  The
    stage tally tile is driven by the ``stage_completed`` listener, which neither
    path's guard may touch.
    """
    post = _js_function(spa_code, "async function sendMessage()")
    sse = _sse_handler(spa_code)

    for body in (post, sse):
        assert "animateValue('stat-tokens'" in body
        assert "'stat-cost'" in body
        assert "'stat-time'" in body
    assert "'stat-stages'" in post, "the POST path's trace stage count must stay"

    completed = _js_function(spa_code, "eventSource.addEventListener('stage_completed'")
    assert "'stat-stages'" in completed, "the stage tally tile must stay driven by stage_completed"
