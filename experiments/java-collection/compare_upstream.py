#!/usr/bin/env python3
"""Unmodified Commons Lang release methods: integration, provenance and command costs.

No fixture answers are imported by the planner, collector or inference engine.
The oracle uses ordered extrema (first argument wins ties), reviewed against
the pinned upstream source. This is not whole-library/application coverage.
"""
import argparse
import datetime
import itertools
import json
import os
from pathlib import Path
import random
import shutil
import sys
import urllib.request
import zipfile

from classfile import read_class
from compare_observations import collect_args, measured, save, summarize
from infer import infer
from observation import plan, query_hash
from run import HERE, ROOT, build, command, digest

OWNER = "org/apache/commons/lang3/math/NumberUtils"
VERSION = "3.17.0"
JARS = {"commons-lang3-3.17.0.jar": "6ee731df5c8e5a2976a1ca023b6bb320ea8d3539fbe64c8a1d5cb765127c33b4",
        "commons-lang3-3.17.0-sources.jar": "5fdcac21ad329766054a95367d7583dfcdca737d221d5e01a5f2a198c04c6b18"}
MODES = ["full", "sparse", "boundary"]


def inputs():
    return list(itertools.product((-1, 0, 1), repeat=3)) + list(itertools.permutations((-2**31, 0, 2**31-1))) + [(-2**31,)*3, (2**31-1,)*3]


def query(rows):
    return dict(schema="java-source-query-v1",
                sources=[dict(id=f"r{r}.arg{i}", kind="argument", root=r, arg=i)
                         for r in range(1, len(rows)+1) for i in range(3)],
                targets=[dict(id=f"r{r}.return", root=r, kind="return") for r in range(1, len(rows)+1)])


def truth(method, rows):
    # Independent mathematical specification, not the implementation's two
    # assignments and not a search for an observed output's matching value.
    result = []
    for root, row in enumerate(rows, 1):
        index = sorted(range(3), key=lambda i: ((-row[i] if method == "max" else row[i]), i))[0]
        result.append((row[index], [f"r{root}.arg{index}"]))
    return result


def check(answer, expected):
    if answer["status"] != "ok": raise AssertionError(str(answer))
    if [(r["value"], r["direct_sources"]) for r in answer["results"]] != expected:
        raise AssertionError("upstream provenance differs from independent ordered-extremum oracle")


def prepare(jdk, out):
    cache = ROOT / "artifacts/java-upstream-deps"; cache.mkdir(exist_ok=True)
    dependencies = []
    for name, sha in JARS.items():
        jar = cache / name
        url = f"https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/{VERSION}/{name}"
        if not jar.exists():
            with urllib.request.urlopen(url, timeout=60) as response: data = response.read(4_000_000)
            if __import__("hashlib").sha256(data).hexdigest() != sha: raise ValueError("upstream download hash")
            jar.write_bytes(data)
        if digest(jar) != sha: raise ValueError("upstream dependency hash")
        shutil.copyfile(jar, out / name)
        dependencies.append(dict(name=name, url=url, sha256=sha))
    jar = out / next(iter(JARS))
    classes = out / "upstream-original"; (classes / OWNER).parent.mkdir(parents=True)
    with zipfile.ZipFile(jar) as z:
        (classes / (OWNER + ".class")).write_bytes(z.read(OWNER + ".class"))
        for name in ("LICENSE.txt", "NOTICE.txt"):
            (out / name).write_bytes(z.read("META-INF/" + name))
    with zipfile.ZipFile(out / "commons-lang3-3.17.0-sources.jar") as z:
        (out / "NumberUtils.java").write_bytes(z.read(OWNER + ".java"))
    agent, fixture, log = build(jdk, out)
    harness = out / "harness-classes"; harness.mkdir()
    log.append(command([jdk / "javac", "--release", "17", "-cp", jar, "-d", harness, HERE / "upstream/CommonsDriver.java"]))
    cp = os.pathsep.join(map(str, (harness, jar)))  # never execute the extracted class
    return agent, fixture, classes, cp, dependencies, log


def scope_negatives(classes, out):
    records = []
    for signature in ("max([I)I", "max(JJJ)J", "createNumber(Ljava/lang/String;)Ljava/lang/Number;"):
        try: plan(classes, OWNER + "." + signature, query(inputs()), out / "rejected.properties", snapshots=True)
        except ValueError as e: records.append(dict(entry=signature, status="unknown", reason=str(e)))
        else: raise AssertionError("unsupported upstream method accepted")
    try: read_class((classes / (OWNER + ".class")).read_bytes())
    except ValueError as e: records.append(dict(entry="unscoped whole class", status="unknown", reason=str(e)))
    else: raise AssertionError("whole-class audit unexpectedly accepted")
    return records


def faults(capture, q, out):
    records = []
    for name in ("missing_exit", "wrong_return", "scope_extra_method", "original_class"):
        dest = out / name; shutil.copytree(capture, dest)
        rows = [json.loads(x) for x in (dest / "events.jsonl").read_text().splitlines()]
        if name == "missing_exit":
            rows.pop(next(i for i, r in enumerate(rows) if r["kind"] == "exit"))
            for i, r in enumerate(rows, 1): r["seq"] = i
        elif name == "wrong_return": next(r for r in rows if r["kind"] == "exit")["values"][0] += 1
        elif name == "scope_extra_method":
            f = dest / "observation.properties"
            f.write_text(f.read_text().replace("method.count=1", "method.count=2") + "method.1=" + OWNER + ".min(III)I\n")
            rows[0]["values"][3] = digest(f)  # semantic closure check, not just a hash mismatch
        else:
            f = dest / (OWNER.replace("/", "_") + ".original.class"); f.write_bytes(f.read_bytes() + b"x")
        (dest / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        answer = infer(dest, q); save(dest / "inference.json", answer)
        if answer["status"] != "unknown" or answer["results"]: raise AssertionError("accepted fault " + name)
        records.append(dict(fault=name, status="unknown", reason=answer["reason"]))
    return records


def main(a):
    jdk = a.jdk.resolve() / "bin"
    out = ROOT / "artifacts" / ("java-upstream-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    out.mkdir(parents=True)
    report = dict(schema="java-upstream-comparison-v1", status="running", modes=MODES, cases=[], measurements=[],
                  rounds=a.rounds, repetitions=a.repeats, warmup_blocks=a.warmup, seed=a.seed,
                  qualification=dict(scope="two unchanged library methods, primitive argument to return",
                     whole_application=False, field_provenance=False, external_tool_comparison=False,
                     steady_state=False, global_optimality=False,
                     boundary="complete integer arguments; no heap inputs or field snapshots in these methods",
                     unobserved="driver, class initialization and unrelated library methods",
                     costs="fresh JVM incl. ASM/startup/output plus fresh Python inference; build/plan excluded"))
    try:
        agent, fixture, classes, cp, report["dependencies"], report["build"] = prepare(jdk, out)
        report["java"] = command([jdk / "java", "-version"])
        report["agent_sha256"] = digest(agent)
        report["class_sha256"] = digest(classes / (OWNER + ".class"))
        report["compatibility_rejections"] = scope_negatives(classes, out)
        rows = inputs(); input_file = out / "inputs.csv"
        input_file.write_text("".join(",".join(map(str, row)) + "\n" for row in rows))
        report["inputs"] = rows
        for method in ("max", "min"):
            expected = truth(method, rows); q = query(rows)
            scope = out / (method + ".properties")
            plan(classes, OWNER + "." + method + "(III)I", q, scope, snapshots=True)
            for jvm, flags in (("default", []), ("interpreter", ["-Xint"])):
                native = command([jdk / "java", *flags, "-Xverify:all", "-cp", cp, "upstream.CommonsDriver", method, input_file, "1"])
                save(out / f"{method}-{jvm}-native.json", native)
                if native["stdout"] != str(sum(v for v, _ in expected)) + "\n": raise AssertionError("native oracle mismatch")
                answers = {}
                for mode in MODES:
                    capture = out / f"{method}-{jvm}-{mode}"
                    run = command(collect_args(jdk, agent, cp, capture, mode, scope, "upstream.CommonsDriver", [method, input_file, "1"], flags))
                    if run["stdout"] != native["stdout"]: raise AssertionError("instrumentation changed output")
                    if digest(capture / (OWNER.replace("/", "_") + ".original.class")) != report["class_sha256"]:
                        raise AssertionError("upstream original class changed")
                    answer = infer(capture, q); check(answer, expected); answers[mode] = answer
                    save(capture / "query.json", q); save(capture / "inference.json", answer); save(capture / "run.json", run)
                    report["cases"].append(dict(method=method, jvm=jvm, mode=mode, capture=capture.name,
                         results=answer["results"], events=answer["observation"]["raw_events"], bytes=(capture / "events.jsonl").stat().st_size))
                for mode in MODES[1:]:
                    for key in ("results", "nodes", "branch_observations", "source_aliases"):
                        if answers[mode][key] != answers["full"][key]: raise AssertionError("cross-mode mismatch " + key)
        report["faults"] = faults(out / "max-default-boundary", query(rows), out / "faults")
        # Bypass the planner deliberately: the live collector must also reject
        # an unsupported *selected* overload even after method-scoped auditing.
        negative_scope = out / "unsupported-array.properties"
        text = (out / "max.properties").read_text().replace(".max(III)I", ".max([I)I")
        negative_scope.write_text(text)
        capture = out / "negative-array"
        command(collect_args(jdk, agent, cp, capture, "boundary", negative_scope, "upstream.CommonsDriver", ["array-max", input_file, "1"]))
        answer = infer(capture, query(rows)); save(capture / "inference.json", answer)
        if answer["status"] != "unknown": raise AssertionError("live unsupported overload accepted")
        report["runtime_rejection"] = answer
        # Fixed repeated max workload; all method invocations remain queries.
        repeated = rows * a.rounds; expected = truth("max", repeated); q = query(repeated)
        qfile = out / "cost-query.json"; save(qfile, q)
        scope = out / "cost.properties"; plan(classes, OWNER + ".max(III)I", q, scope, snapshots=True)
        supervisor = out / "measure-command"
        report["measurement_build"] = command(["cc", "-O2", "-Wall", "-Wextra", "-Werror", HERE / "measure_command.c", "-o", supervisor])
        rng = random.Random(a.seed)
        for block in range(-a.warmup, a.repeats):
            order = ["native", *MODES]; rng.shuffle(order)
            for index, mode in enumerate(order):
                dest = out / f"cost-{block}-{index}-{mode}"; capture = dest / "capture"
                args = ["max", input_file, str(a.rounds)]
                cmd = ([jdk / "java", "-Xverify:all", "-cp", cp, "upstream.CommonsDriver", *args] if mode == "native"
                       else collect_args(jdk, agent, cp, capture, mode, scope, "upstream.CommonsDriver", args))
                online = measured(cmd, dest / "online", supervisor)
                if (dest / "online/stdout.txt").read_text() != str(sum(v for v, _ in expected)) + "\n": raise AssertionError("cost checksum")
                offline, events, size = None, 0, 0
                if mode != "native":
                    offline = measured([sys.executable, HERE / "infer.py", capture, "--query", qfile, "--output", dest / "inference.json"], dest / "offline", supervisor)
                    answer = json.loads((dest / "inference.json").read_text()); check(answer, expected)
                    events = answer["observation"]["raw_events"]; size = (capture / "events.jsonl").stat().st_size
                report["measurements"].append(dict(block=block, warmup=block < 0, order=order, position=index, mode=mode,
                     directory=dest.name, online=online, offline=offline, events=events, trace_bytes=size,
                     end_to_end_wall_seconds=online["wall_seconds"] + (offline["wall_seconds"] if offline else 0),
                     end_to_end_cpu_seconds=online["cpu_seconds"] + (offline["cpu_seconds"] if offline else 0)))
                save(out / "validation.json", report)
        report["summary"] = summarize(report)
        report["qualification"]["memory_measurement_qualified"] = all(s["rss_above_supervisor_floor"] for r in report["measurements"] for s in (r["online"], r["offline"]) if s)
        report["status"] = "pass"
    except Exception as e:
        report.update(status="failed", error=repr(e)); raise
    finally:
        report["source_sha256"] = {str(f.relative_to(HERE)): digest(f) for f in sorted(HERE.rglob("*")) if f.is_file() and f.suffix in (".py", ".java", ".c")}
        shutil.copytree(HERE, out / "source", ignore=shutil.ignore_patterns("__pycache__"))
        report["evidence_files"] = {str(f.relative_to(out)): digest(f) for f in sorted(out.rglob("*")) if f.is_file() and f.name != "validation.json"}
        save(out / "validation.json", report)
        print(json.dumps(dict(status=report["status"], directory=str(out), summary=report.get("summary")), indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jdk", type=Path, required=True)
    p.add_argument("--rounds", type=int, default=10, help="repetitions of 35 triples per cost command")
    p.add_argument("--repeats", type=int, default=6)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--seed", type=int, default=20261010)
    a = p.parse_args()
    if a.rounds < 1 or a.repeats < 1 or a.warmup < 0: p.error("invalid experiment counts")
    main(a)
