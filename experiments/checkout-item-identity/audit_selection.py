#!/usr/bin/env python3
"""Check automatic selection against an existing compare archive, without BPF."""
import argparse
import copy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import observer
from selection_rules import automatic_plan,validate_plan,DEFAULT_QUERIES,CHECKS
from go_byte_adapter import assembly_rows
from go_string_adapter import file_offset
from hybrid_model import require


def save(path,doc):path.write_text(json.dumps(doc,indent=2)+'\n')


def audit(archive,out):
    with ZipFile(archive) as z:
        roots=[name[:-len('plan.json')] for name in z.namelist() if name.endswith('/plan.json')]
        require(len(roots)==1,'Expected one root plan')
        prefix=roots[0]
        read=lambda path:json.loads(z.read(prefix+path))
        base=read('plan.json');binary=z.read(prefix+'checkout-identity')
        require(hashlib.sha256(binary).hexdigest()==base['binary_sha256'],'Binary hash differs')
        assembly={r['address']:r for r in assembly_rows(z.read(prefix+'function.asm').decode())}
        plans={s:read('plan-'+s+'.json') for s in ('boundaries','current','dense_stores')}
        for plan in plans.values():
            require(plan['binary_sha256']==base['binary_sha256'],'Plan binary differs')
            for site in plan['sites']:
                offset=file_offset(binary,site['address']);code=bytes.fromhex(assembly[site['address']]['code'])
                require(offset==site['file_offset'] and binary[offset:offset+len(code)]==code,'Probe bytes differ')
        selected=automatic_plan(base);validate_plan(selected)
        require(selected['sites']==plans['boundaries']['sites'] and
                selected['event_order']==plans['boundaries']['event_order'],'Automatic policy differs from recorded boundary policy')
        dense_selected=automatic_plan(plans['dense_stores'])
        require(dense_selected['sites']==selected['sites'],'Denser catalog gives different required sites')
        alternatives={
            'item_only':automatic_plan(base,['identity.Item']),
            'both':selected,
            'both_with_operand_checks':automatic_plan(base,DEFAULT_QUERIES+(CHECKS,)),
        }
        for name,plan in alternatives.items():
            validate_plan(plan,executable=False);save(out/('selection-'+name+'.json'),plan)
        rows=[]
        for name in sorted(z.namelist()):
            if not name.startswith(prefix) or not name.endswith('/capture/events.json'):continue
            folder=name[len(prefix):-len('/capture/events.json')]
            sample=read(folder+'/sample.json');original=plans[sample['strategy']]
            doc=read(folder+'/capture/events.json')
            inferred=observer.infer(original,doc)
            require(inferred==read(folder+'/inference.json'),'Archived inference differs on replay')
            truth=read(folder+'/truth.json')
            observer.evaluate(inferred,truth)
            # This is an explicitly marked offline projection, not a host run
            # of a different plan. First validate the COMPLETE source capture.
            keep=set(selected['event_order']);projected=copy.deepcopy(doc)
            projected['events']=[e for e in doc['events'] if e['site'] in keep]
            n=len(projected['events'])
            projected['stats'].update(submitted=n,probe_hits=n,pid_rejections=0)
            projected_result=observer.infer(selected,projected)
            observer.evaluate(projected_result,truth)
            for key in ('inputs','error','outputs','conversions','publications'):
                require(projected_result[key]==inferred[key],'Identity query changed under projection')
            same_program=None
            if sample['strategy']=='boundaries':
                diag=doc['diagnostics'];ns=SimpleNamespace(st_dev=diag['namespace']['dev'],st_ino=diag['namespace']['ino'])
                generated=observer.source(selected,diag['target_pid'],ns)
                same_program=generated==z.read(prefix+folder+'/capture/collector.c').decode()
                require(same_program,'Generated boundary collector differs from host-validated program')
            rows.append(dict(path=folder,strategy=sample['strategy'],original_events=len(doc['events']),
                projected_events=n,offline_projection=sample['strategy']!='boundaries',
                boundary_collector_identical=same_program,identity_results_match=True))
        require(rows,'No source captures')
        report=dict(archive_sha256=hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
            binary_sha256=base['binary_sha256'],all_passed=True,captures_checked=len(rows),
            boundary_programs_identical=sum(r['boundary_collector_identical'] is True for r in rows),
            plan_site_counts={name:len(p['sites']) for name,p in alternatives.items()},
            rows=rows,bpf_executed_by_this_audit=False,
            claim='Declared dependency closure matches existing query results and boundary collector; not a new kernel experiment or general semantic proof')
        save(out/'audit.json',report)
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    out=(args.output or ROOT/'artifacts'/('selection-audit-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    report=audit(args.archive,out)
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
    print('Selection audit: '+str(out/'audit.json'))


if __name__=='__main__':main()
