#!/usr/bin/env python3
"""Verify byte-array capture manifests, re-infer raw events and recompute costs."""
import argparse
import json
from pathlib import Path
import random
import zipfile

from compare_arrays import JARS, MODES, OWNER, CORE, cases, query, check, reference
from compare_observations import save, summarize
from infer import infer
from run import HERE, digest


def verify(directory, correctness_only=False):
    out=directory.resolve();report=json.loads((out/"validation.json").read_text())
    assert report["status"] in ("pass","collected") and report["modes"]==MODES
    cost_evidence_issues=[]
    for name,sha in report["evidence_files"].items():
        f=(out/name).resolve();assert f.is_relative_to(out),name
        if digest(f)!=sha:
            parts=Path(name).parts
            assert correctness_only and parts[0].startswith("cost-"),name
            cost_evidence_issues.append(dict(file=name,issue="manifest hash mismatch"))
    for name,sha in report["source_sha256"].items():
        assert digest(out/"source"/name)==sha,name
    for name in CORE:assert digest(HERE/name)==report["source_sha256"][name],name
    for name,sha in JARS.items():assert digest(out/name)==sha
    with zipfile.ZipFile(out/"commons-codec-1.17.1.jar") as z:
        original=z.read(OWNER+".class")
        assert original==(out/"upstream-original"/(OWNER+".class")).read_bytes()
    assert report["inputs"]==cases()
    groups,seen,raw_events={},set(),0
    for c in report["cases"]:
        key=(c["jvm"],c["mode"]);assert key not in seen;seen.add(key)
        capture=out/c["capture"];q=query(cases())
        assert json.loads((capture/"query.json").read_text())==q
        answer=infer(capture,q);check(answer,cases())
        assert answer==json.loads((capture/"inference.json").read_text())
        assert answer["results"]==c["results"] and answer["observation"]["raw_events"]==c["events"]
        assert (capture/"events.jsonl").stat().st_size==c["bytes"]
        assert (capture/(OWNER.replace('/','_')+".original.class")).read_bytes()==original
        raw_events+=c["events"];groups.setdefault(c["jvm"],{})[c["mode"]]=answer
    assert seen=={(j,m) for j in ("default","interpreter") for m in MODES}
    for answers in groups.values():
        for mode in MODES[1:]:
            for key in ("results","nodes","branch_observations","source_aliases"):assert answers[mode][key]==answers["full"][key]
    repeated=cases()*report["rounds"];q=query(repeated)
    assert json.loads((out/"cost-query.json").read_text())==q
    rng=random.Random(report["seed"]);seen=set()
    if correctness_only:
        for r in report["measurements"]:
            dest=out/r["directory"]
            if (dest/"online/stdout.txt").read_text()!=str(sum(reference(c["data"],c["length"],c["seed"]) for c in repeated))+"\n":
                cost_evidence_issues.append(dict(file=r["directory"]+"/online/stdout.txt",issue="business checksum missing or incorrect"))
            if r["mode"]!="native":
                if len((dest/"capture/events.jsonl").read_text().splitlines())!=r["events"]:
                    cost_evidence_issues.append(dict(file=r["directory"]+"/capture/events.jsonl",issue="raw capture count differs from recorded measurement"))
    for block in (() if correctness_only else range(-report["warmup_blocks"],report["repetitions"])):
        order=["native",*MODES];rng.shuffle(order)
        for pos,mode in enumerate(order):
            r=next(r for r in report["measurements"] if r["block"]==block and r["position"]==pos)
            assert r["mode"]==mode and r["order"]==order and r["warmup"]==(block<0)
            assert (block,mode) not in seen;seen.add((block,mode));dest=out/r["directory"]
            expected_stdout=str(sum(reference(c["data"],c["length"],c["seed"]) for c in repeated))+"\n"
            if (dest/"online/stdout.txt").read_text()!=expected_stdout:
                assert correctness_only,"business stdout checksum mismatch: "+r["directory"]
                cost_evidence_issues.append(dict(file=r["directory"]+"/online/stdout.txt",issue="business checksum missing or incorrect"))
            for name in ("online","offline"):
                s=r[name]
                if s is None:continue
                assert json.loads((dest/name/"measurement.json").read_text())==s
                user,system,rss,floor=(dest/name/"resource.txt").read_text().split()
                assert s["user_seconds"]==float(user) and s["system_seconds"]==float(system)
                assert s["cpu_seconds"]==float(user)+float(system) and s["peak_rss_kib"]==int(rss) and s["supervisor_rss_kib"]==int(floor)
            for metric in ("wall","cpu"):
                assert r[f"end_to_end_{metric}_seconds"]==r["online"][metric+"_seconds"]+(r["offline"][metric+"_seconds"] if r["offline"] else 0)
            if mode=="native":assert r["offline"] is None and r["events"]==r["trace_bytes"]==0
            else:
                capture=dest/"capture";answer=infer(capture,q);check(answer,repeated)
                assert answer==json.loads((dest/"inference.json").read_text())
                assert answer["observation"]["raw_events"]==r["events"] and (capture/"events.jsonl").stat().st_size==r["trace_bytes"]
                assert (capture/(OWNER.replace('/','_')+".original.class")).read_bytes()==original
                if mode=="boundary":
                    rows=[json.loads(x) for x in (capture/"events.jsonl").read_text().splitlines()]
                    assert all(x["kind"] in ("start","class","enter","snapshot","exit","finish") and '@' not in x['site'] for x in rows)
                raw_events+=r["events"]
    if not correctness_only:assert len(report["measurements"])==len(seen)
    for f in report["faults"]:
        q=query(cases())
        if f["fault"]=="wrong_source_index":q["sources"][0]["index"]=4096
        answer=infer(out/"faults"/f["fault"],q)
        assert answer["status"]=="unknown" and not answer["results"] and answer["reason"]==f["reason"]
    for f in report["runtime_rejections"]:assert infer(out/("negative-"+f["case"]),query(cases()))==f["answer"]
    if not correctness_only:assert summarize(report)==report["summary"]
    return dict(status="pass",coverage="correctness_only" if correctness_only else "correctness_and_costs",
                costs_qualified=not correctness_only,cost_evidence_issues=cost_evidence_issues,
                verifier_sha256=digest(Path(__file__)),manifest_sha256=digest(out/"validation.json"),evidence_files=len(report["evidence_files"]),
                original_jvm_captures=6,distinct_queries=20,queries_including_two_jvm_modes_and_three_capture_methods=120,
                cost_commands=len(seen),raw_events_reinferred=raw_events,offline_faults=8,actual_jvm_rejections=3)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("directory",type=Path);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--correctness-only",action="store_true",help="verify the dedicated correctness captures; exclude all cost runs and report observed cost artifact defects")
    a=p.parse_args();result=verify(a.directory,a.correctness_only);save(a.output,result);print(json.dumps(result,indent=2))
