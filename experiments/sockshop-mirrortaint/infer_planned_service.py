#!/usr/bin/env python3
"""Same offline identity/version reconstructor for full and automatic observations.

Values only check arithmetic consistency. They never join a producer to a target
or select field origins. Neither fixtures nor expected field names are imported.
"""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
from query_observation_planner import require


def f32(v):return struct.unpack('f',struct.pack('f',v))[0]
def evaluate(e,fields,summed=None):
    op=e['op']
    if op=='constant':return f32(e['value']) if e.get('constant_type')=='Float' else e['value']
    if op=='field':
        v=fields[e['field']]['observed']['value'];return f32(v) if e['descriptor']=='F' else v
    if op=='sum':return summed
    if op=='convert':
        v=evaluate(e['arg'],fields,summed)
        if e['opcode'] in (134,137,144):return f32(v)
        if e['opcode'] in (135,138,141):return float(v)
        raise ValueError('Unmodeled conversion')
    if op=='binary':
        a,b=[evaluate(v,fields,summed) for v in e['args']];n=e['opcode']
        if n in (96,97,98,99):v=a+b
        elif n in (100,101,102,103):v=a-b
        elif n in (104,105,106,107):v=a*b
        elif n in (108,109,110,111):v=a/b
        else:raise ValueError('Unmodeled arithmetic')
        return f32(v) if n in (98,102,106,110) else v
    raise ValueError('Unmodeled scalar expression')


def infer_service(plan,path,rows=None):
    if rows is None:
        raw=Path(path).read_bytes();rows=[json.loads(l) for l in raw.splitlines()];log_bytes=len(raw)
    else:log_bytes=Path(path).stat().st_size
    require(rows and rows[0]['kind']=='start','Capture start missing')
    require([r['seq'] for r in rows]==list(range(1,len(rows)+1)),'Observation sequence gap')
    require(not any(r['kind']=='problem' for r in rows),'Failed collection')
    require(len([r for r in rows if r['kind']=='metrics'])==1,'Capture did not close')
    mode=rows[0]['mode'];require(mode in ('full','selective','boundary'),'Unknown mode')
    require(rows[0]['plan_sha256']==hashlib.sha256((json.dumps(plan,indent=2)+'\n').encode()).hexdigest(),'Frozen plan differs')
    entries={};exits={};aborts=set();events=defaultdict(list);stacks=defaultdict(list)
    versions={};writes=[]
    for r in rows:
        kind=r['kind'];frame=r.get('frame');thread=r['thread']
        if kind=='enter':
            require(frame not in entries and r['parent']==(stacks[thread][-1] if stacks[thread] else None),'Broken frame identity')
            entries[frame]=r;stacks[thread].append(frame)
        elif kind in ('exit','abort'):
            require(stacks[thread] and stacks[thread].pop()==frame,'Broken frame return')
            if kind=='exit':exits[frame]=r
            else:aborts.add(frame)
        if frame:events[frame].append(r)
        if kind=='write':writes.append(r)
        if kind in ('read','write'):
            loc=(r['owner'],r['field']);v=r['version']
            if loc in versions:require(v==versions[loc]+(kind=='write'),'Observed field version discontinuity')
            versions[loc]=v
    require(not any(stacks.values()),'Unclosed frames')
    children=defaultdict(list)
    for frame,e in entries.items():children[e['parent']].append(e)
    answers=[];rejected=[]
    for frame,root in entries.items():
        if root['method']!=plan['entry']:continue
        if frame in aborts:
            rejected.append({'root_frame':frame,'trace_id':root.get('trace_id'),'status':'no-completed-target'});continue
        require(frame in exits,'Root result missing')
        if plan['profile']=='identity-return':
            result=exits[frame];require(result['result']['object']==root['input_object'],'Identity-return object replaced')
            before=[f for f in root['input_fields'] if f['field']==plan['target']]
            after=[f for f in result['fields'] if f['field']==plan['target']]
            require(len(before)==len(after)==1 and before==after,'Identity-return field changed')
            require(before[0]['owner']==root['input_object'],'Input field owner differs')
            answers.append({'root_frame':frame,'trace_id':root.get('trace_id'),'owner':root['input_object'],'field':plan['target'],
                'version':after[0]['version'],'sources':[[root['input_object'],plan['target'],before[0]['version']]],
                'status':'resolved','basis':{'input_argument':plan['input_argument']},'source_boundary':'root-entry DTO field version'})
            continue
        calc=[e for e in children[frame] if e['method']==plan['producer_method']]
        ctor=[e for e in children[frame] if e['method']==plan['writer_method']]
        require(len(calc)==len(ctor)==1,'Producer/writer invocation ambiguity')
        calc,ctor=calc[0],ctor[0]
        require(calc['callsite']==plan['producer_callsite'] and ctor['callsite']==plan['writer_site'],'Wrong def-use call site')
        require(calc['frame'] in exits and ctor['frame'] in exits and calc['seq']<exits[calc['frame']]['seq']<ctor['seq'],'Missing ordered producer/writer')
        operands=ctor['args'];require(operands[plan['writer_parameter']]['value']==exits[calc['frame']]['result']['value'],'Scalar operand contradicts static binding')
        inputs=calc['inputs'];callbacks=[e for e in children[calc['frame']]]
        require(all(e['method']==plan['reduction']['mapper_method'] for e in callbacks),'Unexpected scalar callback')
        require([e['args'][0]['object'] for e in callbacks]==[i['object'] for i in inputs],'Callback/member identity or order differs')
        reduction_events=events[calc['frame']];before=[r for r in reduction_events if r['kind']=='sum-enter'];after=[r for r in reduction_events if r['kind']=='sum-exit']
        require(len(before)==len(after)==1 and not before[0]['parallel'],'Unmodeled reduction')
        origins=set();returns=[]
        for callback,item in zip(callbacks,inputs):
            require(callback['frame'] in exits,'Callback result missing')
            require(before[0]['seq']<callback['seq']<exits[callback['frame']]['seq']<after[0]['seq'],'Callback outside reduction epoch')
            fields={f['field']:f for f in item['fields']}
            for name in plan['mapper_fields']:
                require(name in fields and fields[name]['owner']==item['object'],'Missing source field snapshot')
                origins.add((item['object'],name,fields[name]['version']))
            # All admitted application writes, including counter-only selected
            # hooks, are guarded against source mutation throughout this epoch.
            require(not any(w['owner']==item['object'] and calc['seq']<w['seq']<exits[calc['frame']]['seq'] for w in writes),'Source mutated after snapshot')
            if mode=='full':
                reads=[r for r in events[callback['frame']] if r['kind']=='read']
                require([r['site'] for r in reads]==list(plan['field_read_sites']),'Full mapper trace differs from decoded reads')
                for r in reads:require(r['owner']==item['object'] and r['version']==fields[r['field']]['version'],'Mapper read a different field version')
            computed=evaluate(plan['reduction']['mapper_expression'],fields);actual=exits[callback['frame']]['result']['value']
            require(math.isfinite(actual) and computed==actual,'Mapper replay mismatch');returns.append(actual)
        summed=after[0]['value'];require(math.fsum(returns)==summed,'Unsupported numeric reduction')
        amount=evaluate(plan['expression'],{},summed)
        require(amount==f32(exits[calc['frame']]['result']['value']),'Producer replay mismatch')
        written=[r for r in events[ctor['frame']] if r['kind']=='write' and r['field']==plan['target']]
        require(len(written)==1 and written[0]['site']==plan['write_site'] and written[0]['owner']==ctor['receiver'],'Wrong target write')
        result=exits[frame];require(result['result']['object']==ctor['receiver'],'Repository replaced target instance')
        target=[f for f in result['fields'] if f['owner']==ctor['receiver'] and f['field']==plan['target']]
        require(len(target)==1 and target[0]['version']==written[0]['version'] and f32(target[0]['observed']['value'])==amount,'Target changed after modeled write')
        answers.append({'root_frame':frame,'trace_id':root.get('trace_id'),'owner':ctor['receiver'],'field':plan['target'],
                        'version':target[0]['version'],'sources':[list(v) for v in sorted(origins)],'status':'resolved',
                        'basis':{'producer':calc['frame'],'writer':ctor['frame'],'callbacks':[c['frame'] for c in callbacks]},
                        'source_boundary':'producer-entry DTO field versions'})
    return {'mode':mode,'answers':answers,'rejected_roots':rejected,'events':len(rows),'data_events':sum(r['kind'] not in ('class','start','metrics') for r in rows),
            'field_events':sum(r['kind'] in ('read','write') for r in rows),'branch_events':sum(r['kind']=='branch' for r in rows),
            'snapshot_field_records':sum(len(i['fields']) for e in entries.values() for i in e.get('inputs',[]))+sum(len(e.get('input_fields',[])) for e in entries.values())+sum(len(e.get('fields',[])) for e in exits.values()),
            'log_bytes':log_bytes,'hook_metrics':next(r for r in rows if r['kind']=='metrics'),
            'oracle_consumed':False,'origin_matching_uses_values':False,'origin_matching_uses_trace_ids':False}
