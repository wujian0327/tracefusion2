#!/usr/bin/env python3
"""Collect real branch coverage and method traces in the same author execution.

Uses a disclosed branch-restoration override and restricted JDK-body settings.
This remains a compatibility diagnostic, not a qualified Sock Shop comparison.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import flowdist_preflight as tool
from normalize_flowdist_class_literals import run as normalize_tree
from audit_flowdist_coverage import coverage


def run(repo,scope,branch_adapter,socket_adapter,out):
    tool.verify_repository(repo)
    manifest=json.loads((branch_adapter.parent/'manifest.json').read_text())
    digest=hashlib.sha256(branch_adapter.read_bytes()).hexdigest()
    if manifest['kind']!='flowdist-branch-probe-restoration' or manifest['jar_sha256']!=digest:
        raise ValueError('Unverified branch adapter')
    out.mkdir(parents=True,exist_ok=False);work=out/'work';work.mkdir()
    for name in ('classes','data'):shutil.copytree(scope/'work'/name,work/name)
    for name in ('methodList.out','coveredMethods.txt','Message_PassingAPIList.txt'):shutil.copyfile(scope/'work'/name,work/name)
    shutil.copyfile(branch_adapter,work/'branch-adapter.jar')
    tool.save(out/'manifest.json',{'kind':'flowdist-simultaneous-method-branch-runtime',
        'upstream_commit':tool.COMMIT,'branch_adapter_sha256':digest,'scope_input':str(scope),
        'method_scope_sha256':hashlib.sha256((work/'methodList.out').read_bytes()).hexdigest(),
        'jdk_library_bodies_excluded':True,'original_engine_jar_modified':False,
        'accuracy_eligible':False,'performance_eligible':False})
    restrict=['-no-bodies-for-excluded','-exclude','java.*','-exclude','javax.*',
              '-exclude','sun.*','-exclude','com.sun.*']
    args=tool.static_args('OTBranchInst','OTBranchInstrumented')
    args[3]='/work/branch-adapter.jar:'+args[3]
    args+=['-slicectxinsens','-wrapTryCatch','-intraCD','-interCD','-exInterCD',*restrict]
    tool.execute(repo,out,'branch-probe-instrumentation',args)
    normalize_tree(work/'OTBranchInstrumented',work/'BranchInput')
    args=tool.static_args('OTBetterInstr','OTMethodInstrumented')
    args[7]='/usr/lib/jvm/java-1.8-openjdk/jre/lib/rt.jar:/work/BranchInput:/flowdist/tool/FLOWDIST.jar:/flowdist/tool/soot-trunk.jar'
    args[args.index('-process-dir')+1]='/work/BranchInput'
    tool.execute(repo,out,'method-on-branches',args+['-socket',*restrict])
    normalize_tree(work/'OTMethodInstrumented',work/'OTInstrumented')
    print(tool.runtime(repo,out,socket_adapter)['status'],flush=True)
    mapping=[set(map(int,row.split())) for row in (work/'OTBranchInstrumented/entitystmt.out.branch').read_text().splitlines()]
    size=len((work/'OTBranchInstrumented/stmtids.out').read_text().splitlines())
    reports={}
    for role in ('server','client'):
        branches,statements=coverage(work/'runtime'/role/'stmtCoverage1.out',mapping,size)
        reports[role]={'branches_hit':len(branches),'statements_hit':len(statements)}
    tool.save(out/'measured-coverage.json',{'roles':reports,'branch_count':len(mapping),
        'statement_count':size,'cross_pass_alignment_verified':False,
        'accuracy_eligible':False,'performance_eligible':False})
    print(tool.stage(repo,out,'cross-method-analysis')['status'],flush=True)
    print(tool.inspect_traces(repo,out)['status'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('repo','scope','branch-adapter','socket-adapter','out'):p.add_argument('--'+flag,type=Path,required=True)
    a=p.parse_args();run(a.repo.resolve(),a.scope.resolve(),a.branch_adapter.resolve(),a.socket_adapter.resolve(),a.out.resolve())
