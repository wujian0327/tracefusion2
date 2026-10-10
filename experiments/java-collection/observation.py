#!/usr/bin/env python3
"""Bounded query-entry call closure and sparse trace expansion; no fixture answers.

This eliminates deterministic step probes, not field-level dependencies. Every
field access, branch outcome, call boundary and return remains observed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from classfile import read_class


def require(ok, message):
    if not ok: raise ValueError(message)


def query_hash(query):
    return hashlib.sha256(json.dumps(query, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def closure(methods, entry):
    todo, reached = [entry], set()
    while todo:
        name = todo.pop()
        if name in reached: continue
        require(name in methods, "unavailable scope method: " + name)
        reached.add(name)
        todo.extend(p["operands"][0] for p in methods[name]["plans"] if p["opcode"] == 184)
    return sorted(reached)


def plan(classes, entry, query, output, snapshots=False):
    # Explicit entry binding is required: root invocation ordinals alone cannot
    # identify a class/method before the program runs.
    owner = entry.split(".", 1)[0]
    data = (Path(classes) / (owner + ".class")).read_bytes()
    decoded = read_class(data)
    require(decoded["name"] == owner, "entry class mismatch")
    methods = closure(decoded["methods"], entry)
    # First experiment deliberately limits call closure to one application class.
    props = {"schema": "java-observation-scope-v1", "entry": entry, "classes": owner,
             "query.sha256": query_hash(query), "sha256." + owner: hashlib.sha256(data).hexdigest(),
             "method.count": str(len(methods))}
    props.update({"method." + str(i): m for i, m in enumerate(methods)})
    if snapshots:
        props["schema"] = "java-observation-scope-v2"
        require(not any(p["opcode"] == 184 and p["operands"][0] == entry
                        for m in methods for p in decoded["methods"][m]["plans"]), "recursive boundary entry")
        fields = []
        args = re.findall(r"L[^;]+;|[IZBCS]", entry.split("(", 1)[1].split(")", 1)[0])
        for slot, arg in enumerate(args):
            if not arg.startswith("L"): continue
            owner = arg[1:-1]
            data = (Path(classes) / (owner + ".class")).read_bytes()
            props["snapshot.sha256." + owner] = hashlib.sha256(data).hexdigest()
            for field, access in sorted(read_class(data, fields_only=True)["fields"].items()):
                if not access & 8 and field.endswith(":I"):
                    require(access & 1 and not access & 64, "snapshot requires public nonvolatile int fields")
                    fields.append((slot, field))
        props["snapshot.count"] = str(len(fields))
        for i, (slot, field) in enumerate(fields):
            props[f"snapshot.{i}.arg"], props[f"snapshot.{i}.field"] = str(slot), field
    Path(output).write_text("".join(k + "=" + v + "\n" for k, v in props.items()))
    return props


def read_scope(directory):
    file = Path(directory) / "observation.properties"
    if not file.exists(): return None
    props = {}
    for line in file.read_text().splitlines():
        key, sep, value = line.partition("=")
        require(sep and key not in props, "invalid/duplicate scope property")
        props[key] = value
    require(props.get("schema") in ("java-observation-scope-v1", "java-observation-scope-v2"), "scope schema")
    require(props.get("method.count", "").isdigit(), "scope method count")
    count = int(props["method.count"])
    require(0 < count <= 10000, "scope method count limit")
    methods = [props["method." + str(i)] for i in range(count)]
    require(methods == sorted(set(methods)) and props["entry"] in methods, "scope methods")
    return props


def decoded_scope(directory, props):
    methods = {}
    for owner in props["classes"].split(","):
        data = (Path(directory) / (owner.replace("/", "_") + ".original.class")).read_bytes()
        require(hashlib.sha256(data).hexdigest() == props["sha256." + owner], "scope class hash")
        c = read_class(data)
        require(c["name"] == owner, "scope class name")
        methods.update(c["methods"])
    expected = closure(methods, props["entry"])
    require(expected == [props["method." + str(i)] for i in range(int(props["method.count"]))],
            "scope is not entry call closure")
    return {m: methods[m] for m in expected}


def expand(directory, raw, max_steps=1_000_000):
    """Derive instruction rows in memory. Never rewrite/renumber the raw file.

    Stop at the FIRST mandatory observation, so a missing read/branch/return
    cannot be silently skipped by using the next event's address as a target.
    The existing semantic engine independently recomputes each branch outcome.
    """
    props = read_scope(directory)
    require(props is not None, "sparse capture lacks scope")
    methods = decoded_scope(directory, props)
    result, stack, steps = [], [], 0
    for r in raw:
        kind = r["kind"]
        require(kind != "step", "unexpected raw step in sparse mode")
        if kind == "enter":
            require(r["site"] in methods, "entry outside scope")
            if not stack: require(r["site"] == props["entry"], "root differs from query entry")
            else: require(stack[-1]["pending"] == "enter", "unexpected callee entry")
            stack.append(dict(method=r["site"], frame=r["frame"], pc=0, pending=None))
        elif kind not in ("start", "class", "finish", "reject", "snapshot"):
            require(stack and r["frame"] == stack[-1]["frame"], "sparse frame mismatch")
            f = stack[-1]
            if f["pending"] is None:
                while True:
                    require(steps < max_steps, "sparse expansion instruction limit")
                    code = methods[f["method"]]["plans"]
                    require(0 <= f["pc"] < len(code), "sparse pc outside method")
                    p = code[f["pc"]]; op = p["opcode"]
                    steps += 1
                    result.append(dict(r, kind="step", site=p["site"], values=[],
                                       derived=True, before_raw_seq=r["seq"]))
                    f["last"] = p["site"]
                    f["pc"] += 1
                    if op == 167: f["pc"] = p["operands"][0]
                    elif 153 <= op <= 166 or op in (198, 199): f["pending"] = "branch"
                    elif op in (180, 181): f["pending"] = "read" if op == 180 else "write"
                    elif op == 184: f["pending"] = "call"
                    elif op in (172, 176, 177): f["pending"] = "exit"
                    if f["pending"] is not None: break
            require(kind == f["pending"] and r["site"] == f["last"], "missing mandatory sparse observation")
            f["pending"] = None
            if kind == "branch":
                require(r["values"] in ([0], [1]), "sparse branch value")
                if r["values"][0]:
                    pc = int(f["last"].rsplit("@", 1)[1])
                    f["pc"] = methods[f["method"]]["plans"][pc]["operands"][0]
            elif kind == "call": f["pending"] = "enter"
            elif kind == "exit":
                stack.pop()
                if stack: stack[-1]["pending"] = "call_return"
        result.append(dict(r, derived=False, raw_seq=r["seq"]))
    require(not stack, "incomplete sparse frames")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--classes", type=Path, required=True)
    p.add_argument("--entry", required=True)
    p.add_argument("--query", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--snapshots", action="store_true", help="uniform v2 root field snapshots")
    a = p.parse_args()
    print(json.dumps(plan(a.classes, a.entry, json.loads(a.query.read_text()), a.output, a.snapshots), indent=2))
