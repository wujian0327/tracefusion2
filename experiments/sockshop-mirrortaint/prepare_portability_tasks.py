#!/usr/bin/env python3
"""Seal unfiltered return/property and side-effect obligations BEFORE TF planning."""
import argparse,datetime,json
from pathlib import Path
from run_portability_first import TASK_ROOT,ROLES,verify,log
from run_planned_service import load,save,sha

def leaves(bean,path=''):
    if bean.get('leaf'):return [{'path':path or '/', 'target':None,'type':bean.get('type'),'binding':'root-scalar-or-null'}]
    out=[]
    for p in bean.get('properties',[]):
        pp=path+'/'+p['property'];nested=p.get('nested');generics=p.get('generic_beans',[])
        if nested and nested.get('properties'):out+=leaves(nested,pp)
        elif generics:
            for g in generics:out+=leaves(g,pp+'/*')
        elif p.get('descriptor','').startswith('Ljava/util/') and p.get('type') not in ('java.util.Date','java.util.UUID'):
            out.append({'path':pp+'/*','target':p.get('field'),'type':p['type'],'binding':'dynamic-container-element'})
        else:out.append({'path':pp,'target':p.get('field'),'type':p['type'],'binding':'physical-field'if p.get('field')else'computed-property'})
    return out or [{'path':path or '/','target':None,'type':bean.get('type'),'binding':'dynamic-or-unresolved-return'}]

def seal(root):
    verify(root);out=root/'task-seal.json'
    if out.exists():raise ValueError('Never overwrite a sealed first task')
    methods=load(root/'discovery40.json')['entries'];entries=[]
    for row in methods:
        app=row['application'];role=ROLES[app][int(row['id'].rsplit('-',1)[1])-1];meta=load(root/'method-metadata'/row['id']/'reflection.json')['methods'];assert len(meta)==1
        m=meta[0];model=load(root/'metadata'/role/'model.json');front=[m['entry']];seen=set();effects=[];reads=[]
        while front:
            key=front.pop()
            if key in seen:continue
            seen.add(key)
            for i in model['methods'].get(key,{}).get('instructions',[]):
                if i['op']not in(182,183,184,185):continue
                call=i['owner']+'.'+i['name']+i['desc']
                if call in model['methods']:front.append(call)
                if i['name'].lower().startswith(('save','insert','update','delete','remove','send','convertandsend','publish')):effects.append({'caller':key,'site':i['index'],'callee':call,'descriptor':i['desc'],'kind':'candidate-write-or-message-sink-needs-runtime-execution-check'})
                if i['name'].lower().startswith(('find','select','query','getfor','exchange')):reads.append({'caller':key,'site':i['index'],'callee':call})
        targets=[]if m['return_generic']=='void'else leaves(m['return_bean'])
        if row['id']=='piggymetrics-5':targets=leaves(m['parameters'][1]);target_basis='Source returns the same Recipient parameter; actual runtime class and serialization still require checking'
        else:target_basis='Actual uninstrumented JAR JavaBeans reflection; NOT the TF serializer schema or planner acceptance'
        entries.append({'id':row['id'],'application':app,'role':role,'entry':m['entry'],'return_generic':m['return_generic'],'class_annotations':m['class_annotations'],'method_annotations':m['method_annotations'],'return_targets':targets,'target_selection_basis':target_basis,'effect_sink_candidates':effects,'read_source_candidates':reads,'sources':'Root entry arguments, actual DB read returns and actual RPC read returns; retain concrete message/call/object/field/version coordinates. Helper arguments are not new sources.','parameters':m['parameters'],'sink_scope':'All actual scalar/null method-return leaves plus persistence/message call arguments. Void methods retain side-effect obligations. Unexpressible sinks are target_binding_unsupported, never business N/A.','metadata_sha256':sha(root/'method-metadata'/row['id']/'reflection.json'),'model_sha256':sha(root/'metadata'/role/'model.json'),'input_rule':'Six fixed structures: normal; same value distinct instance; repeat/overwrite; empty list/map; validation/exception/absent auth; normal after failure. Concrete bodies and fixture DB frozen before each first tool run.','oracle_rule':'Review original code and raw input/database/message facts; source coordinate witnesses may be shared, no TF graph or MT tags determine expected dependencies. Unknown truth remains oracle_unavailable; no value-based instance matching.','data_dependency':'Actual data operands only; selection/control evidence separate. Constant known results have empty data source only with an independently verified execution.'})
    value={'sealed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'TF_core':load(root/'protocol-start.json')['TF_commit'],'entries':entries,'count':40,'selection':'All forty methods, all statically discoverable public return leaves and all candidate original persistence/message sink obligations. No success filtering. Dynamic/runtime-only leaves retained as unresolved obligations, not discarded.','evaluation_gate':'A field/HTTP subset cannot be promoted to full method coverage. Complete task success requires return AND original effect sinks to be verified.','first_TF_planning_not_yet_executed':True}
    save(out,value);log(root,'04-task-seal',{'sha256':sha(out),'entries':40,'return_candidates':sum(len(x['return_targets'])for x in entries),'effect_candidates':sum(len(x['effect_sink_candidates'])for x in entries)})
    print({'sealed':str(out),'sha256':sha(out)})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=TASK_ROOT);a=p.parse_args();seal(a.root)
