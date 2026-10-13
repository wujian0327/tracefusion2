#!/usr/bin/env python3
"""Restore the author's disabled branch probe calls, with identical map/probe IDs.

Build an override class in a separate JAR; preserve the upstream repository and
all analysis/branch instrumentation algorithms. This is a disclosed adaptation.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

from flowdist_preflight import verify_repository


def build(repo,out):
    verify_repository(repo);out.mkdir(parents=True,exist_ok=False)
    original=repo/'code/src/disttaint/OTBranchInst.java';before=original.read_text()
    if before.count('System.exit(0);')!=1:raise ValueError('Unexpected author run method')
    after=before.replace('System.exit(0);','rdfCDBranchAnalyzer.removeAssistantNodes();\n\t\tinstrumentAllBranches();\n\t\tinstrumentTerminate();',1)
    after=after.replace('protected SootClass clsMonitor;','protected SootClass clsMonitor;\n\tprivate List<Branch> mappedBranches;',1)
    needle='Map<Branch, Set<Stmt>> br2cdstmts ='
    if after.count(needle)!=1:raise ValueError('Unexpected branch mapping code')
    after=after.replace(needle,'mappedBranches = allBranches;\n\t\t'+needle,1)
    start=after.index('List<Branch> allBranches = rdfCDBranchAnalyzer.getAllBranches();')
    end=after.index('// instrument using DuaF facilities',start)
    after=after[:start]+'List<Branch> allBranches = mappedBranches;\n\t\tif (allBranches == null) throw new IllegalStateException("Branch mapping required");\n\t\t'+after[end:]
    # The bundled three-argument overload EXCLUDES the supplied methods (its
    # contains(method) branch skips insertion). The list is already restricted
    # to selected methods, so use the author's unfiltered two-argument overload.
    call='brInstrumenter.instrumentDirect(allBranches, ProgramFlowGraph.inst().getEntryMethods(),remoteMethods);'
    if after.count(call)!=1:raise ValueError('Unexpected instrumentDirect call')
    after=after.replace(call,'brInstrumenter.instrumentDirect(allBranches, ProgramFlowGraph.inst().getEntryMethods());',1)
    source=out/'OTBranchInst.java';source.write_text(after)
    (out/'OTBranchInst.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(original),tofile=str(source))))
    deps=out/'compile-deps'
    with ZipFile(repo/'tool/soot-trunk.jar') as z:
        for name in z.namelist():
            if name.endswith('.class') and not name.startswith('/'):
                p=deps/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
    jars=[p for p in sorted((repo/'tool').glob('*.jar')) if p.name!='soot-trunk.jar']
    classes=out/'classes';classes.mkdir()
    command=['javac','--release','8','-cp',':'.join(map(str,[deps,*jars])),'-d',str(classes),str(source)]
    p=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (out/'compile.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise ValueError('Branch adaptation compilation failed')
    jar=out/'flowdist-branch-adapter.jar'
    with ZipFile(jar,'w',ZIP_DEFLATED) as z:
        for f in sorted(classes.rglob('*.class')):z.write(f,str(f.relative_to(classes)))
    manifest={'kind':'flowdist-branch-probe-restoration','original_source_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
        'adapted_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'jar_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),
        'changes':['Restore original removeAssistantNodes/instrumentAllBranches/instrumentTerminate calls instead of early exit.',
                   'Use exactly the same selected branch list for mapping and probes to prevent index mismatch.',
                   'Use original two-argument instrumentDirect; three-argument overload excludes all selected candidate methods.'],
        'branch_algorithm_modified':False,'original_engine_jar_modified':False,'compile_command':command,
        'accuracy_eligible':False,'performance_eligible':False}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(jar)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();build(a.repo.resolve(),a.out.resolve())
