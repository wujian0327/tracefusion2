#!/usr/bin/env python3
"""Calibrate replay arithmetic against a real JVM, separate from provenance fixtures."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

from infer import infer
from run import command, HERE, ROOT
from verify import require

# Explicit JVM corner cases, including truncation toward zero and shift masking.
CASES = [
    ("add", [2147483647, 1], -2147483648), ("sub", [-2147483648, 1], 2147483647),
    ("mul", [65536, 65536], 0), ("div", [-7, 3], -2), ("div", [7, -3], -2),
    ("div", [-2147483648, -1], -2147483648), ("rem", [-7, 3], -1), ("rem", [7, -3], 1),
    ("neg", [-2147483648], -2147483648), ("shl", [1, -1], -2147483648),
    ("shl", [1, 32], 1), ("shr", [-8, 1], -4), ("ushr", [-1, 1], 2147483647),
    ("ushr", [-1, 32], -1), ("and", [17, 0], 0), ("or", [16, 3], 19),
    ("xor", [17, 17], 0), ("asByte", [255], -1), ("asByte", [128], -128),
    ("asChar", [-1], 65535), ("asShort", [65535], -1), ("asShort", [32768], -32768),
]


def run(jdk, agent, output):
    output.mkdir(parents=True)
    classes = output / "classes"; classes.mkdir()
    calls = [f'System.out.println(IntOps.{name}({",".join(map(str, args))}));' for name, args, _ in CASES]
    driver = output / "IntDriver.java"
    driver.write_text("package calibration; public final class IntDriver { public static void main(String[] a) {\n"
                      + "\n".join(calls) + "\n} }\n")
    source = HERE / "semantics/calibration/IntOps.java"
    build = command([jdk / "javac", "--release", "17", "-g", "-d", classes, source, driver])
    sources, targets = [], []
    for n, (method, args, expected) in enumerate(CASES, 1):
        sources.extend(dict(id=f"r{n}.arg{i}", kind="argument", root=n, arg=i) for i in range(len(args)))
        targets.append(dict(id=f"r{n}", kind="return", root=n))
    query = dict(schema="java-source-query-v1", sources=sources, targets=targets)
    (output / "query.json").write_text(json.dumps(query, indent=2) + "\n")
    report = dict(status="running", scope="JVM integer semantic calibration; not application or performance evidence", modes=[])
    try:
        for mode, flags in (("default", []), ("interpreter", ["-Xint"])):
            native = command([jdk / "java", *flags, "-cp", classes, "calibration.IntDriver"])
            capture = output / mode
            observed = command([jdk / "java", *flags, "-Xverify:all", f"-javaagent:{agent}",
                                "-Dtracefusion.classes=calibration.IntOps", f"-Dtracefusion.output={capture}",
                                "-cp", classes, "calibration.IntDriver"])
            expected_stdout = "".join(str(c[2]) + "\n" for c in CASES)
            require(native["stdout"] == observed["stdout"] == expected_stdout, "native/observed integer outputs")
            answer = infer(capture, query)
            (capture / "inference.json").write_text(json.dumps(answer, indent=2) + "\n")
            require(answer["status"] == "ok", str(answer))
            for n, (r, (_, args, expected)) in enumerate(zip(answer["results"], CASES), 1):
                require(r["value"] == expected, "replayed integer value")
                require(r["direct_sources"] == [f"r{n}.arg{i}" for i in range(len(args))], "integer data dependency")
            require(len(answer["results"]) == len(CASES), "integer result count")
            report["modes"].append(dict(mode=mode, queries=len(CASES), native=native, observed=observed))
        report.update(status="pass", total_checks=len(CASES)*2, distinct_inputs=len(CASES), build=build,
                      agent_sha256=hashlib.sha256(agent.read_bytes()).hexdigest(),
                      source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      cases=[dict(method=n, arguments=a, expected=v) for n, a, v in CASES])
    finally:
        (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "total_checks", "distinct_inputs")}, indent=2))
    print("Results:", output)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jdk", type=Path, required=True)
    p.add_argument("--agent", type=Path, required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    target = args.output or ROOT / "artifacts" / ("java-integer-calibration-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    run(args.jdk.resolve() / "bin", args.agent.resolve(), target.resolve())
