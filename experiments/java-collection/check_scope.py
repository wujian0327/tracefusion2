#!/usr/bin/env python3
"""Focused regression for changed method-scoped auditing, reusing the built agent."""
import argparse
import json
from pathlib import Path
import shutil

from check_inference import query
from compare_observations import collect_args, entry, save
from infer import infer
from observation import decoded_scope, plan
from run import HERE, command, digest


def main(a):
    source = a.evidence.resolve(); out = a.output.resolve(); out.mkdir(parents=True)
    recorded = json.loads((source / "validation.json").read_text())
    for name in ("classfile.py", "observation.py", "infer.py", "src/tracefusion/Agent.java"):
        assert digest(HERE / name) == recorded["source_sha256"][name]
    agent, classes = source / "tracefusion-java-agent.jar", source / "fixture-classes"
    assert digest(agent) == recorded["agent_sha256"]
    q = query("nested"); scope = out / "nested.properties"
    props = plan(classes, entry("nested"), q, scope, snapshots=True)
    answers = {}
    for mode in ("full", "sparse", "boundary"):
        capture = out / mode
        observed = command(collect_args(a.jdk.resolve() / "bin", agent, classes, capture, mode, scope, "demo.Driver", ["nested"]))
        answer = infer(capture, q); save(capture / "query.json", q); save(capture / "inference.json", answer)
        assert observed["stdout"] == "34\n" and answer["status"] == "ok"
        assert answer["results"][0]["direct_sources"] == ["right.value"]
        answers[mode] = answer
    for mode in ("sparse", "boundary"):
        for key in ("results", "nodes", "branch_observations"):
            assert answers[mode][key] == answers["full"][key]
    # A reachable callee cannot be omitted simply by editing the manifest.
    selected = [props["method." + str(i)] for i in range(int(props["method.count"]))]
    selected = [m for m in selected if ".twice(" not in m]
    props = {k: v for k, v in props.items() if not k.startswith("method.")}
    props["method.count"] = str(len(selected)); props.update({f"method.{i}": m for i, m in enumerate(selected)})
    try: decoded_scope(out / "full", props)
    except ValueError as e: offline_reason = str(e)
    else: raise AssertionError("omitted reachable callee decoded")
    omitted = out / "omitted.properties"
    omitted.write_text("".join(k + "=" + v + "\n" for k, v in props.items()))
    capture = out / "omitted-callee"
    run = command(collect_args(a.jdk.resolve() / "bin", agent, classes, capture, "boundary", omitted, "demo.Driver", ["nested"]))
    answer = infer(capture, q); save(capture / "inference.json", answer)
    assert run["stdout"] == "34\n" and answer["status"] == "unknown"
    result = dict(status="pass", agent_sha256=digest(agent), positive_captures=3,
                  offline_missing_callee=offline_reason, actual_jvm_missing_callee=answer,
                  evidence_files={str(f.relative_to(out)): digest(f) for f in sorted(out.rglob("*")) if f.is_file()})
    save(out / "validation.json", result); print(json.dumps({k: v for k, v in result.items() if k != "evidence_files"}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--jdk", type=Path, required=True)
    main(p.parse_args())
