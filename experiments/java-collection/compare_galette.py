#!/usr/bin/env python3
"""Pinned Galette versus full/sparse/boundary on the original Commons Codec path."""
import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys

from compare_arrays import ENTRY, MODES, OWNER, cases, check, prepare, query, reference
from compare_observations import collect_args
from external_measure import measured, save
from infer import infer
from observation import plan
from prepare_galette import REVISION
from run import HERE, ROOT, command, digest

METHODS = ["native", *MODES, "galette"]


def parse_output(text, rows, galette, audit=False, measured_calls=None):
    results, bindings, windows = [], [], []
    for line in text.splitlines():
        fields=line.split("\t")
        if len(fields)==4 and fields[0]=="RESULT":
            results.append((int(fields[1]),int(fields[2]),fields[3]))
        elif len(fields)==5 and fields[0]=="SOURCE":
            bindings.append((int(fields[1]),fields[2],int(fields[3]),fields[4]))
        elif len(fields)==4 and fields[0]=="WINDOW": windows.append(tuple(map(int,fields[1:])))
        else: raise ValueError("unexpected stdout record: "+line[:200])
    if len(results)!=len(rows) or len(windows)!=1: raise ValueError("incomplete driver output")
    checked=[]
    expected_bindings=[]
    for r,(row,actual) in enumerate(zip(rows,results),1):
        labels=sorted([f"r{r}.byte{i}" for i in range(row["length"])]+[f"r{r}.length",f"r{r}.seed"])
        if actual[:2]!=(r,reference(row["data"],row["length"],row["seed"])): raise ValueError("business output mismatch")
        observed=actual[2].split(",") if galette else []
        if galette and observed!=labels: raise ValueError(f"Galette source mismatch root {r}: {observed} != {labels}")
        if not galette and actual[2]!="-": raise ValueError("unexpected native provenance")
        checked.append(dict(root=r,value=actual[1],sources=observed))
        if audit:
            for i,v in enumerate(row["data"]): expected_bindings.append((r,f"byte{i}",v if v<128 else v-256,f"r{r}.byte{i}"))
            for key in ("length","seed"): expected_bindings.append((r,key,row[key],f"r{r}.{key}"))
    if bindings!=expected_bindings: raise ValueError("source binding audit mismatch")
    wall,cpu,count=windows[0]
    if wall<=0 or cpu<0 or count!=(measured_calls if measured_calls is not None else len(rows)):
        raise ValueError("invalid in-process window")
    return dict(results=checked,source_bindings=len(bindings),window_wall_seconds=wall/1e9,window_cpu_seconds=cpu/1e9,calls=count)


def summary(measurements):
    rows=[r for r in measurements if not r["warmup"]]
    keys=("online_wall_seconds","online_cpu_seconds","offline_wall_seconds","offline_cpu_seconds",
          "end_to_end_wall_seconds","end_to_end_cpu_seconds","window_wall_seconds","window_cpu_seconds")
    medians={m:{k:statistics.median(r[k] for r in rows if r["mode"]==m) for k in keys} for m in METHODS}
    pairs={}
    for mode in MODES:
        paired=[]
        for r in rows:
            if r["mode"]!=mode: continue
            g=next(x for x in rows if x["block"]==r["block"] and x["mode"]=="galette")
            paired.append({k:1-r[k]/g[k] for k in keys if g[k]>0})
        pairs[mode+"_vs_galette"]={k:dict(median=statistics.median(p[k] for p in paired),
            minimum=min(p[k] for p in paired),maximum=max(p[k] for p in paired),ours_worse=sum(p[k]<0 for p in paired))
            for k in keys if all(k in p for p in paired)}
    return dict(cost_medians=medians,paired_reduction=pairs)


def main(a):
    jdk=a.jdk.resolve();external=a.galette.resolve()
    prep=json.loads((external/"preparation.json").read_text())
    if prep["status"]!="prepared" or prep["revision"]!=REVISION: raise ValueError("unprepared or different Galette")
    for name,sha in prep["base_jdk_sha256"].items():
        if digest(jdk/name)!=sha: raise ValueError("native JDK differs from the Galette base: "+name)
    for name,sha in prep["instrumented_jdk_sha256"].items():
        if digest(external/"jdk"/name)!=sha: raise ValueError("instrumented JDK changed: "+name)
    for name,sha in prep["artifacts_sha256"].items():
        if digest(external/name)!=sha: raise ValueError("Galette JAR changed: "+name)
    out=ROOT/"artifacts"/("java-galette-"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    out.mkdir(parents=True)
    report=dict(schema="java-galette-comparison-v1",status="running",galette_revision=REVISION,
        inputs=cases(),cases=[],measurements=[],repetitions=a.repeats,warmup_blocks=a.warmup,
        rounds=a.rounds,jvm_warmup_rounds=a.jvm_warmup,seed=a.seed,platform=platform.uname()._asdict(),
        qualification=dict(external_tool=True,scope="one original hash32 call closure; not whole-application support",
            semantics="operand provenance; Galette additionally propagates index tags; no new labels from indices on these inputs",
            cost_scope="deployment comparison: Galette instruments JCL/application globally; ours instruments selected closure",
            steady_state=False,window="same-JVM warmup, diagnostic only; no JIT convergence assertion; includes input setup, tags and result buffering",
            memory_comparison_qualified=False,build_and_jdk_preparation_in_timing=False))
    try:
        agent,original,cp,report["dependencies"],report["build"]=prepare(jdk/"bin",out)
        shutil.copyfile(external/"galette-agent.jar",out/"galette-agent.jar")
        shutil.copyfile(external/"preparation.json",out/"galette-preparation.json")
        ga=out/"galette-agent.jar"
        report["qualification"]["jvm_verification"]="default JVM verification for all five groups; no -noverify/-Xverify:none"
        report["startup_probes"]={}
        for label,flags in (("default",[]),("verify_all",["-Xverify:all"])):
            cmd=[str(external/"jdk/bin/java"),*flags,f"-Xbootclasspath/a:{ga}",f"-javaagent:{ga}","-version"]
            probe=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
            report["startup_probes"][label]=dict(command=cmd,returncode=probe.returncode,stdout=probe.stdout,stderr=probe.stderr)
        if report["startup_probes"]["default"]["returncode"]: raise ValueError("Galette default JVM startup failed")
        save(out/"startup-probes.json",report["startup_probes"])
        cp=os.pathsep.join((cp,str(ga)))
        report["build"].append(command([jdk/"bin/javac","--release","17","-cp",cp,"-d",out/"harness-classes",HERE/"upstream/ExternalHashDriver.java"]))
        report["java"]=command([jdk/"bin/java","-version"])
        report["agent_sha256"]=digest(agent);report["class_sha256"]=digest(original/(OWNER+".class"))
        rows=cases(); input_file=out/"inputs.csv"
        input_file.write_text("".join(bytes(c["data"]).hex()+f',{c["length"]},{c["seed"]}\n' for c in rows))
        supervisor=out/"measure-command"
        report["measurement_build"]=command(["cc","-O2","-Wall","-Wextra","-Werror",HERE/"measure_command.c","-o",supervisor])
        def invocation(mode,dest,rounds,warmup,scope=None,flags=(),audit=False):
            args=[input_file,str(rounds),str(warmup),"galette" if mode=="galette" else "plain","audit" if audit else "no-audit"]
            if mode in MODES:
                cmd=collect_args(jdk/"bin",agent,cp,dest/"capture",mode,scope,"upstream.ExternalHashDriver",args,flags)
                cmd.remove("-Xverify:all")
                return cmd
            java=external/"jdk/bin/java" if mode=="galette" else jdk/"bin/java"
            options=[f"-Xbootclasspath/a:{ga}",f"-javaagent:{ga}"] if mode=="galette" else []
            return [java,*flags,*options,"-cp",cp,"upstream.ExternalHashDriver",*args]
        # Only the new external baseline gets dedicated correctness runs. Ours is checked in every cost run.
        if a.reuse_correctness:
            prior=a.reuse_correctness.resolve();old=json.loads((prior/"validation.json").read_text())
            if old["status"]!="collected" or old["inputs"]!=rows or len(old["cases"])!=2: raise ValueError("incompatible prior correctness")
            for name,sha in old["evidence_files"].items():
                f=(prior/name).resolve()
                if not f.is_relative_to(prior) or digest(f)!=sha: raise ValueError("prior evidence changed: "+name)
            if digest(prior/"source/upstream/ExternalHashDriver.java")!=digest(HERE/"upstream/ExternalHashDriver.java"):
                raise ValueError("external adapter changed")
            if digest(prior/"galette-agent.jar")!=digest(ga): raise ValueError("external agent changed")
            oldprep=json.loads((prior/"galette-preparation.json").read_text())
            for key in ("base_jdk_sha256","instrumented_jdk_sha256","revision"):
                if oldprep[key]!=prep[key]: raise ValueError("external runtime changed")
            for c in old["cases"]:
                shutil.copytree(prior/c["directory"],out/c["directory"])
                result=parse_output((out/c["directory"]/"stdout.txt").read_text(),rows,True,audit=True)
                for key,v in result.items():
                    if c[key]!=v: raise ValueError("prior correctness summary changed")
            report.update(cases=old["cases"],correctness_reused_from=prior.name,prior_manifest_sha256=digest(prior/"validation.json"))
        for vm,flags in (() if a.reuse_correctness else (("default",[]),("interpreter",["-Xint"]))):
            dest=out/("correctness-"+vm)
            metric=measured(invocation("galette",dest,1,0,flags=flags,audit=True),dest,supervisor)
            result=parse_output((dest/"stdout.txt").read_text(),rows,True,audit=True)
            report["cases"].append(dict(jvm=vm,directory=dest.name,measurement=metric,**result))
        repeated=rows*(a.jvm_warmup+a.rounds)
        q=query(repeated);save(out/"query.json",q)
        scope=out/"query.properties";report["scope"]=plan(original,ENTRY,q,scope,snapshots=True)
        rng=random.Random(a.seed)
        for block in range(-a.warmup,a.repeats):
            order=METHODS.copy();rng.shuffle(order)
            for position,mode in enumerate(order):
                dest=out/f"cost-{block}-{position}-{mode}"
                online=measured(invocation(mode,dest,a.rounds,a.jvm_warmup,scope),dest/"online",supervisor)
                observed=parse_output((dest/"online/stdout.txt").read_text(),repeated,mode=="galette",measured_calls=len(rows)*a.rounds)
                offline=None;events=0;size=0
                if mode in MODES:
                    offline=measured([sys.executable,HERE/"infer.py",dest/"capture","--query",out/"query.json","--output",dest/"inference.json"],dest/"offline",supervisor)
                    answer=json.loads((dest/"inference.json").read_text());check(answer,repeated)
                    events=answer["observation"]["raw_events"];size=(dest/"capture/events.jsonl").stat().st_size
                metrics={"online_wall_seconds":online["wall_seconds"],"online_cpu_seconds":online["cpu_seconds"],
                    "offline_wall_seconds":offline["wall_seconds"] if offline else 0,
                    "offline_cpu_seconds":offline["cpu_seconds"] if offline else 0,
                    "window_wall_seconds":observed["window_wall_seconds"],"window_cpu_seconds":observed["window_cpu_seconds"]}
                for resource in ("wall","cpu"):
                    metrics[f"end_to_end_{resource}_seconds"]=metrics[f"online_{resource}_seconds"]+metrics[f"offline_{resource}_seconds"]
                report["measurements"].append(dict(block=block,warmup=block<0,order=order,position=position,mode=mode,
                    directory=dest.name,online=online,offline=offline,events=events,trace_bytes=size,**metrics))
                save(out/"validation.json",report)
        report["summary"]=summary(report["measurements"]);report["status"]="collected"
    except Exception as e:
        report.update(status="failed",error=repr(e));raise
    finally:
        shutil.copytree(HERE,out/"source",ignore=shutil.ignore_patterns("__pycache__"))
        report["evidence_files"]={str(f.relative_to(out)):digest(f) for f in sorted(out.rglob('*')) if f.is_file() and f!=out/"validation.json"}
        save(out/"validation.json",report)
        print(json.dumps(dict(status=report["status"],directory=str(out),summary=report.get("summary")),indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jdk",type=Path,required=True)
    p.add_argument("--galette",type=Path,required=True,help="output of prepare_galette.py")
    p.add_argument("--rounds",type=int,default=2)
    p.add_argument("--jvm-warmup",type=int,default=0,help="same-JVM warmup rounds; warmup traces remain in total cost")
    p.add_argument("--repeats",type=int,default=6)
    p.add_argument("--warmup",type=int,default=1,help="discarded separate-process preparation blocks")
    p.add_argument("--seed",type=int,default=20261012)
    p.add_argument("--reuse-correctness",type=Path,help="reuse checked external correctness with identical adapter, agent and JDK; run new costs only")
    a=p.parse_args()
    if not (1<=a.rounds<=20 and 0<=a.jvm_warmup<=20 and a.rounds+a.jvm_warmup<=30 and 1<=a.repeats<=30 and 0<=a.warmup<=5):
        p.error("bounded experiment sizes required")
    main(a)
