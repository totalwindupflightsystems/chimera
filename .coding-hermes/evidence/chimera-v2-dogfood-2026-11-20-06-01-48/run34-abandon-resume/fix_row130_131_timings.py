import json, pathlib

B = pathlib.Path("/home/kara/chimera-v2/.coding-hermes/board/tasks.jsonl")

EDITS = {
"DF-CHIMERA-V2-130": [
 ("each returned HTTP 502 in 2.1-9.1s.",
  "each returned HTTP 502 - speed 2.68s, simple 2.27s, auto 3.36s (measured 2026-11-20 against the live process; the same arms in earlier deliveries of this tick ranged 2.1-9.1s, so the retry layer adds variance to a failure that is already decided)."),
 ("adding allowed_models=[z-ai/glm-5] still 502 (2 calls, 9.05s / 8.89s); adding dispatcher_model=z-ai/glm-5 AND aggregator_model=z-ai/glm-5 still 502 (2 calls, 8.31s / 7.06s) - the failure message still names deepseek-v4-flash, a model the caller never asked for.",
  "adding allowed_models=[z-ai/glm-5] still 502 (2 calls); adding dispatcher_model=z-ai/glm-5 AND aggregator_model=z-ai/glm-5 still 502 in 2.29s against 2.34s for the un-overridden request in the same minute - statistically identical, and the failure message still names deepseek-v4-flash, a model the caller never asked for."),
],
"DF-CHIMERA-V2-131": [
 ("both returned 502 in 8.31s and 7.06s with",
  "a same-minute pair against the un-overridden request shows the override changes nothing measurable (2.29s with dispatcher+aggregator overrides vs 2.34s without, both 502), and every one of these calls returned 502 with"),
],
}

lines = B.read_text().splitlines(True)
out, seen = [], set()
for line in lines:
    row = json.loads(line)
    rid = row.get("id")
    if rid in EDITS:
        seen.add(rid)
        txt = row["reasoning"]
        for old, new in EDITS[rid]:
            assert old in txt, f"{rid}: missing fragment: {old[:60]}"
            txt = txt.replace(old, new)
        row["reasoning"] = txt
        out.append(json.dumps(row) + "\n")
    else:
        out.append(line if line.endswith("\n") else line + "\n")
assert seen == set(EDITS), seen
B.write_text("".join(out))
print("patched:", sorted(seen))
