#!/usr/bin/env python3
"""Distributed prediction process: frozen plans and observations only."""
import argparse
from collections import defaultdict
from pathlib import Path
import sys
import traceback
from run import CORE,load,save,sha
from analyze import rows
from replay_round_two import oracle_guard
sys.path.insert(0,str(CORE))
from infer_distributed_fields import Reconstruction


def predict(build,cap,decoded=None):
    try:
        g=Reconstruction(build,cap,['A','B'],decoded_rows=decoded);queries=[]
        for r in g.rows['A']:
            if r['kind']=='http-json'and r['direction']=='response'and r['phase']=='write':
                a=g.query(r['message'],'/text','A',boundary=[{'service':'A','kind':'http-json','direction':'request','phase':'read'}]);a['path_edges']=g.path_edges(a['target_key']);queries.append(a)
        return {'state':'analyzed','queries':queries,'graph':g.export(),'local_results':g.local_queries,'oracle_consumed':False}
    except Exception as e:return {'state':'rejected','error':str(e),'type':type(e).__name__,'traceback':traceback.format_exc(),'oracle_consumed':False}


def compose_mirror(cap):
    """Disclosed reproduction of paper IV-E, NOT an author postprocessor.

    Only native IDs determine intra-JVM dependencies. Local interface tokens
    are translated across actual messages; no business opcode or TF graph is
    available here, and no upstream source IDs are installed in another JVM.
    """
    native={r:rows(cap/r/'native.jsonl')for r in ('A','B')};nodes={};edges={};tokens=defaultdict(list);writes=defaultdict(list);reads=defaultdict(list)
    for role,events in native.items():
        for i,r in enumerate(events):
            if r['kind']!='boundary':continue
            key=(role,i);nodes[key]=r
            external=role=='A'and(r['direction'],r['phase'])==('request','read')
            if external or r['local_interface_token']:
                for t in r['native_ids']:tokens[(role,t)].append(key)
            wire=(tuple(r['connection']),r['message'],r['direction'],r['path'])
            (writes if r['phase']=='write'else reads)[wire].append(key)
    for key,r in nodes.items():
        if r['phase']!='write':continue
        parents=[]
        for tag in r['native_ids']:
            found=tokens[(key[0],tag)]
            if len(found)!=1 or found[0][1]>=key[1]:return {'state':'unresolved','reason':'Ambiguous/unmapped native interface coordinate','native':native}
            parents+=found
        edges[key]=parents
    for wire,targets in reads.items():
        sources=writes.get(wire,[])
        if not sources:continue
        if len(sources)!=1 or len(targets)!=1:raise ValueError('Ambiguous native actual-message field mapping')
        s,t=sources[0],targets[0]
        if s[0]==t[0]or nodes[s]['wire_utf8']!=nodes[t]['wire_utf8']:raise ValueError('Native actual-message bytes/roles differ')
        edges[t]=[s]
    def leaves(k,trail=()):
        if k in trail:raise ValueError('Native relation cycle')
        r=nodes[k]
        if k[0]=='A'and r['direction']=='request'and r['phase']=='read':return {k},True
        if k not in edges:return set(),False
        result=set();known=True
        for p in edges[k]:
            v,ok=leaves(p,trail+(k,));result|=v;known&=ok
        return result,known
    queries=[]
    for key,r in nodes.items():
        if key[0]=='A'and r['direction']=='response'and r['phase']=='write':
            origins,known=leaves(key);queries.append({'message':r['message'],'known':known,'sources':[{'role':k[0],**nodes[k]}for k in sorted(origins)],'native_target':r,'target_key':list(key)})
    return {'state':'composed','queries':queries,'native':native,'edges':[[list(k),list(p)]for k,ps in edges.items()for p in ps],'author_postprocessor':False,'intra_service_dependencies':'public native tag IDs only','strict_version':'N/A','offline_deletion':'N/A'}


def replay(home,out):
    oracle_guard();out.mkdir(parents=True,exist_ok=False)
    for cap in sorted((home/'captures/tracefusion').glob('*/*')):
        dest=out/'tracefusion'/cap.parent.name/cap.name;dest.mkdir(parents=True);save(dest/'prediction.json',predict(home/'build/tf',cap))
    for mode in ('mirror-online','mirror-composed'):
        for cap in sorted((home/'captures'/mode).glob('*/*')):
            dest=out/mode/cap.parent.name/cap.name;dest.mkdir(parents=True)
            save(dest/'prediction.json',compose_mirror(cap)if mode=='mirror-composed'else{'state':'native_export','native':{r:rows(cap/r/'native.jsonl')for r in ('A','B')},'cross_service_calibration':'unconnected online raw tags; not paper IV-E','strict_version':'N/A'})
    save(out/'replay-receipt.json',{'current_core_sources':{str(p):sha(p)for p in CORE.iterdir()if p.suffix in ('.py','.java','.json')},'prediction_sources':{str(p):sha(p)for p in (Path(__file__),)},'oracle_consumed':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--capture',type=Path);p.add_argument('--events',type=Path);a=p.parse_args()
    if a.capture:
        oracle_guard();a.out.mkdir(parents=True,exist_ok=False);decoded={r:rows(a.events/(r+'.jsonl'))for r in ('A','B')}if a.events else None;save(a.out/'prediction.json',predict(a.run/'build/tf',a.capture,decoded))
    else:replay(a.run.resolve(),a.out.resolve())
