#!/usr/bin/env python3
"""Control-input experiments: invariant, modeled updates, and independent bytes."""
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
INPUT_PATTERNS=('0000','0100','0010','0110','1001','1101','1011','1111')
KILL_VARIANTS=('kill-full','kill-partial','kill-none')
COMPARISON_VARIANTS=KILL_VARIANTS+('correlated','correlated-dependent')


def stage(directory,variant='stable'):
    for name in ('go.mod','go.sum','main.go','upstream.go','downstream.go','tracing.go','client.go'):
        source=CHOICE/name if (CHOICE/name).exists() else SCENARIO/name
        shutil.copyfile(source,directory/name)
    shutil.copyfile(CHOICE/('control-inputs.go' if variant=='inputs' else 'control.go'),directory/'control.go')


def build_role(out,role,variant='stable'):
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp);stage(src,variant)
        return build(out,'assign',scenario=src,extra_sources=(role+'.go','tracing.go')+(('control.go',) if role=='downstream' else ()),
            operation_source=CHOICE/({'toggle':'toggle.go','inputs':'inputs.go','kill-full':'kill-full.go','kill-partial':'kill-partial.go',
                'correlated':'correlated.go','correlated-dependent':'correlated-dependent.go'}.get(variant,'choice.go')) if role=='downstream' else None,expected_modules=MODULES,
            planner=partial(plan_binary,cross_role=role,tracing='otel',
                runtime_inputs=[dict(register='rdi',length=4 if variant=='inputs' else 1)] if role=='downstream' else None,
                runtime_input_model='indexed-control-bytes-v1' if variant=='inputs' and role=='downstream' else None,
                observation_target='final-byte-origins-v1' if variant in COMPARISON_VARIANTS else None,
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
            expected=[]
            for i in range(4):
                local_byte=local ^ bool(i%2) if variant=='toggle' else local
                if variant=='inputs':local_byte=INPUT_PATTERNS[ticket-1][i]=='1'
                if variant in ('kill-full','correlated') or variant=='kill-partial' and i>=2:local_byte=False
                byte_name='B.txt' if local_byte else ('C.txt' if ticket%2==0 else 'A.txt')
                expected.append([['downstream' if local_byte else 'upstream',str(ticket),byte_name,i]])
            contributes='0' in INPUT_PATTERNS[ticket-1] if variant=='inputs' else True if variant=='toggle' else not local
            if variant in ('kill-full','kill-partial','correlated'):contributes=True
            require(row['byte_sources']==expected and row['transfer_contributes']==contributes,'Wrong byte origin')
        if variant=='toggle':
            for row in locals_['downstream']['results']:
                updates=row['provenance']['runtime_control_updates']
                require(len(updates)==4 and all(u['after']==(u['before']^1) for u in updates),'Wrong replayed control transitions')
                require(all(a['after']==b['before'] for a,b in zip(updates,updates[1:])),'Broken control version chain')
                require(row['provenance']['final_runtime_control']==updates[0]['before'],'Final control did not return to initial value')
        if variant=='inputs':
            for row in locals_['downstream']['results']:
                samples=[s['runtime_input_evidence'] for s in row['provenance']['instruction_steps'] if 'runtime_input_evidence' in s]
                require([s['offset'] for s in samples]==[0,0,0,1,0,2,0,3],'Missing independent input offsets')
                require(all(s['kind']=='observed-control-byte' for s in samples),'An independent input was guessed')
        if mode=='output':
            require(variant in ('kill-full','correlated'),'Unexpected output projection')
            require(all(r['provenance']['execution_history']=='not_reconstructed' and not r['provenance']['instruction_steps'] and
                        r['provenance']['total_writes'] is None for r in locals_['downstream']['results']),
                    'Unobserved execution history was fabricated')
        negative=negative_checks(locals_['upstream'],locals_['downstream'])+negative_span_checks(locals_['upstream'],locals_['downstream'],spans)
        require(all(n['passed'] for n in negative),'Negative dependency check failed')
        if mode in ('selective','entry','entry_replay'):
            doc=docs['downstream'];plan=plans['downstream'];selected=set(plan['selected_instruction_sites'])
            expected_sites=2 if mode=='selective' and variant in ('toggle','inputs') else 1
            require(len(selected)==expected_sites,'Unexpected number of selected probe sites')
            expected_events=8 if mode in ('entry','entry_replay') else 32*expected_sites
            require(sum(e['site'] in selected for e in doc['events'])==expected_events,'Unexpected number of input observations')
            for failure in ('missing','wrong_pointer','extra'):
                bad=deepcopy(doc);events=bad['events'];i=next(i for i,e in enumerate(events) if e['site'] in selected)
                if failure=='missing':events.pop(i)
                elif failure=='extra':events.insert(i,deepcopy(events[i]))
                else:
                    snap=events[i]['values']['control' if mode in ('entry','entry_replay') else 'load'];snap['pointer']+=1;snap['key']=f"{snap['pointer']:x}:1"
                for j,e in enumerate(events):e['sequence']=j
                bad['stats']['submitted']=len(events)
                result=bind_service(bad,plan);ok=result['status']=='unknown'
                negative.append(dict(case='selected_'+failure,passed=ok));require(ok,'Bad selected event accepted')
        if variant=='toggle':
            bad=deepcopy(docs['downstream'])
            v=next(e for e in bad['events'] if e['op']=='work' and e['phase']=='post')['values']['control']
            v['hex']=bytes([bytes.fromhex(v['hex'])[0]^1]).hex()
            rejected=bind_service(bad,plans['downstream'])['status']=='unknown'
            negative.append(dict(case='wrong_final_control',passed=rejected));require(rejected,'Contradictory final control accepted')
        if variant=='inputs':
            bad=deepcopy(docs['downstream']);events=bad['events']
            index=next(i for i,e in enumerate(events) if e['site'] in plans['downstream']['runtime_input_sites'] and
                       e['values']['load']['pointer']==e['registers']['rdi']+1)
            events.pop(index)
            for i,e in enumerate(events):e['sequence']=i
            bad['stats']['submitted']=len(events)
            rejected=bind_service(bad,plans['downstream'])['status']=='unknown'
            negative.append(dict(case='missing_later_input',passed=rejected));require(rejected,'Missing later input was guessed')
    require(all(c['max_active_scopes']>=2 for c in coverage.values()),'No natural concurrent scope overlap')
    report=dict(passed=True,mode=mode,signature=signature,unknown_requests=unknowns,negative_checks=negative,
        capture_counts=counts,concurrency=coverage,spans=sum(map(len,spans.values())),
        expected_behavior='unknown' if mode=='boundary' else 'resolved',inference_status=joined['status'])
    if mode=='entry':report['entry_stability']=plans['downstream']['entry_stability']
    if mode=='entry_replay':report['entry_state_replay']=plans['downstream']['entry_state_replay']
    return report


def run(out,build_only=False,variant='stable',archive_output=True):
    passed=False;reports={}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp);stage(src,variant);client=build_client(out/'build/client',scenario=src)
        plans={r:build_role(out/'build'/r,r,variant) for r in ('upstream','downstream')}
        optimized='auto' if variant=='inputs' or variant in KILL_VARIANTS else 'entry_replay' if variant=='toggle' else 'entry'
        expected_mode='selective' if variant=='inputs' else 'output' if variant=='kill-full' else 'entry' if variant in KILL_VARIANTS else optimized
        automatic={r:select_observation(p,'auto') for r,p in plans.items()}
        require(automatic['upstream']['observation_mode']=='boundary' and automatic['downstream']['observation_mode']==expected_mode,
                'Fixture no longer satisfies the expected automatic policy')
        for role,plan in automatic.items():
            save(out/'build'/role/'auto-plan.json',plan)
            save(out/'build'/role/'observation-decision.json',plan['observation_decision'])
        if variant=='toggle':
            rejected=False
            try:select_observation(plans['downstream'],'entry')
            except ValueError as exc:rejected=True;save(out/'stable-entry-rejection.json',dict(refused=True,reason=str(exc)))
            require(rejected,'Changing control input was treated as stable')
        if variant=='inputs':
            rejections=[]
            for mode in ('entry','entry_replay'):
                try:select_observation(plans['downstream'],mode)
                except ValueError as exc:rejections.append(dict(mode=mode,refused=True,reason=str(exc)))
            require(len(rejections)==2,'Independent inputs incorrectly accepted by a one-byte entry mode')
            save(out/'entry-rejections.json',rejections)
        if variant in KILL_VARIANTS:
            dependence=automatic['downstream']['observation_decision']['output_dependence']
            require(dependence['varying_output_bytes']==([] if variant=='kill-full' else [0,1] if variant=='kill-partial' else [0,1,2,3]),
                    'Wrong final-origin dependence analysis')
            save(out/'output-dependence.json',dependence)
        if build_only:passed=True;return 0
        fixture=variant if variant in ('toggle','inputs') or variant in KILL_VARIANTS else 'choice'
        modes=('full','boundary','auto') if variant=='inputs' or variant in KILL_VARIANTS else ('full','boundary','selective',optimized)
        for mode in modes:
            trial=out/mode;trial.mkdir()
            def builder(directory,role,variant):
                shutil.copytree(out/'build'/role,directory)
                plan=select_observation(plans[role],'auto' if mode==optimized else mode);plan['binary']=str(directory/'gin-byte-target')
                require(hashlib.sha256(Path(plan['binary']).read_bytes()).hexdigest()==plan['binary_sha256'],'Binary changed')
                save(directory/'plan.json',plan)
                (directory/'collector.preview.c').write_text(gin_byte_capture.source(plan,1,SimpleNamespace(st_dev=0,st_ino=0)))
                return plan
            rc=run_pair(trial,build_fn=builder,worker_script=ROOT/'scripts/gin_otel_provenance.py',
                analyze_fn=analyze,variants=(fixture,),archive_output=False,
                startup_fn=lambda role,pair,caps:dict(Service=role,TraceFile=str(caps[role]/'spans.jsonl'),ClientBinary=str(client)))
            require(rc==0,'Failed '+mode+' trial; inspect '+str(trial/'runner-error.txt'))
            reports[mode]=json.loads((trial/fixture/'evaluation.json').read_text())
        require(reports['full']['signature']==reports[optimized]['signature'],'Full/optimized origins differ')
        if variant!='inputs' and variant not in KILL_VARIANTS:require(reports['full']['signature']==reports['selective']['signature'],'Full/selective origins differ')
        save(out/'comparison.json',dict(all_passed=True,reports=reports,
            variant=variant,control_observation_events={m:reports[m]['capture_counts']['downstream']['instruction_events'] for m in (('auto',) if variant=='inputs' or variant in KILL_VARIANTS else ('selective',optimized))},
            scope=('Final byte origins under bounded copy proof; actual intermediate execution may be unreconstructed' if variant in KILL_VARIANTS else
                   'Independent private request bytes first observed inside loop; automatic per-read fallback, not loop-time I/O or minimum probes' if variant=='inputs' else
                   'Compare supported runtime reads with one initial snapshot and modeled state; private ownership and complete update model required; no minimum claim')))
        passed=True;print(json.dumps(dict(all_passed=True,boundary_unknown=8,full_resolved=8,optimized_mode=expected_mode,optimized_resolved=8)),flush=True)
    except Exception:
        error=traceback.format_exc();(out/'runner-error.txt').write_text(error);print(error,flush=True)
    finally:
        save(out/'run-status.json',dict(completed=passed,build_only=build_only))
        if not build_only and archive_output:
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
    parser.add_argument('--variant',choices=('stable','toggle','inputs')+KILL_VARIANTS,default='stable')
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    prefix={'toggle':'gin-toggle-provenance-','inputs':'gin-inputs-provenance-'}.get(args.variant,'gin-choice-provenance-')
    if args.variant in KILL_VARIANTS:prefix='gin-'+args.variant+'-provenance-'
    out=(args.output or ROOT/'artifacts'/(prefix+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    return run(out,args.command=='build',args.variant)

if __name__=='__main__':raise SystemExit(main())
