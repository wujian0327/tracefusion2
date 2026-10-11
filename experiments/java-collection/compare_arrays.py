#!/usr/bin/env python3
"""Original Commons Codec MurmurHash2 byte-array path, three capture modes and costs."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys
import urllib.request
import zipfile

from compare_observations import collect_args, measured, save, summarize
from infer import infer
from observation import plan
from run import HERE, ROOT, build, command, digest

OWNER = "org/apache/commons/codec/digest/MurmurHash2"
ENTRY = OWNER + ".hash32([BII)I"
JARS = {"commons-codec-1.17.1.jar": "f9f6cb103f2ddc3c99a9d80ada2ae7bf0685111fd6bffccb72033d1da4e6ff23",
        "commons-codec-1.17.1-sources.jar": "2283aff7f425dff23ebdb7a8fc0f03ae21b4ced7a43aacba47cedae126dc5d4a"}
MODES = ["full", "sparse", "boundary"]
CORE = ("classfile.py", "observation.py", "boundary.py", "infer.py", "verify.py", "src/tracefusion/Agent.java", "src/tracefusion/Recorder.java")


def cases():
    # All four tail lengths, multiple blocks, signed bytes, equal-valued positions,
    # ignored suffixes, empty input and non-default seeds. No application names in the engine.
    result = []
    for n in range(13):
        result.append(dict(name=f"prefix-{n}", data=[(i * 53 + 128) % 256 for i in range(16)], length=n, seed=17))
    result.extend([
        dict(name="empty", data=[], length=0, seed=0),
        dict(name="equal-bytes", data=[17]*12, length=7, seed=-1),
        dict(name="zero-bytes", data=[0]*20, length=17, seed=0),
        dict(name="suffix-a", data=[128,255,0,127,1,2,3,4], length=4, seed=-2**31),
        dict(name="suffix-b", data=[128,255,0,127,255,254,253,252], length=4, seed=-2**31),
        dict(name="multi-block", data=[(i*11) % 256 for i in range(64)], length=63, seed=2**31-1),
        dict(name="full-array", data=[0,255,128,127,0,255,128,127], length=8, seed=17),
    ])
    return result


def reference(data, length, seed):
    """Independent Python value oracle using chunk conversion and a packed tail.

    Does not use the JVM decoder, events, graph or engine arithmetic helper.
    Operational source truth is specified separately as the read prefix + length + seed.
    """
    mask, factor = 0xffffffff, 0x5bd1e995
    h = (seed ^ length) & mask
    data = bytes(data[:length]); stop = len(data) // 4 * 4
    for offset in range(0, stop, 4):
        k = int.from_bytes(data[offset:offset+4], "little") * factor & mask
        k ^= k >> 24; k = k * factor & mask
        h = (h * factor & mask) ^ k
    if stop != len(data):
        h ^= int.from_bytes(data[stop:], "little"); h = h * factor & mask
    h ^= h >> 13; h = h * factor & mask; h ^= h >> 15
    return h if h < 2**31 else h - 2**32


def query(rows):
    sources = []
    for r, row in enumerate(rows, 1):
        sources.extend(dict(id=f"r{r}.byte{i}", kind="initial_array_element", root=r, arg=0, index=i)
                       for i in range(len(row["data"])))
        sources.extend(dict(id=f"r{r}.{name}", kind="argument", root=r, arg=i) for i, name in ((1,"length"),(2,"seed")))
    return dict(schema="java-source-query-v1", sources=sources,
                targets=[dict(id=f"r{r}.return", kind="return", root=r) for r in range(1,len(rows)+1)])


def check(answer, rows):
    if answer["status"] != "ok": raise AssertionError(str(answer))
    expected = [(reference(c["data"], c["length"], c["seed"]),
                 sorted([f"r{r}.byte{i}" for i in range(c["length"])] + [f"r{r}.length", f"r{r}.seed"]))
                for r, c in enumerate(rows,1)]
    if [(r["value"],r["direct_sources"]) for r in answer["results"]] != expected:
        raise AssertionError("hash value or prefix provenance differs from independent oracle")


def prepare(jdk, out):
    cache = ROOT / "artifacts/java-array-deps"; cache.mkdir(parents=True,exist_ok=True)
    dependencies = []
    for name, sha in JARS.items():
        file = cache / name
        url = "https://repo.maven.apache.org/maven2/commons-codec/commons-codec/1.17.1/" + name
        if not file.exists():
            with urllib.request.urlopen(url, timeout=60) as r: data = r.read(4_000_000)
            if hashlib.sha256(data).hexdigest() != sha: raise ValueError("dependency download hash")
            file.write_bytes(data)
        if digest(file) != sha: raise ValueError("dependency hash")
        shutil.copyfile(file,out/name); dependencies.append(dict(name=name,url=url,sha256=sha))
    jar=out/"commons-codec-1.17.1.jar"
    original=out/"upstream-original"; (original/OWNER).parent.mkdir(parents=True)
    with zipfile.ZipFile(jar) as z:
        (original/(OWNER+".class")).write_bytes(z.read(OWNER+".class"))
        for name in ("LICENSE.txt","NOTICE.txt"): (out/name).write_bytes(z.read("META-INF/"+name))
    with zipfile.ZipFile(out/"commons-codec-1.17.1-sources.jar") as z:
        (out/"MurmurHash2.java").write_bytes(z.read(OWNER+".java"))
    agent, fixture, log=build(jdk,out)
    harness=out/"harness-classes";harness.mkdir()
    log.append(command([jdk/"javac","--release","17","-cp",jar,"-d",harness,HERE/"upstream/HashDriver.java"]))
    return agent, original, os.pathsep.join(map(str,(harness,jar))), dependencies, log


def fault_checks(capture, rows, out):
    checks=[]
    for name in ("missing_snapshot","snapshot_truncated","wrong_byte","same_value_index","missing_read","switch_selector","missing_exit","wrong_source_index"):
        dest=out/name;shutil.copytree(capture,dest)
        raw=[json.loads(x) for x in (dest/"events.jsonl").read_text().splitlines()];q=query(rows)
        if name.startswith("missing_"):
            kind=name[8:];kind="array_read" if kind=="read" else kind
            raw.pop(next(i for i,r in enumerate(raw) if r["kind"]==kind))
            for i,r in enumerate(raw,1):r["seq"]=i
        elif name=="snapshot_truncated":
            # A source label for the last element must not silently disappear.
            next(r for r in raw if r["kind"]=="snapshot")["values"][4].pop()
        elif name=="wrong_byte": next(r for r in raw if r["kind"]=="array_read")["values"][2]^=1
        elif name=="same_value_index":
            target=next(r for r in raw if r["kind"]=="enter" and r["site"]==ENTRY and r["values"][3]==-1)
            obj=target["values"][1]
            next(r for r in raw if r["kind"]=="array_read" and r["values"][0]==obj)["values"][1]+=1
        elif name=="switch_selector": next(r for r in raw if r["kind"]=="switch")["values"][0]^=1
        elif name=="wrong_source_index": q["sources"][0]["index"]=4096
        (dest/"events.jsonl").write_text("".join(json.dumps(r)+"\n" for r in raw))
        answer=infer(dest,q);save(dest/"inference.json",answer)
        if answer["status"]!="unknown" or answer["results"]: raise AssertionError("accepted "+name)
        checks.append(dict(fault=name,status="unknown",reason=answer["reason"]))
    return checks


def main(a):
    jdk=a.jdk.resolve()/"bin"
    for name in ("java","javac"):
        if not (jdk/name).is_file(): raise ValueError(f"未找到 {jdk/name}；--jdk 必须是实际安装的完整 JDK 根目录")
    out=ROOT/"artifacts"/("java-arrays-"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f"));out.mkdir(parents=True)
    report=dict(schema="java-array-comparison-v1",status="running",modes=MODES,cases=[],measurements=[],rounds=a.rounds,
                repetitions=a.repeats,warmup_blocks=a.warmup,seed=a.seed,
                qualification=dict(scope="unchanged hash32 byte-array call closure; one library path",snapshot="v3 complete immutable byte arrays <=4096 bytes",
                    semantics="operational operand data dependence; array index/address separate",array_writes=False,
                    whole_application=False,external_tool_comparison=False,steady_state=False))
    try:
        if a.reuse_correctness:
            olddir=a.reuse_correctness.resolve();old=json.loads((olddir/"validation.json").read_text())
            if old["inputs"]!=cases() or len(old["cases"])!=6:raise ValueError("incompatible correctness evidence")
            for name in CORE:
                if digest(HERE/name)!=old["source_sha256"][name]:raise ValueError("changed semantic source "+name)
            for name,sha in old["evidence_files"].items():
                f=(olddir/name).resolve()
                if not f.is_relative_to(olddir) or digest(f)!=sha:raise ValueError("changed prior evidence "+name)
            for name in ("agent-classes","fixture-classes","harness-classes","upstream-original","faults",*[c["capture"] for c in old["cases"]],"negative-null","negative-oversize","negative-bounds"):
                shutil.copytree(olddir/name,out/name)
            for name in (*JARS,"tracefusion-java-agent.jar","MurmurHash2.java","LICENSE.txt","NOTICE.txt","default-native.json","interpreter-native.json"):
                shutil.copyfile(olddir/name,out/name)
            agent=out/"tracefusion-java-agent.jar";original=out/"upstream-original"
            if digest(agent)!=old["agent_sha256"]:raise ValueError("changed prior agent")
            cp=os.pathsep.join(map(str,(out/"harness-classes",out/"commons-codec-1.17.1.jar")))
            report.update(dependencies=old["dependencies"],build=old["build"],cases=old["cases"],faults=old["faults"],
                          runtime_rejections=old["runtime_rejections"],correctness_reused_from=olddir.name,
                          prior_manifest_sha256=digest(olddir/"validation.json"))
            for c in report["cases"]:
                answer=infer(out/c["capture"],query(cases()));check(answer,cases())
                if answer!=json.loads((out/c["capture"]/"inference.json").read_text()):raise ValueError("changed prior inference")
        else:
            agent,original,cp,report["dependencies"],report["build"]=prepare(jdk,out)
        report["agent_sha256"]=digest(agent);report["class_sha256"]=digest(original/(OWNER+".class"))
        report["java"]=command([jdk/"java","-version"])
        rows=cases();report["inputs"]=rows
        input_file=out/"inputs.csv";input_file.write_text("".join(bytes(c["data"]).hex()+f',{c["length"]},{c["seed"]}\n' for c in rows))
        q=query(rows);scope=out/"query.properties";report["scope"]=plan(original,ENTRY,q,scope,snapshots=True)
        for jvm,flags in (() if a.reuse_correctness else (("default",[]),("interpreter",["-Xint"]))):
            native=command([jdk/"java",*flags,"-Xverify:all","-cp",cp,"upstream.HashDriver",input_file,"1"])
            save(out/(jvm+"-native.json"),native)
            if native["stdout"]!=str(sum(reference(c["data"],c["length"],c["seed"]) for c in rows))+"\n": raise AssertionError("native reference value")
            answers={}
            for mode in MODES:
                capture=out/f"{jvm}-{mode}"
                run=command(collect_args(jdk,agent,cp,capture,mode,scope,"upstream.HashDriver",[input_file,"1"],flags))
                if run["stdout"]!=native["stdout"]:raise AssertionError("changed business output")
                answer=infer(capture,q);check(answer,rows);answers[mode]=answer
                if digest(capture/(OWNER.replace('/','_')+".original.class"))!=report["class_sha256"]:raise AssertionError("changed upstream class")
                save(capture/"query.json",q);save(capture/"inference.json",answer);save(capture/"run.json",run)
                report["cases"].append(dict(jvm=jvm,mode=mode,capture=capture.name,results=answer["results"],
                    events=answer["observation"]["raw_events"],bytes=(capture/"events.jsonl").stat().st_size))
            for mode in MODES[1:]:
                for key in ("results","nodes","branch_observations","source_aliases"):
                    if answers[mode][key]!=answers["full"][key]:raise AssertionError("three-way graph mismatch "+key)
        if not a.reuse_correctness:
            report["faults"]=fault_checks(out/"default-sparse",rows,out/"faults")
            report["runtime_rejections"]=[]
        for case in (() if a.reuse_correctness else ("null","oversize","bounds")):
            capture=out/("negative-"+case)
            run=command(collect_args(jdk,agent,cp,capture,"boundary",scope,"upstream.HashDriver",[case]))
            answer=infer(capture,q);save(capture/"inference.json",answer);save(capture/"run.json",run)
            if answer["status"]!="unknown":raise AssertionError("accepted runtime negative "+case)
            report["runtime_rejections"].append(dict(case=case,answer=answer))
        repeated=rows*a.rounds;q=query(repeated);qfile=out/"cost-query.json";save(qfile,q)
        scope=out/"cost.properties";plan(original,ENTRY,q,scope,snapshots=True)
        supervisor=out/"measure-command"
        report["measurement_build"]=command(["cc","-O2","-Wall","-Wextra","-Werror",HERE/"measure_command.c","-o",supervisor])
        rng=random.Random(a.seed)
        for block in range(-a.warmup,a.repeats):
            order=["native",*MODES];rng.shuffle(order)
            for position,mode in enumerate(order):
                dest=out/f"cost-{block}-{position}-{mode}";capture=dest/"capture"
                cmd=([jdk/"java","-Xverify:all","-cp",cp,"upstream.HashDriver",input_file,str(a.rounds)] if mode=="native"
                     else collect_args(jdk,agent,cp,capture,mode,scope,"upstream.HashDriver",[input_file,str(a.rounds)]))
                online=measured(cmd,dest/"online",supervisor)
                if (dest/"online/stdout.txt").read_text()!=str(sum(reference(c["data"],c["length"],c["seed"]) for c in repeated))+"\n":raise AssertionError("cost checksum")
                offline,events,size=None,0,0
                if mode!="native":
                    offline=measured([sys.executable,HERE/"infer.py",capture,"--query",qfile,"--output",dest/"inference.json"],dest/"offline",supervisor)
                    answer=json.loads((dest/"inference.json").read_text());check(answer,repeated)
                    events=answer["observation"]["raw_events"];size=(capture/"events.jsonl").stat().st_size
                report["measurements"].append(dict(block=block,warmup=block<0,order=order,position=position,mode=mode,directory=dest.name,
                    online=online,offline=offline,events=events,trace_bytes=size,
                    end_to_end_wall_seconds=online["wall_seconds"]+(offline["wall_seconds"] if offline else 0),
                    end_to_end_cpu_seconds=online["cpu_seconds"]+(offline["cpu_seconds"] if offline else 0)))
                save(out/"validation.json",report)
        report["summary"]=summarize(report)
        report["qualification"]["memory_measurement_qualified"]=all(s["rss_above_supervisor_floor"] for r in report["measurements"] for s in (r["online"],r["offline"]) if s)
        # A separate verifier must re-read the archived files before results
        # are accepted; in-process checks alone do not qualify saved evidence.
        report["status"]="collected"
    except Exception as e:
        report.update(status="failed",error=repr(e));raise
    finally:
        report["source_sha256"]={str(f.relative_to(HERE)):digest(f) for f in sorted(HERE.rglob('*')) if f.is_file() and f.suffix in (".py",".java",".c")}
        shutil.copytree(HERE,out/"source",ignore=shutil.ignore_patterns("__pycache__"))
        report["evidence_files"]={str(f.relative_to(out)):digest(f) for f in sorted(out.rglob('*')) if f.is_file() and f.name!="validation.json"}
        save(out/"validation.json",report)
        print(json.dumps(dict(status=report["status"],directory=str(out),summary=report.get("summary")),indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jdk",type=Path,required=True)
    p.add_argument("--rounds",type=int,default=2)
    p.add_argument("--repeats",type=int,default=6)
    p.add_argument("--warmup",type=int,default=1)
    p.add_argument("--seed",type=int,default=20261011)
    p.add_argument("--reuse-correctness",type=Path,help="reuse checked raw captures with unchanged semantic code; rerun costs only")
    a=p.parse_args()
    if not 1<=a.rounds<=20 or not 1<=a.repeats<=30 or not 0<=a.warmup<=5:p.error("bounded experiment sizes required")
    main(a)
