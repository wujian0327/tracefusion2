#!/usr/bin/env python3
"""Recompute author's branch-to-statement union on each appended report.

The original caches its first statement array, even while branches accumulate.
Only remove that cache guard; preserve the mapping formula and original JARs.
"""
import argparse
import difflib
import hashlib
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED
import flowdist_preflight as tool


def build(repo,out):
    tool.verify_repository(repo);out.mkdir(parents=True,exist_ok=False)
    original=repo/'code/src/profile/BranchReporter.java'
    before=original.read_text()
    guard='if (stmtBinArray != null)\n\t\t\treturn;'
    if before.count(guard)!=1:raise ValueError('Unexpected statement cache guard')
    after=before.replace(guard,'// Recompute from current cumulative branch array on every report.',1)
    source=out/'BranchReporter.java';source.write_text(after)
    (out/'BranchReporter.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True))))
    classes=out/'classes';classes.mkdir()
    cp=':'.join(str(repo/'tool'/name) for name in ('FLOWDIST.jar','DUA1.jar'))
    result=subprocess.run(['javac','--release','8','-cp',cp,'-d',str(classes),str(source)],
        capture_output=True,text=True,timeout=30)
    (out/'compile.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise ValueError('Reporter adapter compilation failed')
    jar=out/'flowdist-reporter-adapter.jar'
    with ZipFile(jar,'w',ZIP_DEFLATED) as archive:
        for file in classes.rglob('*.class'):archive.write(file,str(file.relative_to(classes)))
    test=Path(__file__).parent/'flowdist/FlowDistReporterTest.java'
    tests=out/'test-classes';tests.mkdir()
    subprocess.run(['javac','--release','8','-cp',str(jar)+':'+cp,'-d',str(tests),str(test)],
        check=True,capture_output=True,timeout=30)
    fixture=out/'test-fixture';fixture.mkdir()
    check=subprocess.run(['java','-ea','-cp',':'.join(map(str,[tests.resolve(),jar.resolve()]))+':'+cp,
        'FlowDistReporterTest'],cwd=fixture,capture_output=True,text=True,timeout=30)
    (out/'test.log').write_text(check.stdout+check.stderr)
    if check.returncode:raise ValueError('Reporter cache regression failed')
    tool.save(out/'manifest.json',{'kind':'flowdist-repeated-report-cache-fix',
        'upstream_commit':tool.COMMIT,'original_source_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
        'adapted_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'jar_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),'mapping_algorithm_modified':False,
        'original_engine_jars_modified':False,'accuracy_eligible':False,'performance_eligible':False})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('repo','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();build(a.repo.resolve(),a.out.resolve())
