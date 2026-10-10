#!/usr/bin/env python3
"""Real JVM full-step vs sparse observation experiment, with whole-command costs.

Build/plan creation are outside timing. All captures and inferred graphs retained.
Warmup blocks are separate processes and NOT claimed to warm measured JVMs/JITs.
"""
import argparse
import datetime
import hashlib
import json
import os
import platform
from pathlib import Path
import random
import shutil
import signal
import statistics
import subprocess
import sys
import time
import threading

from check_inference import EXPECTED, query
from infer import infer
from observation import plan
from run import build, command, digest, HERE, ROOT


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def entry(case):
    name = {"overwrite": "overwrite", "nested": "nested", "loop": "sum"}.get(case, "choose")
    return "demo/Subject." + name + "(Ldemo/Cell;Ldemo/Cell;" + ("" if case == "overwrite" else "I") + ")I"


def collect_args(jdk, agent, fixture, capture, mode, scope, main, args, flags=()):
    return [jdk / "java", *flags, "-Xverify:all", f"-javaagent:{agent}",
            f"-Dtracefusion.output={capture}", f"-Dtracefusion.mode={mode}",
            f"-Dtracefusion.scope={scope}", "-Dtracefusion.maxEvents=2000000",
            "-cp", fixture, main, *args]


def faults(capture, config, directory):
    results = []
    original = [json.loads(x) for x in (capture / "events.jsonl").read_text().splitlines()]
    for name in ("missing_read", "missing_branch", "missing_exit", "missing_footer", "same_value_receiver",
                 "branch_direction", "extra_step", "scope_hash", "original_class", "query_binding"):
        dest = directory / name
        shutil.copytree(capture, dest)
        rows = json.loads(json.dumps(original)); q = json.loads(json.dumps(config))
        if name.startswith("missing_"):
            kind = {"missing_footer": "finish"}.get(name, name.removeprefix("missing_"))
            rows.pop(next(i for i, r in enumerate(rows) if r["kind"] == kind))
            for i, r in enumerate(rows, 1): r["seq"] = i
        elif name == "same_value_receiver": next(r for r in rows if r["kind"] == "read")["values"][0] = "o1"
        elif name == "branch_direction": next(r for r in rows if r["kind"] == "branch")["values"][0] ^= 1
        elif name == "extra_step": next(r for r in rows if r["kind"] == "read")["kind"] = "step"
        elif name == "scope_hash":
            with (dest / "observation.properties").open("a") as f: f.write("tamper=yes\n")
        elif name == "original_class":
            f = dest / "demo_Subject.original.class"; f.write_bytes(f.read_bytes() + b"x")
        elif name == "query_binding": q["targets"][0]["root"] = 2
        (dest / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        answer = infer(dest, q); save(dest / "inference.json", answer)
        if answer["status"] != "unknown" or answer["results"]: raise AssertionError("accepted fault " + name)
        results.append(dict(fault=name, rejected=True, reason=answer["reason"]))
    return results


def measured(cmd, dest, supervisor):
    dest.mkdir(parents=True)
    metric = dest / "resource.txt"
    argv = [str(supervisor), str(metric), *map(str, cmd)]
    begin = time.perf_counter()
    with (dest / "stdout.txt").open("w") as out, (dest / "stderr.txt").open("w") as err:
        result = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True)
        expired = threading.Event()
        def expire():
            expired.set()
            try: os.killpg(result.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        timer = threading.Timer(180, expire); timer.daemon = True; timer.start()
        try: result.wait()  # Blocking wait, not Popen.wait(timeout)'s coarse polling.
        finally: timer.cancel()
        if expired.is_set(): raise subprocess.TimeoutExpired(argv, 180)
    wall = time.perf_counter() - begin
    if result.returncode: raise RuntimeError(f"command failed: {argv}; see {dest}")
    user, system, rss, floor = metric.read_text().split()
    record = dict(command=list(map(str, cmd)), wall_seconds=wall, user_seconds=float(user),
                  system_seconds=float(system), cpu_seconds=float(user) + float(system), peak_rss_kib=int(rss),
                  supervisor_rss_kib=int(floor), rss_above_supervisor_floor=int(floor) > 0 and int(rss) > 2 * int(floor))
    save(dest / "measurement.json", record)
    return record


def main(a):
    jdk = (a.jdk.resolve() / "bin") if a.jdk else Path(shutil.which("javac") or "missing").resolve().parent
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    out = ROOT / "artifacts" / ("java-observation-" + stamp); out.mkdir(parents=True)
    report = dict(schema="java-observation-comparison-v1", status="running", cases=[], measurements=[],
                  qualification=dict(query_scope="entry static-call closure, not field-level slicing",
                     retained="all field/branch/call/return observations", global_optimality=False,
                     real_application=False, external_tool_comparison=False, steady_state=False),
                  java=command([jdk / "java", "-version"]), platform=platform.uname()._asdict(),
                  rounds=a.rounds, repetitions=a.repeats, warmup_blocks=a.warmup, seed=a.seed)
    try:
        if a.reuse_correctness:
            prior = a.reuse_correctness.resolve()
            old = json.loads((prior / "validation.json").read_text())
            if len(old["cases"]) != 28 or len(old["faults"]) != 12: raise ValueError("incomplete correctness evidence")
            for name, sha in old["evidence_files"].items():
                path = (prior / name).resolve()
                if not path.is_relative_to(prior) or digest(path) != sha: raise ValueError("changed prior evidence: " + name)
            for name in ("observation.py", "infer.py", "verify.py", "src/tracefusion/Agent.java", "src/tracefusion/Recorder.java"):
                if digest(HERE / name) != old["source_sha256"][name]: raise ValueError("correctness code changed: " + name)
            for name in ("fixture-classes", "agent-classes", "source", "faults"):
                shutil.copytree(prior / name, out / ("correctness-source" if name == "source" else name))
            for path in prior.iterdir():
                if path.is_dir() and path.name.startswith(("default-", "interpreter-", "negative-")):
                    shutil.copytree(path, out / path.name)
            agent, fixture = out / "tracefusion-java-agent.jar", out / "fixture-classes"
            shutil.copyfile(prior / agent.name, agent)
            if digest(agent) != old["agent_sha256"]: raise ValueError("correctness agent changed")
            report.update(cases=old["cases"], faults=old["faults"], build=old["build"],
                          correctness_reused_from=prior.name, correctness_manifest_sha256=digest(prior / "validation.json"))
        else:
            agent, fixture, report["build"] = build(jdk, out)
        report["agent_sha256"] = digest(agent)
        for jvm in (() if a.reuse_correctness else ("default", "interpreter")):
            flags = [] if jvm == "default" else ["-Xint"]
            for case, (values, labels) in EXPECTED.items():
                q = query(case); scope = out / (case + ".properties")
                plan(fixture, entry(case), q, scope)
                answers = {}
                for mode in ("full", "sparse"):
                    capture = out / f"{jvm}-{case}-{mode}"
                    observed = command(collect_args(jdk, agent, fixture, capture, mode, scope,
                                                    "demo.Driver", [case], flags))
                    answer = infer(capture, q)
                    save(capture / "query.json", q); save(capture / "inference.json", answer)
                    save(capture / "run.json", observed)
                    if answer["status"] != "ok": raise AssertionError(str(answer))
                    if [(r["value"], r["direct_sources"]) for r in answer["results"]] != list(zip(values, labels)):
                        raise AssertionError("incorrect sources " + case)
                    if observed["stdout"] != str(values[-1]) + "\n": raise AssertionError("business result changed")
                    answers[mode] = answer
                    raw = capture / "events.jsonl"
                    report["cases"].append(dict(jvm=jvm, case=case, mode=mode, results=answer["results"],
                         events=answer["observation"]["raw_events"], derived_steps=answer["observation"]["derived_steps"],
                         bytes=raw.stat().st_size, graph_nodes=len(answer["nodes"])))
                # Complete graph and control predicates must remain identical, not only final values.
                for key in ("results", "nodes", "branch_observations", "source_aliases"):
                    if answers["full"][key] != answers["sparse"][key]: raise AssertionError("mode mismatch " + key)
        if not a.reuse_correctness:
            report["faults"] = faults(out / "default-right-sparse", query("right"), out / "faults")
        for case in (() if a.reuse_correctness else ("null", "threads")):
            capture = out / ("negative-" + case)
            command(collect_args(jdk, agent, fixture, capture, "sparse", out / "right.properties", "demo.Driver", [case]))
            answer = infer(capture, query("right")); save(capture / "inference.json", answer)
            if answer["status"] != "unknown": raise AssertionError("negative accepted " + case)
            report["faults"].append(dict(fault=case, rejected=True, reason=answer["reason"]))
        # Repeated original loop path, fixed load, independent root-return oracle.
        q = query("loop")
        if a.rounds > 1: q["targets"].append(dict(id="last", root=a.rounds, kind="return"))
        scope = out / "benchmark.properties"; plan(fixture, entry("loop"), q, scope)
        qfile = out / "benchmark-query.json"; save(qfile, q)
        supervisor = out / "measure-command"
        report["measurement_build"] = command(["cc", "-O2", "-Wall", "-Wextra", "-Werror", HERE / "measure_command.c", "-o", supervisor])
        rng = random.Random(a.seed)
        for block in range(-a.warmup, a.repeats):
            order = ["native", "full", "sparse"]; rng.shuffle(order)
            for index, mode in enumerate(order):
                dest = out / f"cost-{block}-{index}-{mode}"
                capture = dest / "capture"
                cmd = ([jdk / "java", "-Xverify:all", "-cp", fixture, "demo.Bench", str(a.rounds)] if mode == "native"
                       else collect_args(jdk, agent, fixture, capture, mode, scope, "demo.Bench", [str(a.rounds)]))
                online = measured(cmd, dest / "online", supervisor)
                if (dest / "online/stdout.txt").read_text() != str(68 * a.rounds) + "\n": raise AssertionError("checksum")
                offline, events, size = None, 0, 0
                if mode != "native":
                    offline = measured([sys.executable, HERE / "infer.py", capture, "--query", qfile,
                                         "--output", dest / "inference.json"], dest / "offline", supervisor)
                    answer = json.loads((dest / "inference.json").read_text())
                    if answer["status"] != "ok" or any(r["value"] != 68 or r["direct_sources"] != ["left.value", "right.value"]
                                                      for r in answer["results"]): raise AssertionError("cost run provenance")
                    events = answer["observation"]["raw_events"]; size = (capture / "events.jsonl").stat().st_size
                report["measurements"].append(dict(block=block, warmup=block < 0, order=order, position=index,
                        mode=mode, online=online, offline=offline, events=events, trace_bytes=size,
                        end_to_end_wall_seconds=online["wall_seconds"] + (offline["wall_seconds"] if offline else 0),
                        end_to_end_cpu_seconds=online["cpu_seconds"] + (offline["cpu_seconds"] if offline else 0)))
                save(out / "validation.json", report)
        report["summary"] = summarize(report)
        report["qualification"]["memory_measurement_qualified"] = all(
            stage["rss_above_supervisor_floor"] for r in report["measurements"]
            for stage in (r["online"], r["offline"]) if stage is not None)
        report["status"] = "pass"
    except Exception as e:
        report.update(status="failed", error=repr(e)); raise
    finally:
        report["source_sha256"] = {str(f.relative_to(HERE)): digest(f) for f in sorted(HERE.rglob("*"))
                                    if f.is_file() and f.suffix in (".java", ".py", ".c")}
        save(out / "validation.json", report)
        shutil.copytree(HERE, out / "source", ignore=shutil.ignore_patterns("__pycache__"))
        report["evidence_files"] = {str(f.relative_to(out)): digest(f) for f in sorted(out.rglob("*"))
                                   if f.is_file() and f.name != "validation.json"}
        save(out / "validation.json", report)
        print(json.dumps({"status": report["status"], "directory": str(out), "summary": report.get("summary")}, indent=2))


def summarize(report):
    result = {"correct_queries_per_mode": sum(len(c["results"]) for c in report["cases"] if c["mode"] == "full"),
              "raw_events": {m: sum(c["events"] for c in report["cases"] if c["mode"] == m) for m in ("full", "sparse")},
              "cost_medians": {}, "paired_reduction": {}}
    rows = [r for r in report["measurements"] if not r["warmup"]]
    def value(r, key):
        if key.startswith("online_"): return r["online"][key[7:]]
        if key.startswith("offline_"): return r["offline"][key[8:]] if r["offline"] else 0
        return r[key]
    keys = ("online_wall_seconds", "online_cpu_seconds", "online_peak_rss_kib", "offline_wall_seconds",
            "offline_cpu_seconds", "offline_peak_rss_kib", "end_to_end_wall_seconds", "end_to_end_cpu_seconds", "events", "trace_bytes")
    for mode in ("native", "full", "sparse"):
        group = [r for r in rows if r["mode"] == mode]
        result["cost_medians"][mode] = {k: statistics.median(value(r, k) for r in group) for k in keys} if group else {}
    for key in keys:
        if "rss" in key and not all(stage["rss_above_supervisor_floor"] for r in rows
                                     for stage in (r["online"], r["offline"]) if stage is not None):
            result["paired_reduction"][key] = {"qualified": False, "reason": "supervisor RSS floor unverified"}
            continue
        ratios = []
        for block in range(report["repetitions"]):
            pair = {r["mode"]: r for r in rows if r["block"] == block}
            base = value(pair["full"], key)
            ratios.append(1 - value(pair["sparse"], key) / base if base else 0)
        result["paired_reduction"][key] = dict(median=statistics.median(ratios), minimum=min(ratios), maximum=max(ratios),
                                               sparse_worse=sum(x < 0 for x in ratios)) if ratios else {}
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jdk", type=Path)
    p.add_argument("--rounds", type=int, default=200)
    p.add_argument("--repeats", type=int, default=6)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--seed", type=int, default=20261010)
    p.add_argument("--reuse-correctness", type=Path, help="reuse completed comparison captures with unchanged collector/inference sources")
    a = p.parse_args()
    if not 1 <= a.rounds <= 2000 or not 0 <= a.repeats <= 100 or not 0 <= a.warmup <= 10: p.error("bounded experiment sizes required")
    main(a)
