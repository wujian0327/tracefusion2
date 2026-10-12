#!/usr/bin/env python3
"""Re-read saved external tags, source bindings, raw traces and paired resource records."""
import argparse
import json
from pathlib import Path
import random
import zipfile

from compare_arrays import CORE, ENTRY, JARS, MODES, OWNER, cases, check, query
from compare_galette import METHODS, parse_output, summary
from compare_observations import save
from infer import infer
from prepare_galette import REVISION
from run import HERE, digest


def resource(directory, record):
    assert json.loads((directory/"measurement.json").read_text())==record
    u,s,r,f=(directory/"resource.txt").read_text().split()
    assert record["user_seconds"]==float(u) and record["system_seconds"]==float(s)
    assert record["cpu_seconds"]==float(u)+float(s) and record["wall_seconds"]>0
    assert record["peak_rss_kib"]==int(r) and record["supervisor_rss_kib"]==int(f)


def verify(directory):
    out=directory.resolve();r=json.loads((out/"validation.json").read_text())
    assert r["schema"]=="java-galette-comparison-v1" and r["status"]=="collected"
    assert r["galette_revision"]==REVISION and r["inputs"]==cases()
    for name,sha in r["evidence_files"].items():
        f=(out/name).resolve();assert f.is_relative_to(out) and digest(f)==sha,name
    for name in (*CORE,"compare_galette.py","compare_arrays.py","compare_observations.py","external_measure.py","upstream/ExternalHashDriver.java","measure_command.c"):
        assert digest(HERE/name)==digest(out/"source"/name),name
    for name,sha in JARS.items(): assert digest(out/name)==sha
    prep=json.loads((out/"galette-preparation.json").read_text())
    assert prep["status"]=="prepared" and prep["revision"]==REVISION
    assert digest(out/"galette-agent.jar")==prep["artifacts_sha256"]["galette-agent.jar"]
    assert digest(out/"tracefusion-java-agent.jar")==r["agent_sha256"]
    assert r["startup_probes"]==json.loads((out/"startup-probes.json").read_text())
    assert r["startup_probes"]["default"]["returncode"]==0
    with zipfile.ZipFile(out/"commons-codec-1.17.1.jar") as z: original=z.read(OWNER+".class")
    assert original==(out/"upstream-original"/(OWNER+".class")).read_bytes()
    assert digest(out/"upstream-original"/(OWNER+".class"))==r["class_sha256"]
    rows=cases()
    expected_csv="".join(bytes(c["data"]).hex()+f',{c["length"]},{c["seed"]}\n' for c in rows)
    assert (out/"inputs.csv").read_text()==expected_csv
    assert len(r["cases"])==2 and {c["jvm"] for c in r["cases"]}=={"default","interpreter"}
    audited=0
    for c in r["cases"]:
        dest=out/c["directory"];resource(dest,c["measurement"])
        assert ("-Xint" in c["measurement"]["command"])==(c["jvm"]=="interpreter")
        observed=parse_output((dest/"stdout.txt").read_text(),rows,True,audit=True)
        for key,v in observed.items():assert c[key]==v
        audited+=observed["source_bindings"]
    repeated=rows*(r["rounds"]+r["jvm_warmup_rounds"]);q=query(repeated)
    assert json.loads((out/"query.json").read_text())==q
    rng=random.Random(r["seed"]);seen=set();events=0;root_bindings=0;answers={}
    for block in range(-r["warmup_blocks"],r["repetitions"]):
        order=METHODS.copy();rng.shuffle(order)
        for position,mode in enumerate(order):
            m=next(x for x in r["measurements"] if x["block"]==block and x["position"]==position)
            assert m["order"]==order and m["mode"]==mode and m["warmup"]==(block<0)
            assert (block,mode) not in seen;seen.add((block,mode))
            dest=out/m["directory"];resource(dest/"online",m["online"])
            assert m["online"]["output_persistence"]=="parent-pipes-v1"
            cmd=m["online"]["command"]
            assert "upstream.ExternalHashDriver" in cmd
            assert not any(x.startswith("-Xverify:") or x=="-noverify" for x in cmd)
            assert cmd[-4:]==[str(r["rounds"]),str(r["jvm_warmup_rounds"]),"galette" if mode=="galette" else "plain","no-audit"]
            observed=parse_output((dest/"online/stdout.txt").read_text(),repeated,mode=="galette",measured_calls=20*r["rounds"])
            for key in ("window_wall_seconds","window_cpu_seconds"):assert m[key]==observed[key]
            if mode in MODES:
                resource(dest/"offline",m["offline"])
                capture=dest/"capture";answer=infer(capture,q);check(answer,repeated)
                assert answer==json.loads((dest/"inference.json").read_text())
                raw=[json.loads(l) for l in (capture/"events.jsonl").read_text().splitlines()]
                assert raw[0]["values"][2]==mode
                assert answer["observation"]["raw_events"]==m["events"]==len(raw)
                assert (capture/"events.jsonl").stat().st_size==m["trace_bytes"]
                assert (capture/(OWNER.replace('/','_')+".original.class")).read_bytes()==original
                roots=[x for x in raw if x["kind"]=="enter" and x["site"]==ENTRY and x["values"][0]==0]
                snapshots={x["frame"]:x for x in raw if x["kind"]=="snapshot"}
                assert len(roots)==len(repeated)
                objects={}
                for root,row in zip(roots,repeated):
                    # HexFormat may reuse its zero-length array. It contains no source elements.
                    obj=root["values"][1]
                    if obj in objects: assert row["data"]==objects[obj]==[]
                    objects[obj]=row["data"]
                    assert root["values"][2:]==[row["length"],row["seed"]]
                    assert snapshots[root["frame"]]["values"]==[0,obj,"[B",len(row["data"]),[x if x<128 else x-256 for x in row["data"]]]
                if mode=="boundary":assert all(x["kind"] in ("start","class","enter","snapshot","exit","finish") and '@' not in x['site'] for x in raw)
                root_bindings+=len(roots);events+=len(raw)
                # Compare provenance answers across the three capture modes.
                answers.setdefault(block,{})[mode]=answer["results"]
            else: assert m["offline"] is None and m["events"]==m["trace_bytes"]==0
            for metric in ("wall","cpu"):
                online=m["online"][metric+"_seconds"];offline=m["offline"][metric+"_seconds"] if m["offline"] else 0
                assert m[f"online_{metric}_seconds"]==online and m[f"offline_{metric}_seconds"]==offline
                assert m[f"end_to_end_{metric}_seconds"]==online+offline
    assert len(seen)==len(r["measurements"])
    for group in answers.values():assert group["full"]==group["sparse"]==group["boundary"]
    assert summary(r["measurements"])==r["summary"]
    return dict(status="pass",manifest_sha256=digest(out/"validation.json"),verifier_sha256=digest(Path(__file__)),
        evidence_files=len(r["evidence_files"]),galette_revision=REVISION,galette_correctness_queries=40,
        external_source_bindings_audited=audited,cost_commands=len(seen),queries_per_cost_command=len(repeated),
        raw_events_reinferred=events,our_root_input_bindings_audited=root_bindings,
        costs_qualified="whole-command measurements only; warmed windows diagnostic; memory unqualified",summary=r["summary"])


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("directory",type=Path)
    p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    result=verify(a.directory);save(a.output,result);print(json.dumps(result,indent=2))
