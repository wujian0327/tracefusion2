#!/usr/bin/env python3
"""Recheck saved comparison evidence without executing another JVM workload."""
import argparse
import json
from pathlib import Path
import shutil

from check_inference import EXPECTED, query
from compare_observations import digest, summarize, save
from infer import infer


def require(ok, why):
    if not ok: raise ValueError(why)


def additional_faults(directory, output):
    output.mkdir(parents=True, exist_ok=False)
    report = []
    for name, case, kind in (("missing_write", "overwrite", "write"),
                              ("bad_write_version", "overwrite", "write"),
                              ("missing_call", "nested", "call"),
                              ("missing_call_return", "nested", "call_return"),
                              ("missing_callee_entry", "nested", "enter"),
                              ("bad_callee_argument", "nested", "enter")):
        dest = output / name
        shutil.copytree(directory / f"default-{case}-sparse", dest)
        rows = [json.loads(s) for s in (dest / "events.jsonl").read_text().splitlines()]
        if name == "bad_callee_argument":
            next(r for r in rows if r["kind"] == "enter" and ".twice(" in r["site"])["values"][1] += 1
        elif name == "bad_write_version": next(r for r in rows if r["kind"] == kind)["values"][3] += 1
        else:
            rows.pop(next(i for i, r in enumerate(rows) if r["kind"] == kind
                          and (kind != "enter" or r["values"][0] != 0)))
            for i, r in enumerate(rows, 1): r["seq"] = i
        (dest / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        answer = infer(dest, query(case)); save(dest / "inference.json", answer)
        require(answer["status"] == "unknown" and not answer["results"], "accepted new fault " + name)
        report.append(dict(fault=name, reason=answer["reason"], rejected=True))
    return report


def verify(directory, output):
    directory = directory.resolve()
    manifest = json.loads((directory / "validation.json").read_text())
    require(manifest["status"] == "pass", "incomplete comparison")
    for name, sha in manifest["evidence_files"].items():
        path = (directory / name).resolve()
        require(path.is_relative_to(directory) and digest(path) == sha, "evidence hash: " + name)
    for name, sha in manifest["source_sha256"].items():
        require(digest(directory / "source" / name) == sha, "source snapshot: " + name)
    require(digest(directory / "tracefusion-java-agent.jar") == manifest["agent_sha256"], "agent hash")
    seen, answers, counts = set(), {}, {"full": 0, "sparse": 0}
    for c in manifest["cases"]:
        key = (c["jvm"], c["case"], c["mode"])
        require(key not in seen, "duplicate case"); seen.add(key)
        capture = directory / "-".join(key)
        q = query(c["case"])
        answer = infer(capture, q)
        require(answer == json.loads((capture / "inference.json").read_text()), "saved inference differs")
        values, sources = EXPECTED[c["case"]]
        require(answer["status"] == "ok" and [(r["value"], r["direct_sources"]) for r in answer["results"]]
                == list(zip(values, sources)), "source truth mismatch")
        require(c["results"] == answer["results"] and c["events"] == answer["observation"]["raw_events"]
                and c["derived_steps"] == answer["observation"]["derived_steps"]
                and c["graph_nodes"] == len(answer["nodes"])
                and c["bytes"] == (capture / "events.jsonl").stat().st_size, "saved counts differ")
        answers[key] = answer; counts[c["mode"]] += len(answer["results"])
    require(seen == {(j, c, m) for j in ("default", "interpreter") for c in EXPECTED for m in ("full", "sparse")}, "case coverage")
    for j in ("default", "interpreter"):
        for c in EXPECTED:
            for k in ("results", "nodes", "branch_observations", "source_aliases"):
                require(answers[j, c, "full"][k] == answers[j, c, "sparse"][k], "full/sparse graph mismatch")
    bench_query = json.loads((directory / "benchmark-query.json").read_text())
    measured_queries, order = 0, set()
    for r in manifest["measurements"]:
        key = (r["block"], r["mode"])
        require(key not in order, "duplicate measurement"); order.add(key)
        require(r["warmup"] == (r["block"] < 0) and r["order"][r["position"]] == r["mode"]
                and set(r["order"]) == {"native", "full", "sparse"}, "measurement order")
        dest = directory / f'cost-{r["block"]}-{r["position"]}-{r["mode"]}'
        for stage in ("online", "offline"):
            if r[stage] is None: continue
            require(r[stage] == json.loads((dest / stage / "measurement.json").read_text()), "raw measurement differs")
            user, system, rss, floor = map(float, (dest / stage / "resource.txt").read_text().split())
            require((user, system, rss, floor) == (r[stage]["user_seconds"], r[stage]["system_seconds"],
                                                  r[stage]["peak_rss_kib"], r[stage]["supervisor_rss_kib"]), "resource metrics")
        require(r["end_to_end_wall_seconds"] == r["online"]["wall_seconds"] + (r["offline"]["wall_seconds"] if r["offline"] else 0), "end-to-end time")
        require((dest / "online/stdout.txt").read_text() == str(68 * manifest["rounds"]) + "\n", "benchmark output")
        if r["mode"] != "native":
            answer = infer(dest / "capture", bench_query)
            require(answer == json.loads((dest / "inference.json").read_text()), "benchmark saved inference differs")
            require(answer["status"] == "ok" and all(v["value"] == 68 and v["direct_sources"] == ["left.value", "right.value"]
                                                      for v in answer["results"]), "benchmark sources")
            require(r["events"] == answer["observation"]["raw_events"] and r["trace_bytes"] == (dest / "capture/events.jsonl").stat().st_size,
                    "benchmark event/byte count")
            measured_queries += len(answer["results"])
    require(order == {(b, m) for b in range(-manifest["warmup_blocks"], manifest["repetitions"])
                      for m in ("native", "full", "sparse")}, "cost coverage")
    require(summarize(manifest) == manifest["summary"], "cost summary differs")
    for f in manifest["faults"]:
        q = query("right")
        if f["fault"] == "query_binding": q["targets"][0]["root"] = 2
        dest = directory / (("negative-" + f["fault"]) if f["fault"] in ("null", "threads") else "faults/" + f["fault"])
        answer = infer(dest, q)
        require(answer["status"] == "unknown" and not answer["results"], "old fault accepted")
    new_faults = additional_faults(directory, output / "additional-faults")
    report = dict(status="pass", new_JVM_execution=False, correct_queries=counts,
                  benchmark_queries_including_warmup=measured_queries, raw_manifest_sha256=digest(directory / "validation.json"),
                  existing_rejections=len(manifest["faults"]), additional_rejections=new_faults,
                  evidence_files_checked=len(manifest["evidence_files"]), summary=manifest["summary"])
    save(output / "verification.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(verify(a.directory, a.output), indent=2))
