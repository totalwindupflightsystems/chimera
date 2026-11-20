import json, pathlib

B = pathlib.Path("/home/kara/chimera-v2/.coding-hermes/board/tasks.jsonl")
OLD = ("a Ctrl-C'd CLI that is still QUEUED is cancelled cleanly - exit 124 at 4.11s, no upstream arrival - so the "
       "gap is specifically a run already in flight).")
NEW = ("the CLI arm is not a counter-example either: Ctrl-C at 2s did not end the run - the process had to be killed "
       "by `timeout` (exit 124, wall 4.11s, stderr shows engine_dispatched 0.2s earlier) - so the CLI also keeps "
       "working after the user gives up; its upstream arrival was cut off by probe exit and is UNRESOLVED, not "
       "proven clean).")

lines = B.read_text().splitlines(True)
out, hits = [], 0
for line in lines:
    row = json.loads(line)
    if row.get("id") == "DF-CHIMERA-V2-132":
        assert OLD in row["reasoning"], "fragment missing"
        row["reasoning"] = row["reasoning"].replace(OLD, NEW)
        hits += 1
        out.append(json.dumps(row) + "\n")
    else:
        out.append(line if line.endswith("\n") else line + "\n")
assert hits == 1, hits
B.write_text("".join(out))
print("patched 132 ctrl-c clause")
