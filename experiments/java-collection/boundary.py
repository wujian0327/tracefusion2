"""Boundary-only JVM replay using the shared operational dependency semantics.

No fixture oracle, observed internal path, or full/sparse trace is read. All
internal instructions, field accesses, calls and branch outcomes are computed.
"""
import hashlib
import re
from pathlib import Path
from classfile import read_class
from observation import read_scope, decoded_scope, require


def snapshot_layout(directory, props):
    methods = decoded_scope(directory, props)
    entry = props["entry"]
    require(not any(p["opcode"] == 184 and p["operands"][0] == entry for m in methods.values() for p in m["plans"]),
            "recursive boundary entry")
    args = re.findall(r"L[^;]+;|[IZBCS]", methods[entry]["descriptor"].split(")", 1)[0][1:])
    expected = []
    for slot, arg in enumerate(args):
        if not arg.startswith("L"): continue
        owner = arg[1:-1]
        data = (Path(directory) / ("field_" + owner.replace("/", "_") + ".class")).read_bytes()
        require(hashlib.sha256(data).hexdigest() == props["snapshot.sha256." + owner], "snapshot owner hash")
        c = read_class(data, fields_only=True)
        require(c["name"] == owner, "snapshot owner name")
        for name, flags in sorted(c["fields"].items()):
            if not flags & 8 and name.endswith(":I"):
                require(flags & 1 and not flags & 64, "snapshot field access contract")
                expected.append((slot, name))
    require(props["snapshot.count"] == str(len(expected)), "incomplete static snapshot layout")
    require(expected == [(int(props[f"snapshot.{i}.arg"]), props[f"snapshot.{i}.field"]) for i in range(len(expected))],
            "snapshot layout mismatch")
    return expected


def validate_snapshots(directory, rows):
    props = read_scope(directory)
    v2 = props is not None and props["schema"] == "java-observation-scope-v2"
    if not v2:
        require(not any(r["kind"] == "snapshot" for r in rows), "snapshot without v2 scope")
        return
    layout = snapshot_layout(directory, props)
    consumed = set()
    for i, root in enumerate(rows):
        if root["kind"] != "enter" or root["values"][0] != 0: continue
        require(root["site"] == props["entry"], "snapshot root entry")
        values = {}
        for offset, (slot, field) in enumerate(layout, 1):
            j = i + offset
            require(j < len(rows), "missing boundary snapshot")
            r = rows[j]
            require(r["kind"] == "snapshot" and r["site"] == root["site"] and r["frame"] == root["frame"]
                    and r["thread"] == root["thread"], "missing/misplaced boundary snapshot")
            require(len(r["values"]) == 4, "snapshot shape")
            arg, obj, name, value = r["values"]
            require(type(arg) is int and (arg, name) == (slot, field) and obj == root["values"][slot + 1]
                    and isinstance(obj, str) and obj.startswith("o") and obj[1:].isdigit() and obj != "o0", "snapshot argument identity")
            require(type(value) is int and -2**31 <= value < 2**31, "snapshot integer")
            key = (obj, name)
            require(key not in values or values[key] == value, "inconsistent aliased snapshots")
            values[key] = value; consumed.add(j)
    require(consumed == {i for i, r in enumerate(rows) if r["kind"] == "snapshot"}, "extra boundary snapshot")


def validate_boundary(directory, rows):
    props = read_scope(directory)
    require(props and props["schema"] == "java-observation-scope-v2", "boundary requires v2 scope")
    current, roots, classes, threads, objects = None, 0, set(), set(), set()
    for r in rows[1:-1]:
        kind, site, values = r["kind"], r["site"], r["values"]
        require(kind in ("class", "enter", "snapshot", "exit"), "internal/unexpected boundary event")
        if kind == "class":
            require(site not in classes and current is None, "boundary class event")
            data = (Path(directory) / (site.replace("/", "_") + ".original.class")).read_bytes()
            require(values == [hashlib.sha256(data).hexdigest()], "class hash")
            classes.add(site); continue
        threads.add(r["thread"])
        require(site == props["entry"] and site.split(".", 1)[0] in classes, "boundary method identity")
        if kind == "enter":
            roots += 1
            require(current is None and r["frame"] == roots and values[0] == 0, "boundary root order")
            current = r["frame"]
            objects.update(v for v in values[1:] if isinstance(v, str) and v != "o0")
        else:
            require(current is not None and current == r["frame"], "boundary frame")
            if kind == "exit": current = None
    require(current is None and roots and len(threads) == 1, "boundary completeness/thread scope")
    require(classes == set(props["classes"].split(",")), "boundary class coverage")
    require(rows[-1]["values"][2:] == [roots, len(objects), len(classes)], "boundary footer counts")
    require(objects == {f"o{i}" for i in range(1, len(objects) + 1)}, "boundary object IDs")
    return rows


def replay(engine):
    next_frame, steps = 0, 0
    rows, index = engine.rows, 0
    while index < len(rows):
        root = rows[index]; index += 1
        if root["kind"] in ("start", "class", "finish"): continue
        require(root["kind"] == "enter", "expected boundary root")
        next_frame += 1
        root = dict(root, frame=next_frame)
        engine.enter(root)
        while rows[index]["kind"] == "snapshot":
            engine.seed_snapshot(dict(rows[index], frame=next_frame)); index += 1
        observed_return = rows[index]; index += 1
        require(observed_return["kind"] == "exit", "missing boundary return")
        pcs, callers = {next_frame: 0}, {}
        while engine.frames:
            require(steps < 1_000_000 and len(engine.frames) <= 512, "boundary replay execution limit")
            frame = engine.frames[-1]
            pc = pcs[frame.id]
            code = engine.methods[frame.method]["plans"]
            require(0 <= pc < len(code), "boundary pc outside method")
            p = code[pc]; op = p["opcode"]
            r = dict(kind="step", site=p["site"], frame=frame.id, values=[], derived=True)
            engine.step(r, frame); steps += 1; pcs[frame.id] += 1
            if op == 167: pcs[frame.id] = p["operands"][0]
            if frame.pending is None: continue
            kind = frame.pending[0]
            if kind == "branch":
                value = frame.pending[1].value
                engine.observe(dict(r, kind=kind, values=[value]), frame)
                if value: pcs[frame.id] = p["operands"][0]
            elif kind in ("read", "write"):
                _, obj, field, val = frame.pending
                key = (obj.value, field)
                require(key in engine.memory, "field absent from complete boundary snapshot")
                version, previous = engine.memory[key]
                engine.observe(dict(r, kind=kind, values=[obj.value, field, previous.value if kind == "read" else val.value,
                                                          version if kind == "read" else version + 1]), frame)
            elif kind == "call":
                _, method, args = frame.pending
                next_frame += 1
                callers[next_frame] = r
                engine.enter(dict(kind="enter", site=method, frame=next_frame, values=[frame.id] + [a.value for a in args]))
                pcs[next_frame] = 0
            elif kind == "exit":
                value = frame.pending[1]
                values = observed_return["values"] if len(engine.frames) == 1 else ([] if value is None else [value.value])
                engine.observe(dict(r, kind="exit", values=values), frame)
                if engine.frames:
                    caller = callers.pop(frame.id)
                    engine.observe(dict(caller, kind="call_return"), engine.frames[-1])
            else: raise ValueError("unsupported boundary replay event")
    engine.replayed_steps = steps
