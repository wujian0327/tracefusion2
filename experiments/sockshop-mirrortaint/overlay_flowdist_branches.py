#!/usr/bin/env python3
"""Attach validated Soot application branch bytecode to independent Boot copies.

Graph refinement may still be failed. This builder only validates branch
output; it explicitly declares modified application bytecode and no accuracy.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED

import flowdist_preflight as tool


def build(repo, apps, orders, shipping, out, reporter_adapter=None):
    tool.verify_repository(repo)
    manifest=json.loads((apps/'manifest.json').read_text())
    out.mkdir(parents=True,exist_ok=False)
    models={}
    reporter={}
    if reporter_adapter:
        meta=json.loads((reporter_adapter.parent/'manifest.json').read_text())
        if meta['kind']!='flowdist-repeated-report-cache-fix' or \
            hashlib.sha256(reporter_adapter.read_bytes()).hexdigest()!=meta['jar_sha256']:
            raise ValueError('Unverified reporter adapter')
        with ZipFile(reporter_adapter) as archive:
            for name in archive.namelist():
                if not name.startswith('profile/BranchReporter') or not name.endswith('.class'):
                    raise ValueError('Unexpected reporter class')
                reporter['BOOT-INF/classes/'+name]=archive.read(name)
    for role,static in (('orders',orders),('shipping',shipping)):
        source=apps/(role+'-flowdist.jar')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=manifest['apps'][role]['adapted_sha256']:
            raise ValueError('Source Spring application digest mismatch')
        config=json.loads((static/'manifest.json').read_text())
        stage=json.loads((static/'service-branches-stage.json').read_text())
        if config['role']!=role or stage['exit_code']!=0 or stage['errors']:
            raise ValueError('Unvalidated application branch stage')
        if config['shipping_jar_sha256']!=manifest['apps'][role]['original_sha256']:
            raise ValueError('Branch input differs from original Spring app')
        branches=static/'work'/('ReframedBranches' if config.get('verifier_frames_recomputed') else 'NormalizedBranches')
        overrides={}
        for file in branches.rglob('*.class'):
            relative=str(file.relative_to(branches))
            if relative!='AuxInstr.class' and not relative.startswith('works/weave/socks/'+role+'/'):continue
            data=file.read_bytes()
            if data[:4]!=b'\xca\xfe\xba\xbe':raise ValueError('Invalid branch class')
            overrides['BOOT-INF/classes/'+relative]=data
        output=out/(role+'-flowdist.jar')
        changed={}
        with ZipFile(source) as original,ZipFile(output,'w') as target:
            for entry in original.infolist():
                data=original.read(entry.filename)
                replacement=overrides.pop(entry.filename,data)
                if replacement!=data:
                    changed[entry.filename]={'before_sha256':hashlib.sha256(data).hexdigest(),
                        'after_sha256':hashlib.sha256(replacement).hexdigest()}
                target.writestr(entry,replacement)
            for name,data in overrides.items():
                if name!='BOOT-INF/classes/AuxInstr.class':raise ValueError('Unexpected new application class')
                target.writestr(name,data)
            for name,data in reporter.items():target.writestr(name,data)
            # BranchReporter runtime helpers reference Soot utility classes.
            target.writestr('BOOT-INF/lib/flowdist-original-soot-trunk.jar',
                (repo/'tool/soot-trunk.jar').read_bytes(),compress_type=ZIP_STORED)
        manifest['apps'][role]['adapted_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
        manifest['apps'][role].update(original_entries_preserved=False,
            branch_modified_entries=changed,source_spring_adapter_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        models[role]={'static_artifact':str(static),'mapping':str(branches/'entitystmt.out.branch'),
            'mapping_sha256':hashlib.sha256((branches/'entitystmt.out.branch').read_bytes()).hexdigest(),
            'statements':str(branches/'stmtids.out'),
            'statements_sha256':hashlib.sha256((branches/'stmtids.out').read_bytes()).hexdigest(),
            'graph_refinement_verified':False,
            'verifier_frames_recomputed':config.get('verifier_frames_recomputed',False),
            'author_method_instrumentation':config.get('author_method_instrumentation',False),
            'wrap_try_catch_enabled':'-wrapTryCatch' in stage['command']}
    manifest.update(branch_models=models,static_branch_instrumentation=True,
        original_business_classes_modified=True,modification='Author branch probes; bundled ASM Java 8 emission',
        static_statement_graph_verified=False,accuracy_eligible=False,performance_eligible=False)
    if reporter_adapter:manifest.update(reporter_cache_fixed=True,reporter_adapter_sha256=meta['jar_sha256'])
    if all(model['author_method_instrumentation'] for model in models.values()):
        manifest.update(method_instrumentation='original OTBetterInstr selected application enter/returnInto/returnFrom',
            spring_boundary_duplicate_enter_suppressed=True,original_main_return_and_shutdown_flush=True)
    tool.save(out/'manifest.json',manifest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('repo','apps','orders','shipping','out'):p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--reporter-adapter',type=Path)
    a=p.parse_args();build(a.repo.resolve(),a.apps.resolve(),a.orders.resolve(),a.shipping.resolve(),a.out.resolve(),
                          a.reporter_adapter.resolve() if a.reporter_adapter else None)
