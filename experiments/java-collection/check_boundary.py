"""Boundary evidence fault checks. No truth or mutation code imported by replay."""
import json
from pathlib import Path
import shutil
from infer import infer
from check_inference import query


def runtime_checks(jdk, agent, fixture, scope, output):
    from run import command
    results = []
    for case in ("null", "threads"):
        capture = output / ("runtime_" + case)
        run = command([jdk / "java", "-Xverify:all", f"-javaagent:{agent}",
                       f"-Dtracefusion.output={capture}", "-Dtracefusion.mode=boundary",
                       f"-Dtracefusion.scope={scope}", "-cp", fixture, "demo.Driver", case])
        expected = "caught-null\n" if case == "null" else "17\n"
        if run["stdout"] != expected: raise AssertionError("boundary probes changed negative-case output")
        config = query("right"); answer = infer(capture, config)
        if answer["status"] != "unknown" or answer["results"]: raise AssertionError("boundary runtime rejection " + case)
        for name, data in (("run.json", run), ("query.json", config), ("inference.json", answer)):
            (capture / name).write_text(json.dumps(data, indent=2) + "\n")
        results.append(dict(case="runtime_" + case, expected="unknown", passed=True, reason=answer["reason"]))
    return results


def fault_checks(captures, output):
    output.mkdir(parents=True, exist_ok=False)
    report = []
    for name in ("missing_snapshot", "missing_entry", "missing_exit", "missing_footer", "duplicate_snapshot",
                 "snapshot_identity", "snapshot_value", "return_value", "extra_internal_event", "alias_disagreement",
                 "later_snapshot_mutation", "query_binding", "plan_tamper", "scope_hash", "same_value_selector_change"):
        case = "alias" if name == "alias_disagreement" else "gc" if name == "later_snapshot_mutation" else "right"
        dest = output / name
        shutil.copytree(Path(captures) / f"default-{case}-boundary", dest)
        rows = [json.loads(s) for s in (dest / "events.jsonl").read_text().splitlines()]
        config = query(case)
        if name.startswith("missing_"):
            kind = {"missing_entry": "enter", "missing_footer": "finish"}.get(name, name[8:])
            rows.pop(next(i for i, r in enumerate(rows) if r["kind"] == kind))
        elif name == "duplicate_snapshot": rows.insert(4, next(r for r in rows if r["kind"] == "snapshot").copy())
        elif name == "snapshot_identity": next(r for r in rows if r["kind"] == "snapshot")["values"][1] = "o999"
        elif name == "snapshot_value": [r for r in rows if r["kind"] == "snapshot"][1]["values"][3] += 1
        elif name == "alias_disagreement": [r for r in rows if r["kind"] == "snapshot"][1]["values"][3] += 1
        elif name == "later_snapshot_mutation": [r for r in rows if r["kind"] == "snapshot"][-1]["values"][3] += 1
        elif name == "return_value": next(r for r in rows if r["kind"] == "exit")["values"][0] += 1
        elif name == "extra_internal_event": rows.insert(5, dict(rows[4], kind="branch", values=[1]))
        elif name == "query_binding": config["targets"][0]["root"] = 2
        elif name == "plan_tamper":
            f = dest / "demo_Subject.plan.jsonl"
            plans = [json.loads(s) for s in f.read_text().splitlines()]
            plans[0]["operands"] = [99]
            f.write_text("".join(json.dumps(p) + "\n" for p in plans))
        elif name == "scope_hash":
            with (dest / "observation.properties").open("a") as f: f.write("changed=true\n")
        elif name == "same_value_selector_change":
            # A coherent alternative execution is NOT detectable corruption.
            # Equal output, but changed selector must change the inferred origin.
            next(r for r in rows if r["kind"] == "enter")["values"][-1] = 1
        for i, r in enumerate(rows, 1): r["seq"] = i
        (dest / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (dest / "query.json").write_text(json.dumps(config, indent=2) + "\n")
        answer = infer(dest, config)
        (dest / "inference.json").write_text(json.dumps(answer, indent=2) + "\n")
        if name == "same_value_selector_change":
            if answer["status"] != "ok" or answer["results"][0]["direct_sources"] != ["left.value"]:
                raise AssertionError("boundary replay guessed origin from equal output")
            report.append(dict(case=name, expected="ok_different_origin", passed=True))
        else:
            if answer["status"] != "unknown" or answer["results"]: raise AssertionError("accepted boundary fault " + name)
            report.append(dict(case=name, expected="unknown", passed=True, reason=answer["reason"]))
    return report
