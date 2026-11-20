import json, pathlib

B = pathlib.Path("/home/kara/chimera-v2/.coding-hermes/board/tasks.jsonl")

TITLE = ("[P2] A client that walks away is not noticed: the abandoned deliberation keeps the only concurrency slot "
         "and keeps buying upstream calls - the retry waits 6.1s for a slot the corpse holds (14.18s vs 8.54s control) "
         "and 2 upstream calls are paid for an answer nobody received")

REASONING = (
"Fixture-served instance (queue.max_concurrent: 1, max_queue_depth: 4, 4s-per-call stdlib stub logging every upstream "
"arrival with a monotonic clock). Control request: wall 8.54s, HTTP 200, X-Chimera-Queue-Position 1, two upstream "
"stages (t_in 3.54 / 7.56). Abandon arm: same request, client gave up after 2.02s (curl rc=28, body 000), send at "
"t=11.66. Stub clock: the abandoned request's first stage arrived t_in=11.66 and was served t_out=15.67 - i.e. 2.0s "
"AFTER the client was gone - and its second stage was then DISPATCHED at t_in=15.69 and served t_out=19.69, 6.0s "
"after abandonment. Retry issued immediately as a user would: wall 14.18s, queue position 2, and its first upstream "
"arrival is t_in=19.74 - 6.1s of its 14.18s spent waiting for the slot the abandoned run still held.\n"
"Upstream accounting for the arm: 6 arrivals, 6 served, for 2 delivered answers. The abandoned request bought 2 "
"calls and returned nothing, and one of those 2 was issued after nobody was listening.\n"
"Mechanism: the deliberation path awaits the engine, not the request stream, so nothing in "
"src/chimera/api/server.py calls request.is_disconnected() before or during a non-streaming run (grep for "
"499/client_disconnect/task.cancel finds no disconnect handling outside the queue's own wait path; a Ctrl-C'd CLI "
"that is still QUEUED is cancelled cleanly - exit 124 at 4.11s, no upstream arrival - so the gap is specifically a "
"run already in flight).\n"
"User-felt: closing the tab costs money, delays the retry, and on a small deployment (max_concurrent 1-2) blocks "
"other users until the abandoned run finishes."
)

AC = ("1. On client disconnect during a non-streaming deliberation, in-flight stages are cancelled, the concurrency "
"slot is released immediately and no further upstream calls are issued for that request; proven with the run-34 "
"fixture (abort at 2s: stub arrivals for the aborted prompt stop at the stage in flight, and the next request's "
"first upstream arrival is within one stage of its send time instead of 6.1s later). 2. The cancellation is logged "
"once per request (reason=client_disconnect) so the spend is attributable. 3. A test drives disconnect->cancel and "
"asserts both the arrival count and the slot release; red-prove it against today's tree. 4. Streaming and "
"non-streaming paths behave consistently, or the difference is documented.")

lines = B.read_text().splitlines(True)
out, hits = [], 0
for line in lines:
    row = json.loads(line)
    if row.get("id") == "DF-CHIMERA-V2-132":
        hits += 1
        row["title"] = TITLE
        row["reasoning"] = REASONING
        row["acceptance_criteria"] = AC
        out.append(json.dumps(row) + "\n")
    else:
        out.append(line if line.endswith("\n") else line + "\n")
assert hits == 1, hits
B.write_text("".join(out))
print("patched 132; lines:", len(out))
