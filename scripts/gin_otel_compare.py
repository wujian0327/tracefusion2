#!/usr/bin/env python3
"""Paired full/boundary probe pilot using identical Gin binaries and fixtures."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import traceback
from types import SimpleNamespace
import zipfile

from hybrid_provenance import ROOT,save
from hybrid_model import require
from gin_byte_adapter import select_observation
from gin_byte_provenance import VARIANTS
from gin_cross_provenance import run as run_pair
from gin_otel_provenance import build_role,build_client,analyze_pair
from lineage_graph import backward_nodes
import gin_byte_capture


def comparison_signature(pair):
    """Use client ticket only to compare runs, never to infer provenance."""
    responses=json.loads((pair/'downstream/capture/client-responses.json').read_text())
    tickets={r['trace']:r['ticket'] for r in responses}
    joined=json.loads((pair/'joined.json').read_text())
    require(joined['status']=='resolved','Incomplete joined provenance')
    rows=[]
    for row in joined['results']:
        graph=row['graph'];nodes={n['id']:n for n in graph['nodes']};positions=[]
        for index in range(4):
            sink='downstream/request:%d:output-byte:%d'%(row['downstream_request'],index)
            require(sink in nodes,'Missing final output position')
            keep=backward_nodes(graph['edges'],[sink],{'data','same-slice-response-write','http-json-field'})
            origins=[]
            for nid in keep:
                node=nodes[nid]
                if node['kind']!='source-byte':continue
                source=nid.split('/byte:')[0]
                if source not in nodes or nodes[source]['kind']!='source':continue
                origins.append([source.split('/')[0],*Path(nodes[source]['path']).parts[-2:],node['byte']])
            positions.append(sorted(origins))
        rows.append(dict(ticket=tickets[row['request_trace']],body=row['body'],byte_sources=positions,
                         transfer_contributes=row['transfer_contributes']))
    return sorted(rows,key=lambda r:r['ticket'])


def summarize(trials):
    require(trials and len(trials)%2==0,'Incomplete paired trials')
    for i in range(0,len(trials),2):
        a,b=trials[i:i+2]
        require(a['round']==b['round'] and {a['mode'],b['mode']}=={'full','boundary'},'Unpaired trial order')
        require(a['signature']==b['signature'],'Full/boundary byte origins differ')
        require(a['binary_sha256']==b['binary_sha256'],'Compared different binaries')
    modes={}
    for mode in ('full','boundary'):
        selected=[t for t in trials if t['mode']==mode]
        modes[mode]=dict(runs=len(selected),events=sum(t['events'] for t in selected),
            instruction_events=sum(t['instruction_events'] for t in selected),
            per_run_physical_probes=[t.get('physical_probes') for t in selected],
            per_run_mean_request_ms=[t['mean_request_ms'] for t in selected],
            median_run_mean_request_ms=statistics.median(t['mean_request_ms'] for t in selected))
    full=modes['full'];boundary=modes['boundary']
    return dict(all_passed=True,paired_runs=len(trials)//2,modes=modes,
        event_reduction_fraction=1-boundary['events']/full['events'],
        boundary_to_full_latency_ratio=boundary['median_run_mean_request_ms']/full['median_run_mean_request_ms'],
        timing_scope='Repeated eight-request/four-worker fixture per variant; HTTP round trip, includes cold connections; excludes build/attach/analysis',
        limitation='Pilot relative comparison, not throughput, absolute eBPF overhead, or a production benchmark; OTel enabled in both modes')


def run(out,rounds):
    trials=[];passed=False;binary_index={}
    try:
        client=build_client(out/'build/client')
        templates={}
        for variant in VARIANTS:
            for role in ('upstream','downstream'):
                print('Building shared binary '+variant+'/'+role,flush=True)
                path=out/'build'/variant/role
                templates[variant,role]=build_role(path,role,variant)
                binary_index[templates[variant,role]['binary_sha256']]=str((path/'gin-byte-target').relative_to(out))
        for repetition in range(rounds):
            order=('full','boundary') if repetition%2==0 else ('boundary','full')
            for mode in order:
                trial=out/'trials'/('round-%02d-%s'%(repetition+1,mode));trial.mkdir(parents=True)
                def builder(directory,role,variant):
                    template=out/'build'/variant/role
                    shutil.copytree(template,directory)
                    plan=select_observation(templates[variant,role],mode)
                    plan['binary']=str(directory/'gin-byte-target')
                    require(hashlib.sha256(Path(plan['binary']).read_bytes()).hexdigest()==plan['binary_sha256'],'Binary changed')
                    save(directory/'plan.json',plan)
                    (directory/'collector.preview.c').write_text(gin_byte_capture.source(plan,1,SimpleNamespace(st_dev=0,st_ino=0)))
                    return plan
                print('Trial %d/%d: %s'%(repetition+1,rounds,mode),flush=True)
                rc=run_pair(trial,build_fn=builder,worker_script=ROOT/'scripts/gin_otel_provenance.py',
                    analyze_fn=analyze_pair,archive_output=False,
                    startup_fn=lambda role,pair,captures:dict(Service=role,TraceFile=str(captures[role]/'spans.jsonl'),ClientBinary=str(client)))
                require(rc==0,'Trial failed: '+str(trial))
                evaluation=json.loads((trial/'evaluation.json').read_text());reports=evaluation['variants']
                require(evaluation['all_passed'],'Failed correctness or coverage gate')
                counts=[c for r in reports for c in r['capture_counts'].values()]
                row=dict(round=repetition+1,mode=mode,events=sum(c['events'] for c in counts),
                    instruction_events=sum(c['instruction_events'] for c in counts),
                    physical_probes=sum(c['physical_probes'] for c in counts),
                    mean_request_ms=statistics.mean(r['request_timing']['mean_ms'] for r in reports),
                    binary_sha256={v+'/'+role:templates[v,role]['binary_sha256'] for v in VARIANTS for role in ('upstream','downstream')},
                    signature={v:comparison_signature(trial/v) for v in VARIANTS})
                if mode=='boundary':require(row['instruction_events']==0,'Boundary trial captured internal events')
                trials.append(row);save(out/'trials.json',trials)
        report=summarize(trials);save(out/'comparison.json',report);passed=True
        print(json.dumps(report),flush=True)
    except Exception:
        (out/'runner-error.txt').write_text(traceback.format_exc())
        print(traceback.format_exc(),flush=True)
    finally:
        save(out/'run-status.json',dict(completed=passed))
        save(out/'binary-index.json',dict(by_sha256=binary_index,
            note='Archive stores shared binaries in build/ once; copied trial binaries omitted, plans retain original host paths'))
        archive=out.with_suffix('.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(out.rglob('*')):
                if not p.is_file():continue
                rel=p.relative_to(out)
                if rel.parts[0]=='trials' and p.name=='gin-byte-target':continue
                z.write(p,p.relative_to(out.parent))
        if os.geteuid()==0 and os.environ.get('SUDO_UID','').isdigit():
            os.chown(archive,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
        print('Return this archive: '+str(archive),flush=True)
    return int(not passed)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rounds',type=int,default=4);p.add_argument('--output',type=Path)
    args=p.parse_args();require(2<=args.rounds<=10 and args.rounds%2==0,'Use an even number of rounds from 2 to 10')
    out=(args.output or ROOT/'artifacts'/('gin-otel-compare-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    return run(out,args.rounds)

if __name__=='__main__':raise SystemExit(main())
