#!/usr/bin/env python3
"""Read-only, pinned-source preflight; does not build/run the service or score provenance."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVISION = "474d0f2eb73d97525234995a40d7781b7923a07d"
GAL_REVISION = "bc6002cc5ee4d6eaa30518b2d176a9831d77cb1a"


def command(args, cwd=None):
    p = subprocess.run([str(x) for x in args], cwd=cwd, text=True,
                       capture_output=True, timeout=30)
    if p.returncode:
        raise RuntimeError(p.stderr or p.stdout)
    return p.stdout.strip()


def evidence(base, relative, needles):
    path = base / relative
    data = path.read_bytes()
    lines = data.decode().splitlines()
    matches = []
    for needle in needles:
        found = [{"line": i, "text": line.strip()}
                 for i, line in enumerate(lines, 1) if needle in line]
        if not found:
            raise ValueError(f"source assumption changed: {relative}: {needle}")
        matches.append({"needle": needle, "matches": found})
    return {"path": relative, "sha256": hashlib.sha256(data).hexdigest(),
            "evidence": matches}


def clean_revision(path, expected):
    revision = command(["git", "rev-parse", "HEAD"], path)
    if revision != expected:
        raise ValueError(f"expected revision {expected}, got {revision}")
    if command(["git", "status", "--porcelain", "--untracked-files=no"], path):
        raise ValueError("tracked upstream source is modified")
    return revision


def main(a):
    upstream = a.upstream.resolve()
    revision = clean_revision(upstream, REVISION)
    app = "src/adservice/src/main/java/hipstershop/AdService.java"
    records = [
        evidence(upstream, app, [
            "public void getAds(", "catch (StatusRuntimeException",
            "private Collection<Ad> getAdsByCategory(", "return adsMap.get(category)",
            "new ArrayList<>()", "AdResponse.newBuilder().addAllAds(allAds).build()",
            "responseObserver.onNext(reply)", "random.nextInt",
            ".setText(", ".setRedirectUrl(", '.putAll("kitchen", bambooGlassJar, mug)']),
        evidence(upstream, "src/adservice/build.gradle",
                 ["sourceCompatibility = JavaVersion.VERSION_19",
                  "targetCompatibility = JavaVersion.VERSION_19"]),
        evidence(upstream, "src/adservice/Dockerfile",
                 ["FROM eclipse-temurin:21", "FROM eclipse-temurin:25"]),
        evidence(upstream, "src/adservice/src/main/proto/demo.proto",
                 ["repeated string context_keys", "repeated Ad ads",
                  "string redirect_url", "string text"]),
    ]
    engine = [
        evidence(ROOT, "experiments/java-collection/classfile.py",
                 ["45 <= major <= 61", "method access contract"]),
        evidence(ROOT, "experiments/java-collection/src/tracefusion/Agent.java",
                 ["static_concrete_unsynchronized_methods_only", "exception_handlers:",
                  'f.desc.equals("I")', "op == INVOKESTATIC"]),
        evidence(ROOT, "experiments/java-collection/observation.py",
                 ["external scope callee:", '== owner, "external scope callee:']),
        evidence(ROOT, "experiments/java-collection/src/tracefusion/Recorder.java",
                 ["multiple_application_threads"]),
    ]
    galette = {"service_runtime": "not_run", "source": "not_supplied"}
    if a.galette_source:
        gp = a.galette_source.resolve()
        galette.update({
            "revision": clean_revision(gp, GAL_REVISION),
            "source": evidence(gp, "README.md",
                               ["requires Java 17 to build", "Java 8 through 21"]),
            "interpretation": "JDK21 candidate; README is not service compatibility evidence",
        })
    jdk = {"status": "not_probed"}
    if a.jdk:
        version = command([a.jdk.resolve() / "bin/javac", "-version"])
        jdk = {"status": "compiler_version_only", "javac": version,
               "service_build": "not_attempted"}
    report = {
        "schema": "adservice-source-preflight-v1",
        "status": "blocked_by_current_tracefusion_contract",
        "evidence_level": "pinned_source_inspection_and_optional_compiler_version_only",
        "upstream": {"repository": "GoogleCloudPlatform/microservices-demo",
                     "tag": "v0.10.4", "revision": revision, "tracked_clean": True},
        "upstream_evidence": records,
        "engine_revision": command(["git", "rev-parse", "HEAD"], ROOT),
        "engine_evidence": engine,
        "jdk": jdk, "galette": galette,
        "blockers": [
            {"id": "class_version", "finding": "upstream target Java19; decoder accepts at most Java17",
             "kind": "static_configuration_mismatch"},
            {"id": "instance_calls", "finding": "RPC and category lookup are instance methods; agent requires static methods",
             "kind": "static_contract_mismatch"},
            {"id": "reference_fields_and_libraries", "finding": "String/collections/protobuf and cross-class calls exceed field/call contracts",
             "kind": "static_contract_mismatch"},
            {"id": "exception_handlers", "finding": "getAds has catch; agent rejects exception handlers",
             "kind": "static_contract_mismatch"},
            {"id": "threading", "finding": "current recorder rejects multiple observed application threads; RPC threading requires measurement",
             "kind": "unvalidated_runtime_requirement"},
            {"id": "random_fallback", "finding": "empty/unmatched contexts use Random; replay needs observed/declared random state",
             "kind": "additional_contract_requirement"},
        ],
        "proposed_queries": [
            {"id": "ad_text", "source": "initialized catalog Ad object text field",
             "sink": "AdResponse.ads[i].text"},
            {"id": "ad_url", "source": "initialized catalog Ad object redirect_url field",
             "sink": "AdResponse.ads[i].redirect_url"},
        ],
        "query_semantics": {
            "boundary": "catalog objects after initialization, not remote/database provenance",
            "source_identity": "catalog object identity plus field; never string value equality",
            "context_keys": "selection/address influence, not declared direct text-content source",
            "not_implemented": "source tagging, independent runtime oracle, collector, RPC comparison",
        },
        "runtime_results": {
            "native_service": "not_run", "tracefusion": "not_run",
            "galette": "not_run", "correct_queries": None, "performance": None,
        },
    }
    out = a.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(json.dumps({"status": report["status"], "output": str(out),
                      "runtime_executed": False, "blockers": len(report["blockers"])}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream", required=True, type=Path)
    p.add_argument("--galette-source", type=Path)
    p.add_argument("--jdk", type=Path)
    p.add_argument("--output", required=True, type=Path)
    main(p.parse_args())
