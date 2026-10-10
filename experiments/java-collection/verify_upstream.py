#!/usr/bin/env python3
"""Recheck immutable upstream evidence and inference without rerunning business code."""
import argparse
import json
from pathlib import Path
import random

from compare_observations import save, summarize
from compare_upstream import JARS, MODES, OWNER, check, inputs, query, truth
from infer import infer
from run import HERE, digest


def verify(out):
    out = out.resolve()
    report = json.loads((out / "validation.json").read_text())
    assert report["status"] == "pass" and report["modes"] == MODES
    for name, sha in report["evidence_files"].items():
        path = (out / name).resolve()
        assert path.is_relative_to(out) and digest(path) == sha, name
    for name, sha in report["source_sha256"].items():
        assert digest(out / "source" / name) == sha, name
        assert digest(HERE / name) == sha, "inference/runner source changed: " + name
    for name, sha in JARS.items(): assert digest(out / name) == sha
    import zipfile
    with zipfile.ZipFile(out / "commons-lang3-3.17.0.jar") as z:
        assert z.read(OWNER + ".class") == (out / "upstream-original" / (OWNER + ".class")).read_bytes()
    assert report["inputs"] == [list(x) for x in inputs()]
    assert len(report["cases"]) == 12
    groups, seen, queries, raw_events = {}, set(), 0, 0
    for c in report["cases"]:
        key = (c["method"], c["jvm"], c["mode"])
        assert key not in seen; seen.add(key)
        capture = out / c["capture"]
        q = query(inputs()); assert json.loads((capture / "query.json").read_text()) == q
        answer = infer(capture, q); check(answer, truth(c["method"], inputs()))
        assert answer == json.loads((capture / "inference.json").read_text())
        assert answer["results"] == c["results"]
        assert digest(capture / (OWNER.replace("/", "_") + ".original.class")) == report["class_sha256"]
        assert c["events"] == answer["observation"]["raw_events"]
        assert c["bytes"] == (capture / "events.jsonl").stat().st_size
        groups.setdefault((c["method"], c["jvm"]), {})[c["mode"]] = answer
        queries += len(answer["results"]); raw_events += c["events"]
    assert seen == {(m, j, mode) for m in ("max", "min") for j in ("default", "interpreter") for mode in MODES}
    for answers in groups.values():
        for mode in MODES[1:]:
            for key in ("results", "nodes", "branch_observations", "source_aliases"):
                assert answers[mode][key] == answers["full"][key]
    repeated = inputs() * report["rounds"]
    q = query(repeated); assert json.loads((out / "cost-query.json").read_text()) == q
    rng, seen = random.Random(report["seed"]), set()
    for block in range(-report["warmup_blocks"], report["repetitions"]):
        order = ["native", *MODES]; rng.shuffle(order)
        for position, mode in enumerate(order):
            r = next(r for r in report["measurements"] if r["block"] == block and r["position"] == position)
            assert r["order"] == order and r["mode"] == mode and r["warmup"] == (block < 0)
            assert (block, mode) not in seen; seen.add((block, mode))
            dest = out / r["directory"]
            assert (dest / "online/stdout.txt").read_text() == str(sum(v for v, _ in truth("max", repeated))) + "\n"
            for name in ("online", "offline"):
                s = r[name]
                if s is None: continue
                assert json.loads((dest / name / "measurement.json").read_text()) == s
                user, system, rss, floor = (dest / name / "resource.txt").read_text().split()
                assert s["user_seconds"] == float(user) and s["system_seconds"] == float(system)
                assert s["cpu_seconds"] == float(user) + float(system)
                assert s["peak_rss_kib"] == int(rss) and s["supervisor_rss_kib"] == int(floor)
            assert r["end_to_end_wall_seconds"] == r["online"]["wall_seconds"] + (r["offline"]["wall_seconds"] if r["offline"] else 0)
            assert r["end_to_end_cpu_seconds"] == r["online"]["cpu_seconds"] + (r["offline"]["cpu_seconds"] if r["offline"] else 0)
            if mode == "native": assert r["offline"] is None and r["events"] == r["trace_bytes"] == 0
            else:
                capture = dest / "capture"; answer = infer(capture, q); check(answer, truth("max", repeated))
                assert answer == json.loads((dest / "inference.json").read_text())
                assert digest(capture / (OWNER.replace("/", "_") + ".original.class")) == report["class_sha256"]
                assert r["events"] == answer["observation"]["raw_events"]
                assert r["trace_bytes"] == (capture / "events.jsonl").stat().st_size
                if mode == "boundary":
                    rows = [json.loads(x) for x in (capture / "events.jsonl").read_text().splitlines()]
                    assert all(x["kind"] in ("start", "class", "enter", "exit", "finish") for x in rows)
                    assert all("@" not in x["site"] for x in rows)
                raw_events += r["events"]
    assert len(report["measurements"]) == len(seen)
    for r in report["faults"]:
        answer = infer(out / "faults" / r["fault"], query(inputs()))
        assert answer["status"] == "unknown" and answer["reason"] == r["reason"] and not answer["results"]
    assert infer(out / "negative-array", query(inputs())) == report["runtime_rejection"]
    assert summarize(report) == report["summary"]
    return dict(status="pass", manifest_sha256=digest(out / "validation.json"),
                evidence_files=len(report["evidence_files"]), positive_jvm_captures=12,
                distinct_input_method_queries=70, queries_with_two_jvm_modes_and_three_methods=queries,
                cost_commands=len(seen), raw_events_reinferred=raw_events,
                offline_faults=4, actual_jvm_rejections=1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = verify(a.directory); save(a.output, result); print(json.dumps(result, indent=2))
