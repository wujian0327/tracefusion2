#!/usr/bin/env python3
"""Check capture integrity and fixture observations; does NOT infer source labels."""
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(directory):
    directory = Path(directory)
    rows = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    require(len(rows) >= 3 and rows[0]["kind"] == "start" and rows[-1]["kind"] == "finish", "missing boundaries")
    require([r["seq"] for r in rows] == list(range(1, len(rows) + 1)), "event gap/order")
    require(rows[-1]["values"][0] == "complete" and not rows[-1]["values"][1], "collector reports unknown")
    require(sum(r["kind"] == "start" for r in rows) == 1 and sum(r["kind"] == "finish" for r in rows) == 1, "duplicate boundaries")
    mode = rows[0]["values"][2] if len(rows[0]["values"]) > 2 else "full"
    require(mode in ("full", "sparse"), "unsupported observation mode")
    scope_path = directory / "observation.properties"
    scope_hash = rows[0]["values"][3] if len(rows[0]["values"]) > 3 else ""
    require(scope_hash == (hashlib.sha256(scope_path.read_bytes()).hexdigest() if scope_path.exists() else ""),
            "scope evidence hash mismatch")
    if mode == "sparse":
        from observation import expand
        rows = expand(directory, rows)
    plans, methods = {}, {}
    for file in directory.glob("*.plan.jsonl"):
        for line in file.read_text().splitlines():
            p = json.loads(line)
            require(p["site"] not in plans, "duplicate site")
            plans[p["site"]] = p
            methods.setdefault(p["method"], []).append(p)
    for method, instructions in methods.items():
        require([p["pc"] for p in instructions] == list(range(len(instructions))), "non-contiguous plan")
        require(all(p["site"] == f'{method}@{p["pc"]}' for p in instructions), "plan site mismatch")
    stack, seen, memory, threads, classes, objects = [], set(), {}, set(), set(), set()
    for r in rows[1:-1]:
        kind, site, values, fid = r["kind"], r["site"], r["values"], r["frame"]
        if kind == "class":
            require(site not in classes, "repeated class transform")
            classes.add(site)
            original = directory / (site.replace("/", "_") + ".original.class")
            require(hashlib.sha256(original.read_bytes()).hexdigest() == values[0], "class hash")
            continue
        require(kind not in ("reject", "start", "finish"), "unexpected lifecycle record")
        threads.add(r["thread"])
        if kind == "enter":
            require(fid not in seen and site in methods, "frame identity/method")
            require(site.split(".")[0] in classes, "method without class record")
            seen.add(fid)
            for value in values[1:]:
                if isinstance(value, str):
                    require(value.startswith("o") and value[1:].isdigit(), "invalid object ID")
                    if value != "o0": objects.add(value)
            parent = stack[-1]["id"] if stack else 0
            require(values and values[0] == parent, "parent frame")
            if stack:
                f = stack[-1]
                require(f["pending"] == "enter", "unannounced callee")
                require(plans[f["last"]]["operands"][0] == site, "callee mismatch")
                f["pending"] = "child"
            stack.append(dict(id=fid, method=site, next=0, pending=None, last=None))
            continue
        require(stack and stack[-1]["id"] == fid, "event frame stack")
        f = stack[-1]
        require(site in plans and plans[site]["method"] == f["method"], "unknown/cross-method site")
        p = plans[site]
        op = p["opcode"]
        if kind == "step":
            require(f["pending"] is None and p["pc"] == f["next"], "instruction sequence")
            f["last"], f["next"] = site, p["pc"] + 1
            if op == 167:
                f["next"] = p["operands"][0]
            elif 153 <= op <= 166 or op in (198, 199):
                f["pending"] = "branch"
            elif op in (180, 181):
                f["pending"] = "read" if op == 180 else "write"
            elif op == 184:
                f["pending"] = "call"
            elif op in (172, 176, 177):
                f["pending"] = "exit"
        else:
            require(f["last"] == site and f["pending"] == kind, "missing/unexpected observation")
            f["pending"] = None
            if kind == "branch":
                require(values in ([0], [1]), "branch value")
                if values[0]:
                    f["next"] = p["operands"][0]
            elif kind in ("read", "write"):
                require(len(values) == 4, "field shape")
                obj, field, value, version = values
                require(isinstance(obj, str) and obj.startswith("o") and obj[1:].isdigit() and obj != "o0", "field object")
                require(obj in objects, "field object without observed argument")
                require(field == p["operands"][0] and type(value) is int and -(2**31) <= value < 2**31, "field descriptor/value")
                key = (obj, field)
                old_version, old_value = memory.get(key, (0, value))
                if kind == "write":
                    require(version == old_version + 1, "field write version")
                else:
                    require(version == old_version and value == old_value, "unobserved field mutation/version")
                memory[key] = (version, value)
            elif kind == "call":
                f["pending"] = "enter"
            elif kind == "call_return":
                pass
            elif kind == "exit":
                require(len(values) == (0 if op == 177 else 1), "return shape")
                stack.pop()
                if stack:
                    require(stack[-1]["pending"] == "child", "return without caller")
                    stack[-1]["pending"] = "call_return"
            else:
                raise ValueError("unexpected event " + kind)
    require(not stack and len(threads) == 1 and seen, "incomplete/thread scope")
    require(rows[-1]["values"][2] == len(seen) and rows[-1]["values"][4] == len(classes), "footer counts")
    require(objects == {f"o{i}" for i in range(1, rows[-1]["values"][3] + 1)}, "object identity count/gap")
    return rows


def check_fixture(directory, case):
    rows = validate(directory)
    entries = [r for r in rows if r["kind"] == "enter"]
    roots = [r for r in entries if r["values"][0] == 0]
    reads = [r["values"] for r in rows if r["kind"] == "read"]
    writes = [r["values"] for r in rows if r["kind"] == "write"]
    branches = [r["values"][0] for r in rows if r["kind"] == "branch"]
    a, b = roots[0]["values"][1:3]
    require(a == b if case == "alias" else a != b, "alias/distinct input identity")
    field = "demo/Cell.value:I"
    expected_reads = {
        "left": [[a, field, 17, 0]], "right": [[b, field, 17, 0]],
        "alias": [[a, field, 17, 0]],
        "overwrite": [[b, field, 17, 0], [a, field, 17, 1]],
        "nested": [[b, field, 17, 0]],
        "loop": [[a, field, 17, 0]] + [[b, field, 17, 0]] * 3,
        "gc": [[a, field, 17, 0], [b, field, 17, 0]],
    }[case]
    require(reads == expected_reads, "fixture field reads")
    require(writes == ([[a, field, 17, 1]] if case == "overwrite" else []), "fixture writes")
    require(branches == {"left": [0], "right": [1], "alias": [1], "overwrite": [],
                         "nested": [1], "loop": [0, 0, 0, 1], "gc": [0, 1]}[case], "fixture branch directions")
    exits = {r["frame"]: r for r in rows if r["kind"] == "exit"}
    expected_result = 34 if case == "nested" else 68 if case == "loop" else 17
    require(all(exits[r["frame"]]["values"] == [expected_result] for r in roots), "fixture returned value")
    if case == "nested":
        require([r["site"].split(".")[-1].split("(")[0] for r in entries] == ["nested", "choose", "twice"], "nested call order")
        require(entries[-1]["values"][1:] == [17], "nested argument")
    if case == "gc":
        require(roots[0]["values"][1:3] == roots[1]["values"][1:3], "identity across GC request")
    return {"events": len(rows), "instructions": sum(r["kind"] == "step" for r in rows),
            "frames": len(entries), "reads": len(reads), "writes": len(writes), "branches": len(branches)}


def verify_run(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "validation.json").read_text())
    require(manifest["status"] == "pass", "run did not pass")
    for name, sha in manifest["source_sha256"].items():
        require(hashlib.sha256((directory / "source" / name).read_bytes()).hexdigest() == sha, "source snapshot hash")
    require(hashlib.sha256((directory / "tracefusion-java-agent.jar").read_bytes()).hexdigest()
            == manifest["agent_sha256"], "agent hash")
    expected = {(m, c) for m in ("default", "interpreter")
                for c in ("left", "right", "alias", "overwrite", "nested", "loop", "gc")}
    require(len(manifest["cases"]) == len(expected)
            and {(r["mode"], r["case"]) for r in manifest["cases"]} == expected, "case coverage")
    total = 0
    for r in manifest["cases"]:
        capture = directory / f'{r["mode"]}-{r["case"]}'
        stats = check_fixture(capture, r["case"])
        require(all(r[k] == v for k, v in stats.items()), "saved counts mismatch")
        require(r["native"]["stdout"] == r["observed"]["stdout"], "saved business output mismatch")
        require((capture / "demo_Subject.original.class").read_bytes()
                == (directory / "fixture-classes/demo/Subject.class").read_bytes(), "captured class identity")
        require((capture / "field_demo_Cell.class").read_bytes()
                == (directory / "fixture-classes/demo/Cell.class").read_bytes(), "field owner identity")
        total += stats["events"]
    expected_negative = {"null", "threads", "unsupported", "limit", "external", "handler", "volatile"}
    require(len(manifest["negative_cases"]) == 7
            and {r["case"] for r in manifest["negative_cases"]} == expected_negative, "negative case coverage")
    for r in manifest["negative_cases"]:
        try: validate(directory / ("negative-" + r["case"]))
        except ValueError: pass
        else: raise ValueError("negative capture accepted")
    require(len(manifest["fault_checks"]) == 8, "fault coverage")
    for r in manifest["fault_checks"]:
        try: check_fixture(directory / "faults" / r["fault"], "overwrite")
        except ValueError: pass
        else: raise ValueError("fault accepted")
    return {"status": "pass", "positive_captures": 14, "positive_events": total,
            "negative_captures": 7, "fault_rejections": 8,
            "scope": "collection integrity and fixture observations; not provenance inference"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_run(args.directory), indent=2))
