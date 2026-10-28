#!/usr/bin/env python3
"""Mutate only in-memory/copy evidence; check source/target ambiguity rejection."""
import argparse,copy,json,shutil
from pathlib import Path
from run_planned_service import load,save
from run_portability_first import TASK_ROOT
from run_mirror_capability_probe import read_events,native_answer

def run(root,out):
    out.mkdir(parents=True);home=root/'tool-runs/piggymetrics-2/mirrortaint/fixed-adapter';(out/'role').symlink_to(home/'capture',target_is_directory=True);rows=read_events(out,'role');case=load(home/'results.json')['cases'][0];msg=case['message'];base=native_answer(rows,msg,'/name');assert base['state']=='known';target=next(r for r in rows if r['kind']=='target'and r['context'].get('message')==msg);source=next(r for r in rows if r['kind']=='source'and r['root']==target['root']and r['call']=='@argument:0');username=next(f for f in source['fields']if f['path']=='/username');expected={('@argument:0',source['ordinal'],'/username',username['owner'],username['field'],username['version'])};assert{tuple(s)for s in base['sources']}==expected
    checks=[]
    def trial(name,mutate,required):
        rs=copy.deepcopy(rows);t=next(r for r in rs if r['kind']=='target'and r['context'].get('message')==msg);mutate(rs,t);a=native_answer(rs,msg,'/name');assert a['state']==required,(name,a);checks.append({'check':name,'state':a['state'],'passed':True})
    trial('Missing actual serialized field cannot create empty answer',lambda rs,t:t.update(wire_fields=[]),'unknown')
    trial('Duplicate request target is not resolved by choosing first',lambda rs,t:rs.append(copy.deepcopy(t)),'evidence_invalid')
    trial('Equal value different target object identity is rejected',lambda rs,t:next(f for f in t['fields']if f['path']=='/name').update(owner='equal-value-wrong-object'),'unknown')
    def ambiguous(rs,t):
        s=next(s for s in rs if s['kind']=='source'and s['root']==t['root']and s['call']=='@argument:0');other=copy.deepcopy(next(f for f in s['fields']if f['path']=='/username'));other.update(owner='equal-value-other-object');s['fields'].append(other)
    trial('Ambiguous source coordinates are not selected by value',ambiguous,'unknown')
    rs=copy.deepcopy(rows);t=next(r for r in rs if r['kind']=='target'and r['context'].get('message')==msg);s=next(r for r in rs if r['kind']=='source'and r['root']==t['root']and r['call']=='@argument:0');password=next(f for f in s['fields']if f['path']=='/password');next(f for f in t['fields']if f['path']=='/name')['native_ids']=password['native_ids'];a=native_answer(rs,msg,'/name');assert a['state']=='known'and{tuple(s)for s in a['sources']}!=expected;checks.append({'check':'Independent username oracle catches wrong password source, does not copy predicted tag','state':'known_wrong_detected','passed':True})
    rs=copy.deepcopy(rows);t=next(r for r in rs if r['kind']=='target'and r['context'].get('message')==msg);next(f for f in t['fields']if f['path']=='/name')['tag_present']=False;a=native_answer(rs,msg,'/name');assert a['state']=='unknown';checks.append({'check':'Absent native tag stays unknown, not known empty','passed':True})
    alias=out/'missing-close';(alias/'role').mkdir(parents=True);shutil.copyfile(home/'capture/instances.jsonl',alias/'role/instances.jsonl');(alias/'role/native-capability.jsonl').write_text('\n'.join(json.dumps(r)for r in rows if r['kind']!='closed')+'\n')
    try:read_events(alias,'role')
    except AssertionError:checks.append({'check':'Capture without close rejected','passed':True})
    else:raise AssertionError('Missing close accepted')
    save(out/'checks.json',{'checks':checks,'raw_captures_modified':False,'scope':'Scoring/source identity controls only; not new independent business executions'});print({'checks':len(checks),'passed':True})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=TASK_ROOT);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
