#!/usr/bin/env python3
"""Focused live-JVM gates: array identity, aliasing, lookup switch and rejected stores."""
import argparse
import hashlib
import json
from pathlib import Path

from compare_observations import collect_args, save
from infer import infer
from observation import plan, query_hash
from run import HERE, command, digest


def main(a):
    out=a.output.resolve();out.mkdir(parents=True)
    previous=json.loads((a.evidence/"validation.json").read_text())
    for name in ("classfile.py","observation.py","boundary.py","infer.py","verify.py","src/tracefusion/Agent.java","src/tracefusion/Recorder.java"):
        assert digest(HERE/name)==previous["source_sha256"][name]
    agent=a.evidence.resolve()/"tracefusion-java-agent.jar";assert digest(agent)==previous["agent_sha256"]
    classes=out/"classes";classes.mkdir();jdk=a.jdk.resolve()/"bin"
    command([jdk/"javac","--release","17","-d",classes,HERE/"semantics/calibration/ByteOps.java",HERE/"semantics/calibration/ByteDriver.java"])
    records=[]
    for case,selected in (("distinct",["right"]),("alias",["left","right"]),("-3",["byte0"]),("7",["byte1"]),("1000",["byte2"]),("2",["byte3"])):
        alias=case in ("distinct","alias")
        sources=([dict(id=name,kind="initial_array_element",root=1,arg=i,index=0) for i,name in enumerate(("left","right"))] if alias
                 else [dict(id=f"byte{i}",kind="initial_array_element",root=1,arg=0,index=i) for i in range(4)])
        sources.append(dict(id="selector",kind="argument",root=1,arg=2 if alias else 1))
        q=dict(schema="java-source-query-v1",sources=sources,targets=[dict(id="return",kind="return",root=1)])
        entry="calibration/ByteOps."+("select([B[BI)I" if alias else "lookup([BI)I")
        scope=out/(case+".properties");plan(classes,entry,q,scope,snapshots=True)
        answers={}
        for mode in ("full","sparse","boundary"):
            capture=out/(case+"-"+mode)
            run=command(collect_args(jdk,agent,classes,capture,mode,scope,"calibration.ByteDriver",[case]))
            answer=infer(capture,q);save(capture/"query.json",q);save(capture/"inference.json",answer)
            assert run["stdout"]=="17\n" and answer["status"]=="ok"
            assert answer["results"][0]["direct_sources"]==selected
            answers[mode]=answer
            records.append(dict(case=case,mode=mode,status="pass",sources=selected))
        for mode in ("sparse","boundary"):
            for key in ("results","nodes","branch_observations","source_aliases"):
                assert answers[mode][key]==answers["full"][key]
    q=dict(schema="java-source-query-v1",sources=[],targets=[dict(id="return",kind="return",root=1)])
    scope=out/"store.properties"
    try:plan(classes,"calibration/ByteOps.store([B)I",q,scope,snapshots=True)
    except ValueError as e:static_reason=str(e)
    else:raise AssertionError("array store should be rejected")
    # Deliberately bypass static planning to check the actual collector gate too.
    scope.write_text("schema=java-observation-scope-v3\nentry=calibration/ByteOps.store([B)I\nclasses=calibration/ByteOps\n"
                     +"sha256.calibration/ByteOps="+digest(classes/"calibration/ByteOps.class")+"\nquery.sha256="+query_hash(q)
                     +"\nmethod.count=1\nmethod.0=calibration/ByteOps.store([B)I\nsnapshot.count=1\nsnapshot.0.arg=0\nsnapshot.0.field=[B\n")
    capture=out/"store-rejected"
    run=command(collect_args(jdk,agent,classes,capture,"boundary",scope,"calibration.ByteDriver",["store"]))
    answer=infer(capture,q);save(capture/"inference.json",answer)
    assert run["stdout"]=="1\n" and answer["status"]=="unknown"
    report=dict(status="pass",cases=records,static_store_rejection=static_reason,actual_jvm_store_rejection=answer,
                source_sha256={n:digest(HERE/n) for n in ("check_arrays.py","semantics/calibration/ByteOps.java","semantics/calibration/ByteDriver.java")},
                evidence_files={str(f.relative_to(out)):digest(f) for f in sorted(out.rglob('*')) if f.is_file()})
    save(out/"validation.json",report)
    print(json.dumps(dict(status="pass",positive_captures=len(records),negative_captures=1),indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jdk",type=Path,required=True);p.add_argument("--evidence",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    main(p.parse_args())
