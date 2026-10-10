#!/usr/bin/env python3
"""Bounded JVM replay and direct data-dependency queries. No fixture oracle imports."""
from dataclasses import dataclass, field
import argparse
import hashlib
import json
import re
from pathlib import Path

from classfile import descriptor, read_class
from verify import validate, require


def i32(x): return ((x + 2**31) % 2**32) - 2**31


@dataclass(frozen=True)
class Value:
    kind: str
    value: object
    node: int


@dataclass
class Frame:
    id: int
    method: str
    root: int
    locals: dict
    stack: list = field(default_factory=list)
    pending: object = None
    returned: object = None


class Engine:
    def __init__(self, directory, config):
        self.directory, self.config = Path(directory), config
        self.rows = validate(self.directory)  # structural checks only; never check_fixture()
        require(self.rows[0]["values"][0] == "java-collection-v1", "unsupported capture schema")
        self.methods, self.plans, self.fields = {}, {}, {}
        for r in self.rows:
            if r["kind"] != "class": continue
            stem = r["site"].replace("/", "_")
            c = read_class((self.directory / (stem + ".original.class")).read_bytes())
            require(c["name"] == r["site"], "class name mismatch")
            decoded = [p for m in c["methods"].values() for p in m["plans"]]
            saved = [json.loads(x) for x in (self.directory / (stem + ".plan.jsonl")).read_text().splitlines()]
            require(saved == decoded, "collector plan differs from independently decoded original class")
            self.methods.update(c["methods"])
            self.plans.update({p["site"]: p for p in decoded})
            self.fields.update(c["fields"])
        for f in self.directory.glob("field_*.class"):
            self.fields.update(read_class(f.read_bytes(), fields_only=True)["fields"])
        for p in self.plans.values():
            if p["opcode"] in (180, 181): self.check_field(p["operands"][0])
            if p["opcode"] == 184:
                require(p["operands"][0] in self.methods, "unavailable callee")
        self.roots = [r for r in self.rows if r["kind"] == "enter" and r["values"][0] == 0]
        self.field_labels, self.arg_labels, self.bindings = {}, {}, []
        self.bind()
        self.nodes, self.frames, self.memory, self.answers, self.branches = [], [], {}, {}, []
        self.root_count = 0

    def check_field(self, name):
        require(name.endswith(":I") and name in self.fields and self.fields[name] & (0x8 | 0x40) == 0,
                "field not declared nonvolatile instance int: " + name)

    def bind(self):
        q = self.config
        require(q.get("schema") == "java-source-query-v1", "query schema")
        require(set(q) == {"schema", "sources", "targets"}, "unexpected query keys")
        ids = set()
        for s in q["sources"]:
            require(isinstance(s.get("id"), str) and s["id"] and s["id"] not in ids, "source identifier")
            ids.add(s["id"])
            require(type(s.get("root")) is int and 1 <= s["root"] <= len(self.roots), "source root not observed")
            r = self.roots[s["root"] - 1]
            args, ret = descriptor(self.methods[r["site"]]["descriptor"])
            slot = s.get("arg")
            require(type(slot) is int and 0 <= slot < len(args), "source argument slot")
            if s.get("kind") == "initial_field":
                require(set(s) == {"id", "kind", "root", "arg", "field"}, "field source keys")
                require(s["root"] == 1 and args[slot] == "ref", "initial field binds a first-root reference")
                self.check_field(s["field"])
                raw_args = self.methods[r["site"]]["descriptor"].split(")", 1)[0][1:]
                declared_args = re.findall(r"L[^;]+;|[IZBCS]", raw_args)
                owner = s["field"].rsplit(".", 1)[0]
                require(declared_args[slot] == "L" + owner + ";", "source owner must match declared argument class")
                obj = r["values"][slot + 1]
                require(obj != "o0", "null source object")
                location = (obj, s["field"])
                self.field_labels.setdefault(location, []).append(s["id"])
                self.bindings.append(dict(id=s["id"], kind="initial_field", object=obj, field=s["field"], version=0))
            elif s.get("kind") == "argument":
                require(set(s) == {"id", "kind", "root", "arg"}, "argument source keys")
                require(args[slot] == "int", "only integer arguments are data sources")
                self.arg_labels.setdefault((s["root"], slot), []).append(s["id"])
                self.bindings.append(dict(id=s["id"], kind="argument", root=s["root"], arg=slot))
            else: raise ValueError("unsupported source boundary")
        ids = set()
        require(q["targets"], "no targets")
        for t in q["targets"]:
            require(set(t) == {"id", "root", "kind"} and t["kind"] == "return", "only return targets supported")
            require(isinstance(t["id"], str) and t["id"] and t["id"] not in ids, "target identifier")
            require(type(t["root"]) is int and 1 <= t["root"] <= len(self.roots), "target root not observed")
            ids.add(t["id"])

    def node(self, kind, value_kind, value, parents=(), address=(), site="", frame=0, labels=(), origin=None):
        require(len(self.nodes) < 1_000_000, "dependency graph limit")
        index = len(self.nodes)
        require(all(0 <= p < index for p in list(parents) + list(address)), "invalid dependency edge")
        self.nodes.append(dict(id=index, kind=kind, type=value_kind, value=value,
                               data_parents=list(parents), address_parents=list(address),
                               site=site, frame=frame, labels=list(labels), origin=origin))
        return Value(value_kind, value, index)

    def derived(self, kind, value, inputs, r, value_kind="int", address=()):
        return self.node(kind, value_kind, value, [v.node for v in inputs], [v.node for v in address],
                         r["site"], r["frame"])

    @staticmethod
    def pop(f, kind=None):
        require(f.stack, "operand stack underflow")
        v = f.stack.pop()
        require(kind is None or v.kind == kind, "operand type mismatch")
        return v

    def origins(self, node):
        pending, seen, leaves, labels = [node], set(), [], set()
        while pending:
            i = pending.pop()
            if i in seen: continue
            seen.add(i)
            n = self.nodes[i]
            labels.update(n["labels"])
            if n["origin"] is not None: leaves.append(n["origin"])
            pending.extend(n["data_parents"])  # Never merge address or branch observations.
        return sorted(labels), sorted(leaves, key=lambda x: json.dumps(x, sort_keys=True))

    def enter(self, r):
        types, _ = descriptor(self.methods[r["site"]]["descriptor"])
        observed = r["values"][1:]
        require(len(types) == len(observed), "entry argument count")
        for t, v in zip(types, observed):
            require((type(v) is int and -2**31 <= v < 2**31) if t == "int"
                    else isinstance(v, str) and v.startswith("o") and v[1:].isdigit(), "entry value type")
        if not self.frames:
            self.root_count += 1
            root = self.root_count
            vals = [self.node("argument", t, v, labels=self.arg_labels.get((root, i), ()),
                              origin=dict(kind="argument", root=root, arg=i, type=t), site=r["site"], frame=r["frame"])
                    for i, (t, v) in enumerate(zip(types, observed))]
        else:
            parent = self.frames[-1]
            require(parent.pending and parent.pending[0] == "call", "missing semantic call")
            _, method, vals = parent.pending
            require(method == r["site"] and [(v.kind, v.value) for v in vals] == list(zip(types, observed)),
                    "callee arguments disagree with caller operand stack")
            root = parent.root
            vals = [self.derived("parameter", v.value, [v], r, v.kind) for v in vals]
        self.frames.append(Frame(r["frame"], r["site"], root, dict(enumerate(vals))))

    def step(self, r, f):
        p = self.plans[r["site"]]
        op, args = p["opcode"], p["operands"]
        if op == 0 or op == 167: return
        if op == 1 or 2 <= op <= 8 or op in (16, 17, 18):
            kind, value = ("ref", "o0") if op == 1 else ("int", op - 3 if 2 <= op <= 8 else args[0])
            f.stack.append(self.derived("constant", value, [], r, kind))
        elif op in (21, 25):
            require(args[0] in f.locals, "uninitialized local")
            v = f.locals[args[0]]
            require(v.kind == ("int" if op == 21 else "ref"), "local load type")
            f.stack.append(self.derived("local_load", v.value, [v], r, v.kind))
        elif op in (54, 58):
            v = self.pop(f, "int" if op == 54 else "ref")
            f.locals[args[0]] = self.derived("local_store", v.value, [v], r, v.kind)
        elif op == 87: self.pop(f)
        elif op == 89:
            v = self.pop(f); f.stack.extend([v, v])
        elif op == 95:
            a, b = self.pop(f), self.pop(f); f.stack.extend([a, b])
        elif op in (96, 100, 104, 108, 112, 120, 122, 124, 126, 128, 130):
            b, a = self.pop(f, "int"), self.pop(f, "int")
            x, y = a.value, b.value
            if op in (108, 112):
                require(y != 0, "division by zero without exceptional completion")
                quotient = (abs(x) // abs(y)) * (-1 if (x < 0) != (y < 0) else 1)
                z = quotient if op == 108 else x - quotient * y
            else:
                z = {96: lambda: x+y, 100: lambda: x-y, 104: lambda: x*y,
                     120: lambda: x << (y & 31), 122: lambda: x >> (y & 31),
                     124: lambda: (x & 0xffffffff) >> (y & 31), 126: lambda: x & y,
                     128: lambda: x | y, 130: lambda: x ^ y}[op]()
            f.stack.append(self.derived("int_op_" + str(op), i32(z), [a, b], r))
        elif op in (116, 145, 146, 147):
            a = self.pop(f, "int")
            z = {116: lambda: -a.value, 145: lambda: (a.value + 128) % 256 - 128,
                 146: lambda: a.value & 65535, 147: lambda: (a.value + 32768) % 65536 - 32768}[op]()
            f.stack.append(self.derived("int_op_" + str(op), i32(z), [a], r))
        elif op == 132:
            require(args[0] in f.locals and f.locals[args[0]].kind == "int", "iinc local")
            a = f.locals[args[0]]
            f.locals[args[0]] = self.derived("iinc", i32(a.value + args[1]), [a], r)
        elif 153 <= op <= 166 or op in (198, 199):
            if op in (198, 199):
                a = self.pop(f, "ref"); inputs = [a]
                taken = (a.value == "o0") if op == 198 else (a.value != "o0")
            elif op in (165, 166):
                b, a = self.pop(f, "ref"), self.pop(f, "ref"); inputs = [a, b]
                taken = a.value == b.value if op == 165 else a.value != b.value
            else:
                if op <= 158:
                    a = self.pop(f, "int"); x, y, inputs, cmp = a.value, 0, [a], op - 153
                else:
                    b, a = self.pop(f, "int"), self.pop(f, "int")
                    x, y, inputs, cmp = a.value, b.value, [a, b], op - 159
                taken = (x == y, x != y, x < y, x >= y, x > y, x <= y)[cmp]
            condition = self.derived("branch_predicate", int(taken), inputs, r)
            f.pending = ("branch", condition)
        elif op in (180, 181):
            val = self.pop(f, "int") if op == 181 else None
            obj = self.pop(f, "ref")
            require(obj.value != "o0", "null field access")
            f.pending = ("write" if op == 181 else "read", obj, args[0], val)
        elif op == 184:
            types, _ = descriptor(self.methods[args[0]]["descriptor"])
            vals = [self.pop(f, t) for t in reversed(types)][::-1]
            f.pending = ("call", args[0], vals)
        elif op in (172, 176, 177):
            _, ret = descriptor(self.methods[f.method]["descriptor"])
            require(ret == {172: "int", 176: "ref", 177: "void"}[op], "return opcode/type")
            v = None if ret == "void" else self.pop(f, ret)
            require(not f.stack, "nonempty stack at return outside contract")
            f.pending = ("exit", v)
        else: raise ValueError("unsupported replay opcode " + str(op))
        m = self.methods[f.method]
        require(len(f.stack) <= m["max_stack"] and all(0 <= i < m["max_locals"] for i in f.locals), "class stack/local bounds")

    def observe(self, r, f):
        kind, values = r["kind"], r["values"]
        require(f.pending and f.pending[0] == ("call" if kind == "call_return" else kind), "semantic event mismatch")
        if kind == "branch":
            condition = f.pending[1]
            require(len(values) == 1 and type(values[0]) is int and values == [condition.value], "branch disagrees with computed operands")
            labels, origins = self.origins(condition.node)
            self.branches.append(dict(root=f.root, site=r["site"], frame=f.id, taken=bool(condition.value),
                                      node=condition.node, predicate_sources=labels, predicate_origins=origins))
            f.pending = None
        elif kind in ("read", "write"):
            _, obj, name, val = f.pending
            oid, field_name, observed, version = values
            require((oid, field_name) == (obj.value, name), "field receiver/identity disagrees with operand stack")
            key = (oid, name)
            old_version = self.memory[key][0] if key in self.memory else 0
            if kind == "read":
                require(version == old_version, "field read version")
                if key not in self.memory:
                    initial = self.node("initial_field", "int", observed, labels=self.field_labels.get(key, ()),
                                        origin=dict(kind="initial_field", object=oid, field=name, version=0),
                                        site=r["site"], frame=f.id)
                    self.memory[key] = (0, initial)
                val = self.memory[key][1]
                require(val.value == observed, "field read differs from last definition")
                f.stack.append(self.derived("field_read", observed, [val], r, address=[obj]))
            else:
                require(version == old_version + 1 and val.value == observed, "write value/version disagrees with computation")
                self.memory[key] = (version, self.derived("field_write", observed, [val], r, address=[obj]))
            f.pending = None
        elif kind == "call": pass
        elif kind == "call_return":
            _, ret = descriptor(self.methods[f.pending[1]]["descriptor"])
            if ret != "void":
                require(f.returned is not None, "missing computed callee return")
                f.stack.append(self.derived("call_return", f.returned.value, [f.returned], r, f.returned.kind))
            f.pending, f.returned = None, None
        elif kind == "exit":
            v = f.pending[1]
            require(values == ([] if v is None else [v.value]), "return value disagrees with bytecode replay")
            if v is not None:
                require(type(values[0]) is type(v.value), "return representation/type mismatch")
            if v is not None: v = self.derived("return", v.value, [v], r, v.kind)
            self.frames.pop()
            if self.frames: self.frames[-1].returned = v
            else: self.answers[f.root] = v
        else: raise ValueError("unsupported observation")

    def run(self):
        for r in self.rows:
            if r["kind"] in ("start", "class", "finish"): continue
            if r["kind"] == "enter": self.enter(r); continue
            f = self.frames[-1]
            require(f.id == r["frame"], "replay frame mismatch")
            if r["kind"] == "step": self.step(r, f)
            else: self.observe(r, f)
        require(not self.frames, "incomplete replay")
        results = []
        for t in self.config["targets"]:
            v = self.answers[t["root"]]
            if v is None:
                results.append(dict(id=t["id"], root=t["root"], status="no_sink")); continue
            require(v.kind == "int", "only int return queries supported")
            labels, origins = self.origins(v.node)
            results.append(dict(id=t["id"], root=t["root"], status="ok", value=v.value,
                                direct_sources=labels, direct_origins=origins, node=v.node))
        aliases = [sorted(labels) for labels in self.field_labels.values() if len(labels) > 1]
        return dict(schema="java-provenance-v1", status="ok", semantics="operational-direct-data-dependency",
                    source_bindings=self.bindings, source_aliases=aliases, results=results,
                    branch_observations=self.branches, nodes=self.nodes,
                    evidence={f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(self.directory.iterdir())
                              if f.suffix == ".class" or f.name == "events.jsonl" or f.name.endswith(".plan.jsonl")})


def infer(directory, config):
    try: return Engine(directory, config).run()
    except (ValueError, KeyError, IndexError, TypeError, OSError, UnicodeError) as e:
        return dict(schema="java-provenance-v1", status="unknown", reason=str(e), results=[])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = infer(args.directory, json.loads(args.query.read_text()))
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k not in ("nodes", "branch_observations", "evidence")}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if output["status"] == "ok" else 2)
