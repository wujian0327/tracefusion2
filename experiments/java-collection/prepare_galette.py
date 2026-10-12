#!/usr/bin/env python3
"""Build pinned upstream Galette and a separate instrumented JDK (never overwrite a JDK)."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from run import digest

REVISION = "bc6002cc5ee4d6eaa30518b2d176a9831d77cb1a"
URL = "https://github.com/neu-se/galette.git"


def logged(cmd, out, name, env=None, cwd=None):
    begin = time.perf_counter()
    p = subprocess.run(list(map(str, cmd)), cwd=cwd, env=env, capture_output=True, timeout=1800)
    for suffix,data in (("stdout",p.stdout),("stderr",p.stderr)):
        with (out / (name + "." + suffix + ".txt")).open("wb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
    record = dict(command=list(map(str, cmd)), returncode=p.returncode, wall_seconds=time.perf_counter()-begin)
    (out / (name + ".json")).write_text(json.dumps(record, indent=2)+"\n")
    if p.returncode: raise RuntimeError(f"{name} failed; inspect {out}/{name}.stderr.txt")
    return record


def main(a):
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    jdk = a.jdk.resolve()
    if not (jdk / "bin/javac").is_file(): raise ValueError("--jdk must name a complete JDK 17")
    source = a.source.resolve() if a.source else out / "upstream"
    report = dict(schema="galette-build-v1", status="running", revision=REVISION, repository=URL, jdk=str(jdk), steps=[])
    try:
        env = dict(os.environ, JAVA_HOME=str(jdk), PATH=str(jdk / "bin")+os.pathsep+os.environ["PATH"])
        version = subprocess.check_output([str(jdk / "bin/java"), "-version"], env=env, stderr=subprocess.STDOUT, text=True)
        if 'version "17.' not in version: raise ValueError("this comparison pins the build and runtime to JDK 17")
        report["java"] = version
        report["base_jdk_sha256"] = {p:digest(jdk/p) for p in ("release", "bin/java", "lib/modules")}
        if not a.source:
            report["steps"].append(logged(["git", "clone", URL, source], out, "clone"))
            report["steps"].append(logged(["git", "checkout", "--detach", REVISION], out, "checkout", cwd=source))
        if subprocess.check_output(["git", "rev-parse", "HEAD"],cwd=source,text=True).strip()!=REVISION:
            raise ValueError("Galette revision differs from pinned upstream")
        if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],cwd=source,text=True).strip():
            raise ValueError("Galette has modified tracked source")
        for name in ("README.md", "LICENSE", "LICENSE.md"):
            if (source/name).is_file(): shutil.copyfile(source/name,out/("upstream-"+name))
        if not a.skip_build:
            report["steps"].append(logged([a.maven,"-B","-DskipTests","-Dmaven.javadoc.skip=true",
                "-pl","galette-instrument","-am","clean","install"],out,"build",env=env,cwd=source))
        report["build_reused"] = a.skip_build
        if subprocess.check_output(["git", "diff", "--name-only"],cwd=source,text=True).strip():
            raise ValueError("upstream build modified tracked source; inspect before reuse")
        for module in ("agent", "instrument"):
            jar=source/f"galette-{module}/target/galette-{module}-1.0.0-SNAPSHOT.jar"
            shutil.copyfile(jar,out/f"galette-{module}.jar")
        report["steps"].append(logged([jdk/"bin/java", "-jar", out/"galette-instrument.jar", jdk, out/"jdk"],out,"instrument",env=env))
        report["instrumented_jdk_sha256"]={p:digest(out/"jdk"/p) for p in ("release", "bin/java", "lib/modules")}
        report["artifacts_sha256"]={p:digest(out/p) for p in ("galette-agent.jar", "galette-instrument.jar")}
        report["status"]="prepared"
    except Exception as e:
        report.update(status="failed", error=repr(e)); raise
    finally:
        (out/"preparation.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(dict(status=report["status"],directory=str(out))))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jdk",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--source",type=Path,help="existing clean checkout at pinned revision")
    p.add_argument("--maven",default="mvn")
    p.add_argument("--skip-build",action="store_true",help="reuse JARs from the pinned checkout; recorded in provenance")
    main(p.parse_args())
