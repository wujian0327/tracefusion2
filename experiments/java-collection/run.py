#!/usr/bin/env python3
"""Build a real javaagent, collect on a JVM, validate and package raw evidence."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from verify import check_fixture, validate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEPS = {"asm": "8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281",
        "asm-tree": "9929881f59eb6b840e86d54570c77b59ce721d104e6dfd7a40978991c2d3b41f"}
CASES = ("left", "right", "alias", "overwrite", "nested", "loop", "gc")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args, cwd=None):
    p = subprocess.run([str(x) for x in args], cwd=cwd, text=True, capture_output=True, timeout=120)
    if p.returncode:
        raise RuntimeError(f"command failed ({p.returncode}): {args}\n{p.stdout}\n{p.stderr}")
    return {"command": [str(x) for x in args], "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}


def build(jdk, target):
    cache = ROOT / "artifacts/java-collection-deps"
    cache.mkdir(parents=True, exist_ok=True)
    jars = []
    for name, sha in DEPS.items():
        jar = cache / f"{name}-9.7.1.jar"
        if not jar.exists():
            url = f"https://repo.maven.apache.org/maven2/org/ow2/asm/{name}/9.7.1/{jar.name}"
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read(2_000_000)
            if hashlib.sha256(data).hexdigest() != sha:
                raise ValueError("ASM download hash mismatch")
            jar.write_bytes(data)
        if digest(jar) != sha:
            raise ValueError(f"dependency hash mismatch: {jar}")
        jars.append(jar)
    classes, fixture = target / "agent-classes", target / "fixture-classes"
    classes.mkdir(); fixture.mkdir()
    log = [command([jdk / "javac", "--release", "17", "-g", "-cp", os.pathsep.join(map(str, jars)),
                    "-d", classes, *sorted((HERE / "src").rglob("*.java"))]),
           command([jdk / "javac", "--release", "17", "-g", "-d", fixture,
                    *sorted((HERE / "fixtures").rglob("*.java"))])]
    agent = target / "tracefusion-java-agent.jar"
    with zipfile.ZipFile(agent, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nPremain-Class: tracefusion.Agent\n\n")
        for f in sorted(classes.rglob("*.class")):
            z.write(f, f.relative_to(classes).as_posix())
        for jar in jars:
            with zipfile.ZipFile(jar) as src:
                for name in src.namelist():
                    if name.startswith("org/objectweb/asm/") and name.endswith(".class"):
                        z.writestr(name, src.read(name))
    return agent, fixture, log


def fault_checks(capture, scratch):
    original = [json.loads(x) for x in (capture / "events.jsonl").read_text().splitlines()]
    checks = []
    for fault in ("missing_footer", "missing_step", "missing_step_renumbered", "missing_read_renumbered",
                  "reordered_events", "write_version", "object_identity", "return_value"):
        dest = scratch / fault
        shutil.copytree(capture, dest)
        rows = json.loads(json.dumps(original))
        if fault == "missing_footer": rows.pop()
        elif fault == "missing_step": rows.pop(next(i for i, r in enumerate(rows) if r["kind"] == "step"))
        elif fault in ("missing_step_renumbered", "missing_read_renumbered"):
            kind = "step" if fault == "missing_step_renumbered" else "read"
            rows.pop(next(i for i, r in enumerate(rows) if r["kind"] == kind))
            for i, r in enumerate(rows, 1): r["seq"] = i
        elif fault == "reordered_events": rows[3], rows[4] = rows[4], rows[3]
        elif fault == "write_version": next(r for r in rows if r["kind"] == "write")["values"][3] += 1
        elif fault == "object_identity": next(r for r in rows if r["kind"] == "read")["values"][0] = "o999"
        elif fault == "return_value": next(r for r in rows if r["kind"] == "exit")["values"][0] += 1
        (dest / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        try:
            check_fixture(dest, "overwrite")
        except ValueError as e:
            checks.append({"fault": fault, "rejected": True, "reason": str(e)})
        else:
            raise AssertionError("fault accepted: " + fault)
    return checks


def run(args):
    if args.jdk:
        jdk = Path(args.jdk).resolve() / "bin"
    else:
        javac = shutil.which("javac")
        if not javac:
            raise RuntimeError("A complete JDK 17+ is required; pass --jdk /path/to/jdk")
        jdk = Path(javac).resolve().parent
    java_info = command([jdk / "java", "-version"])
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = ROOT / "artifacts" / ("java-collection-" + stamp)
    target.mkdir(parents=True)
    result = {"schema": "java-collection-validation-v1", "status": "running",
              "scope": "controlled JVM collection only; no provenance inference or external-tool comparison",
              "java": java_info, "dependencies": DEPS, "cases": [], "negative_cases": []}
    try:
        agent, fixture, log = build(jdk, target)
        result["build"] = log
        result["agent_sha256"] = digest(agent)
        result["source_sha256"] = {str(f.relative_to(HERE)): digest(f) for f in sorted(HERE.rglob("*"))
                                    if f.is_file() and f.suffix in (".java", ".py")}
        # Collect javap disassembly of ORIGINAL bytecode for independently inspectable site mapping.
        disasm = command([jdk / "javap", "-c", "-p", "-s", "-classpath", fixture, "demo.Subject"])
        (target / "original-javap.txt").write_text(disasm["stdout"])
        for mode in ("default", "interpreter"):
            flags = [] if mode == "default" else ["-Xint"]
            for case in CASES:
                native = command([jdk / "java", *flags, "-cp", fixture, "demo.Driver", case])
                capture = target / f"{mode}-{case}"
                observed = command([jdk / "java", *flags, "-Xverify:all", f"-javaagent:{agent}",
                                    f"-Dtracefusion.output={capture}", "-cp", fixture, "demo.Driver", case])
                if native["stdout"] != observed["stdout"]:
                    raise AssertionError("instrumentation changed business output")
                expected = "34\n" if case == "nested" else "68\n" if case == "loop" else "17\n"
                if native["stdout"] != expected:
                    raise AssertionError("native fixture output mismatch")
                checked = check_fixture(capture, case)
                record = {"case": case, "mode": mode, **checked, "native": native, "observed": observed}
                (capture / "run.json").write_text(json.dumps(record, indent=2) + "\n")
                result["cases"].append(record)
        for case in ("null", "threads", "unsupported", "limit", "external", "handler", "volatile"):
            capture = target / ("negative-" + case)
            fixture_case = "loop" if case == "limit" else case
            extra = ["-Dtracefusion.maxEvents=10"] if case == "limit" else []
            observed = command([jdk / "java", "-Xverify:all", f"-javaagent:{agent}",
                                f"-Dtracefusion.output={capture}",
                                "-Dtracefusion.classes=demo.Subject,demo.Unsupported,demo.Unsupported$External,demo.Unsupported$Handler,demo.Unsupported$VolatileRead", *extra,
                                "-cp", fixture, "demo.Driver", fixture_case])
            rows = [json.loads(s) for s in (capture / "events.jsonl").read_text().splitlines()]
            if rows[-1]["values"][0] != "unknown":
                raise AssertionError("negative capture accepted: " + case)
            reasons = rows[-1]["values"][1]
            expected_reason = {"null": "incomplete_frames", "threads": "multiple_application_threads",
                               "unsupported": "argument_type", "limit": "event_limit",
                               "external": "unsupported_opcode", "handler": "exception_handlers",
                               "volatile": "inherited_or_volatile_field"}[case]
            if not any(expected_reason in s for s in reasons):
                raise AssertionError("wrong rejection reason")
            try: validate(capture)
            except ValueError: pass
            else: raise AssertionError("validator accepted negative capture")
            result["negative_cases"].append({"case": case, "reasons": reasons, "observed": observed})
        result["fault_checks"] = fault_checks(target / "default-overwrite", target / "faults")
        result["status"] = "pass"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = repr(e)
        raise
    finally:
        (target / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
        shutil.copytree(HERE, target / "source", ignore=shutil.ignore_patterns("__pycache__"))
        archive = shutil.make_archive(str(target), "zip", target.parent, target.name)
        print(json.dumps({"status": result["status"], "directory": str(target), "archive": archive}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jdk", help="JDK root containing bin/java and bin/javac")
    run(p.parse_args())
