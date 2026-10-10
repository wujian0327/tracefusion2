#!/usr/bin/env python3
"""Score the new backend using existing real JVM captures; never rerun collection."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil

from infer import infer
from verify import verify_run

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPECTED = {"left": ([17], [["left.value"]]), "right": ([17], [["right.value"]]),
            "alias": ([17], [["left.value", "right.value"]]),
            "overwrite": ([17], [["right.value"]]), "nested": ([34], [["right.value"]]),
            "loop": ([68], [["left.value", "right.value"]]),
            "gc": ([17, 17], [["left.value"], ["right.value"]])}


def query(case):
    # Boundary declarations only. EXPECTED is not passed to the inference engine.
    sources = [dict(id=label + ".value", kind="initial_field", root=1, arg=i, field="demo/Cell.value:I")
               for i, label in enumerate(("left", "right"))]
    if case in ("left", "right", "alias", "nested", "loop", "gc"):
        sources.append(dict(id="selector" if case != "loop" else "count", kind="argument", root=1, arg=2))
    if case == "gc": sources.append(dict(id="selector.second", kind="argument", root=2, arg=2))
    return dict(schema="java-source-query-v1", sources=sources,
                targets=[dict(id="return" + str(i), root=i, kind="return") for i in range(1, 3 if case == "gc" else 2)])


def require_ok(value, message):
    if not value: raise AssertionError(message)


def check_faults(captures, output):
    names = ("same_value_receiver", "callee_argument", "plan_local_swap", "same_value_branch",
             "missing_source_field", "unobserved_target")
    result = []
    for name in names:
        case = "nested" if name == "callee_argument" else "right"
        target = output / name
        shutil.copytree(captures / ("default-" + case), target)
        rows = [json.loads(s) for s in (target / "events.jsonl").read_text().splitlines()]
        config = query(case)
        if name == "same_value_receiver":
            next(r for r in rows if r["kind"] == "read")["values"][0] = "o1"
        elif name == "callee_argument":
            next(r for r in rows if r["kind"] == "enter" and ".twice(" in r["site"])["values"][1] = 18
        elif name == "plan_local_swap":
            planfile = target / "demo_Subject.plan.jsonl"
            plans = [json.loads(s) for s in planfile.read_text().splitlines()]
            next(p for p in plans if ".choose(" in p["site"] and p["pc"] == 5)["operands"] = [0]
            planfile.write_text("".join(json.dumps(p) + "\n" for p in plans))
        elif name == "same_value_branch":
            for r in rows:
                if r["kind"] == "branch": r["values"] = [0]
                if r["kind"] == "read": r["values"][0] = "o1"
                if "@" in r["site"]:
                    method, pc = r["site"].rsplit("@", 1)
                    if int(pc) >= 5: r["site"] = method + "@" + str(int(pc) - 3)
        elif name == "missing_source_field": config["sources"][0]["field"] = "demo/Cell.missing:I"
        elif name == "unobserved_target": config["targets"][0]["root"] = 99
        (target / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (target / "query.json").write_text(json.dumps(config, indent=2) + "\n")
        answer = infer(target, config)
        (target / "inference.json").write_text(json.dumps(answer, indent=2) + "\n")
        require_ok(answer["status"] == "unknown" and not answer["results"], "accepted inference fault " + name)
        result.append(dict(fault=name, rejected=True, reason=answer["reason"]))
    return result


def evaluate(captures, output):
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema="java-inference-validation-v1", status="running", cases=[])
    try:
        report["collection_reverification"] = verify_run(captures)
        report["capture_manifest_sha256"] = hashlib.sha256((captures / "validation.json").read_bytes()).hexdigest()
        tp = fp = fn = correct = total = 0
        for mode in ("default", "interpreter"):
            for case, (values, sources) in EXPECTED.items():
                directory = output / (mode + "-" + case)
                directory.mkdir()
                config = query(case)
                (directory / "query.json").write_text(json.dumps(config, indent=2) + "\n")
                answer = infer(captures / (mode + "-" + case), config)
                (directory / "inference.json").write_text(json.dumps(answer, indent=2) + "\n")
                require_ok(answer["status"] == "ok", str(answer))
                actual = answer["results"]
                require_ok(len(actual) == len(values), "result count")
                for a, value, labels in zip(actual, values, sources):
                    require_ok(a["status"] == "ok" and a["value"] == value, "return mismatch")
                    found, expected = set(a["direct_sources"]), set(labels)
                    tp += len(found & expected); fp += len(found - expected); fn += len(expected - found)
                    correct += found == expected; total += 1
                require_ok(answer["source_aliases"] == ([["left.value", "right.value"]] if case == "alias" else []), "source alias mismatch")
                controls = set().union(*(set(b["predicate_sources"]) for b in answer["branch_observations"]))
                expected_controls = {"selector", "selector.second"} if case == "gc" else {"count"} if case == "loop" else set() if case == "overwrite" else {"selector"}
                require_ok(controls == expected_controls, "branch predicate sources mismatch")
                report["cases"].append(dict(mode=mode, case=case, results=actual, source_aliases=answer["source_aliases"],
                                             branch_predicate_sources=sorted(controls), graph_nodes=len(answer["nodes"])))
        report.update(correct_queries=correct, total_queries=total, TP=tp, FP=fp, FN=fn)
        report["physical_origin_relationships"] = sum(len(a["direct_origins"]) for c in report["cases"] for a in c["results"])
        require_ok(correct == total and fp == fn == 0, "source mismatch")
        rejected = []
        for directory in sorted(captures.glob("negative-*")) + sorted((captures / "faults").iterdir()):
            answer = infer(directory, query("overwrite"))
            require_ok(answer["status"] == "unknown", "old bad evidence accepted")
            rejected.append(dict(case=directory.name, reason=answer["reason"]))
        report["existing_bad_capture_rejections"] = rejected
        report["new_fault_checks"] = check_faults(captures, output / "faults")
        report["source_sha256"] = {str(f.relative_to(HERE)): hashlib.sha256(f.read_bytes()).hexdigest()
                                   for f in sorted(HERE.rglob("*")) if f.is_file() and f.suffix in (".py", ".java")}
        report["qualification"] = dict(real_JVM_capture=True, new_JVM_execution=False, independent_class_decoder=True,
                                        fixture_oracle_used_by_inference=False, selective_capture=False,
                                        external_tool_comparison=False, performance_eligible=False,
                                        minimal_semantic_dependency_claim=False)
        report["status"] = "pass"
    except Exception as e:
        report["status"], report["error"] = "failed", repr(e)
        raise
    finally:
        (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("captures", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    output = args.output or ROOT / "artifacts" / ("java-inference-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    report = evaluate(args.captures.resolve(), output.resolve())
    print(json.dumps({k: report[k] for k in ("status", "correct_queries", "total_queries", "TP", "FP", "FN")}, indent=2))
    print("Results:", output.resolve())
