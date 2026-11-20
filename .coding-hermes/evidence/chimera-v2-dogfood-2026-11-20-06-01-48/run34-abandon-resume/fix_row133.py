import json, pathlib

B = pathlib.Path("/home/kara/chimera-v2/.coding-hermes/board/tasks.jsonl")
OLD = ("a fourth (CLI Ctrl-C while queued) was cancelled before dispatch and never appears at all")
NEW = ("the CLI arm (Ctrl-C at 2s, which did NOT stop the run - `timeout` had to kill it at 4.11s after "
       "engine_dispatched) reached no terminal status in the window either, so aborted work is absent from the "
       "numerator AND from every other series")

lines = B.read_text().splitlines(True)
out, hits = [], 0
for line in lines:
    row = json.loads(line)
    if row.get("id") == "DF-CHIMERA-V2-133":
        assert OLD in row["reasoning"], "fragment missing"
        row["reasoning"] = row["reasoning"].replace(OLD, NEW)
        hits += 1
        out.append(json.dumps(row) + "\n")
    else:
        out.append(line if line.endswith("\n") else line + "\n")
assert hits == 1, hits
B.write_text("".join(out))
print("patched 133 cli clause")
