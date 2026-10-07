#!/usr/bin/env python3
"""Control-byte experiment: full / boundary / selective / stable entry snapshot."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import traceback
from types import SimpleNamespace
import zipfile

from hybrid_provenance import ROOT,save
from hybrid_model import require
from gin_byte_provenance import build
from gin_byte_adapter import plan_binary,select_observation
from gin_byte_boundaries import group_events
from gin_cross_boundaries import bind_service
from gin_cross_provenance import run as run_pair,negative_checks
from gin_default_boundaries import default_scheduler
from gin_otel_provenance import SCENARIO,MODULES,build_client
from gin_otel_boundaries import read_spans,span_chains,stitch_otel,negative_span_checks
from gin_otel_compare import comparison_signature
import gin_byte_capture

CHOICE=ROOT/'scenarios/gin-choice-provenance'


def stage(directory):
    for name in ('go.mod','go.sum','main.go','upstream.go','downstream.go','tracing.go','client.go'):
        source=CHOICE/name if (CHOICE/name).exists() else SCENARIO/name
        shutil.copyfile(source,directory/name)


def build_role(out,role):
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp);stage(src)
        return build(out,'assign',scenario=src,extra_sources=(role+'.go','tracing.go'),
            operation_source=CHOICE/'choice.go' if role=='downstream' else None,expected_modules=MODULES,
            planner=partial(plan_binary,cross_role=role,tracing='otel',
                runtime_inputs=[dict(register='rdi',length=1)] if role=='downstream' else None,
                runtime_input_ownership='request-private' if role=='downstream' else None))


def individual_unknowns(doc,plan):
    groups,_=group_events(doc,plan);rows=[]
    for group in groups:
        single=deepcopy(doc);single['events']=deepcopy(group)
        for i,e in enumerate(single['events']):e['sequence']=i
        single['stats']['submitted']=len(group)
        result=bind_service(single,plan)
        rows.append(dict(status=result['status'],reason=result.get('reason'),
            passed=result['status']=='unknown' and 'Missing runtime input observation' in result.get('reason','')))
    return rows


def analyze(pair,plans,captures,variant):
    mode=plans['downstream']['observation_mode'];locals_={};docs={};counts={};coverage={}
    for role,cap in captures.items():
        doc=json.loads((cap/'events.json').read_text());docs[role]=doc
        groups,peak=group_events(doc,plans[role])
        require(len(groups)==8,'Expected eight complete request scopes')
        coverage[role]=dict(max_active_scopes=peak,migrated_requests=sum(len({e['tid'] for e in g})>1 for g in groups))
        metadata=[json.loads(line) for line in (cap/'target.stdout').read_text().splitlines()]
        require(len(metadata)==2 and default_scheduler(metadata[0].get('scheduler')) and
                default_scheduler(metadata[1].get('scheduler_final')),'Scheduler override or missing metadata')
        locals_[role]=bind_service(doc,plans[role]);save(cap/'inference.json',locals_[role])
        counts[role]=dict(events=len(doc['events']),instruction_events=sum(e['op']=='instruction' for e in doc['events']),
            physical_probes=doc['diagnostics']['physical_probes'])
    spans=read_spans(captures);chains=span_chains(spans);require(len(chains)==8,'Incomplete SDK chain')
    joined=stitch_otel(locals_['upstream'],locals_['downstream'],spans);save(pair/'joined.json',joined)
    responses=json.loads((captures['downstream']/'client-responses.json').read_text())
    require(len(responses)==8 and {r['ticket'] for r in responses}==set(range(1,9)),'Client request coverage')
    require(all(r['status']==200 and json.loads(r['body'])=={'result':[83,65,77,69]} for r in responses),'HTTP result changed')
    require(locals_['upstream']['status']=='resolved','Upstream reconstruction failed')
    negative=[];signature=None;unknowns=[]
    if mode=='boundary':
        require(joined['status']=='unknown','Boundary mode guessed a source')
        unknowns=individual_unknowns(docs['downstream'],plans['downstream'])
        require(len(unknowns)==8 and all(r['passed'] for r in unknowns),'Expected missing-control evidence for every request')
    else:
        require(joined['status']=='resolved','Reconstruction failed: '+str(joined.get('reason')))
        signature=comparison_signature(pair)
        require(len(signature)==8,'Missing request origin')
        for row in signature:
            ticket=row['ticket'];local=ticket%4>=2
            name='B.txt' if local else ('C.txt' if ticket%2==0 else 'A.txt')
            expected=[[[('downstream' if local else 'upstream'),str(ticket),name,i]] for i in range(4)]
            require(row['byte_sources']==expected and row['transfer_contributes']==(not local),'Wrong byte origin')
        negative=negative_checks(locals_['upstream'],locals_['downstream'])+negative_span_checks(locals_['upstream'],locals_['downstream'],spans)
        require(all(n['passed'] for n in negative),'Negative dependency check failed')
        if mode in ('selective','entry'):
            doc=docs['downstream'];plan=plans['downstream'];selected=set(plan['selected_instruction_sites'])
            require(len(selected)==1,'Expected one selected probe site')
            expected_events=8 if mode=='entry' else 32
            require(sum(e['site'] in selected for e in doc['events'])==expected_events,'Unexpected number of input observations')
            for failure in ('missing','wrong_pointer','extra'):
                bad=deepcopy(doc);events=bad['events'];i=next(i for i,e in enumerate(events) if e['site'] in selected)
                if failure=='missing':events.pop(i)
                elif failure=='extra':events.insert(i,deepcopy(events[i]))
                else:
                    snap=events[i]['values']['control' if mode=='entry' else 'load'];snap['pointer']+=1;snap['key']=f"{snap['pointer']:x}:1"
                for j,e in enumerate(events):e['sequence']=j
                bad['stats']['submitted']=len(events)
                result=bind_service(bad,plan);ok=result['status']=='unknown'
                negative.append(dict(case='selected_'+failure,passed=ok));require(ok,'Bad selected event accepted')
    require(all(c['max_active_scopes']>=2 for c in coverage.values()),'No natural concurrent scope overlap')
    report=dict(passed=True,mode=mode,signature=signature,unknown_requests=unknowns,negative_checks=negative,
        capture_counts=counts,concurrency=coverage,spans=sum(map(len,spans.values())),
        expected_behavior='unknown' if mode=='boundary' else 'resolved',inference_status=joined['status'])
    if mode=='entry':report['entry_stability']=plans['downstream']['entry_stability']
    return report


def run(out,build_only=False):
    passed=False;reports={}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp);stage(src);client=build_client(out/'build/client',scenario=src)
        plans={r:build_role(out/'build'/r,r) for r in ('upstream','downstream')}
        automatic={r:select_observation(p,'auto') for r,p in plans.items()}
        require(automatic['upstream']['observation_mode']=='boundary' and automatic['downstream']['observation_mode']=='entry',
                'Fixture no longer satisfies the expected automatic policy')
        for role,plan in automatic.items():
            save(out/'build'/role/'auto-plan.json',plan)
            save(out/'build'/role/'observation-decision.json',plan['observation_decision'])
        if build_only:passed=True;return 0
        for mode in ('full','boundary','selective','entry'):
            trial=out/mode;trial.mkdir()
            def builder(directory,role,variant):
                shutil.copytree(out/'build'/role,directory)
                plan=select_observation(plans[role],'auto' if mode=='entry' else mode);plan['binary']=str(directory/'gin-byte-target')
                require(hashlib.sha256(Path(plan['binary']).read_bytes()).hexdigest()==plan['binary_sha256'],'Binary changed')
                save(directory/'plan.json',plan)
                (directory/'collector.preview.c').write_text(gin_byte_capture.source(plan,1,SimpleNamespace(st_dev=0,st_ino=0)))
                return plan
            rc=run_pair(trial,build_fn=builder,worker_script=ROOT/'scripts/gin_otel_provenance.py',
                analyze_fn=analyze,variants=('choice',),archive_output=False,
                startup_fn=lambda role,pair,caps:dict(Service=role,TraceFile=str(caps[role]/'spans.jsonl'),ClientBinary=str(client)))
            require(rc==0,'Failed '+mode+' trial; inspect '+str(trial/'runner-error.txt'))
            reports[mode]=json.loads((trial/'choice/evaluation.json').read_text())
        require(reports['full']['signature']==reports['selective']['signature']==reports['entry']['signature'],'Full/selective/entry origins differ')
        save(out/'comparison.json',dict(all_passed=True,reports=reports,
            control_observation_events={m:reports[m]['capture_counts']['downstream']['instruction_events'] for m in ('selective','entry')},
            scope='Compare four per-comparison observations with one entry snapshot, conditional on checked leaf stores and declared private ownership; no global minimum claim'))
        passed=True;print(json.dumps(dict(all_passed=True,boundary_unknown=8,full_resolved=8,selective_resolved=8,entry_resolved=8)),flush=True)
    except Exception:
        error=traceback.format_exc();(out/'runner-error.txt').write_text(error);print(error,flush=True)
    finally:
        save(out/'run-status.json',dict(completed=passed,build_only=build_only))
        if not build_only:
            archive=out.with_suffix('.zip')
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for p in sorted(out.rglob('*')):
                    if not p.is_file():continue
                    rel=p.relative_to(out)
                    if rel.parts[0]!='build' and p.name=='gin-byte-target':continue
                    z.write(p,p.relative_to(out.parent))
            if os.geteuid()==0 and os.environ.get('SUDO_UID','').isdigit():os.chown(archive,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
            print('Return this archive: '+str(archive),flush=True)
    return int(not passed)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('build','run'))
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    out=(args.output or ROOT/'artifacts'/('gin-choice-provenance-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    return run(out,args.command=='build')

if __name__=='__main__':raise SystemExit(main())
