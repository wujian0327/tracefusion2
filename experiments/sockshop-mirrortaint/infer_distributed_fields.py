#!/usr/bin/env python3
"""Application-independent field-instance graph over frozen code and observations.

No query oracle, business names, request labels, value-based joins or inferred
network correlations. Unbound boundaries remain visible in graph leaves.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from infer_planned_service import infer_service
from query_observation_planner import require
from transport_context import validate_protocol
from infer_collection_service import infer_collection
from infer_execution_kernel import infer_execution
import infer_response_binding as response_binding


def coord(f):return (f['owner'],f['field'],f['version'])
def equivalent(a,b):
    if 'date_epoch_ms' in a or 'date_epoch_ms' in b:return all(a.get(k)==b.get(k) for k in ('date_epoch_ms','date_type'))
    return a.get('value')==b.get('value')


class Reconstruction:
    def __init__(self,build,root,roles,decoded_rows=None):
        self.nodes={};self.edges={};self.rows={};self.plans={};self.providers=defaultdict(list);self.unpaired=[]
        self.stats={};self.local_queries={};self.root_return_messages={}
        for role in roles:
            plan=json.loads((build/role/'plan.json').read_text());path=root/role/'events.jsonl'
            rows=decoded_rows[role] if decoded_rows is not None else [json.loads(l) for l in path.read_text().splitlines()]
            require([r['seq'] for r in rows]==list(range(1,len(rows)+1)),'Event sequence gap')
            require(not any(r['kind']=='problem' or r['kind']=='metrics' and r.get('capture_invalid') for r in rows),'Collector problem')
            require(not path.with_name(path.name+'.invalid').exists(),'Collector failure sidecar')
            require(sum(r['kind']=='metrics' for r in rows)==1,'Capture did not close')
            require(rows[0]['plan_sha256']==hashlib.sha256((build/role/'plan.json').read_bytes()).hexdigest(),'Frozen plan differs')
            if any(r.get('transport_protocol')=='w3c-trace-context' for r in rows):validate_protocol(rows)
            self.rows[role]=rows;self.plans[role]=plan
            returns=defaultdict(list)
            for row in rows:
                if row['kind']=='binding-return':returns[row['frame']].append(row.get('message'))
            # Retain every candidate. Duplicate returns are not resolved by
            # insertion order, including equal-message duplicates.
            self.root_return_messages[role]=returns
            from infer_date_projection import validate_date_serialization
            validate_date_serialization(plan,rows)
            from infer_scalar_projection import validate as validate_scalar_projection
            validate_scalar_projection(plan,rows)
            from infer_uuid_projection import validate_uuid_projection
            validate_uuid_projection(plan,rows)
            self.stats[role]={'events':len(rows),'json_events':sum(r['kind']=='http-json' for r in rows),'log_bytes':path.stat().st_size}
        self.json=[]
        for role,rows in self.rows.items():
            for r in rows:
                if r['kind']!='http-json':continue
                require(r['message'] and r['direction'] in ('request','response') and r['phase'] in ('read','write'),'Invalid transport context')
                paths=set()
                for f in r['fields']:
                    require(f['path'] not in paths,'Repeated JSON pointer');paths.add(f['path'])
                    schema_field=f.get('schema_field',f['field']);owner=schema_field.rsplit('.',1)[0];ps=[p for p in self.plans[role]['json_schema'][owner] if p['field']==schema_field]
                    require(len(ps)==1,'Unknown property')
                    suffix=ps[0]['property'].replace('~','~0').replace('/','~1')
                    if f['field'].startswith(('@list:','@map:')):
                        require(self.plans[role].get('collection_elements'),'Collection fields not admitted')
                        require('/'+suffix+'/' in f['path'],'Collection parent property mismatch')
                        leaf=f['field'].split(':',1)[1].replace('~','~0').replace('/','~1')
                        require(f['path'].endswith('/'+leaf),'Collection key/index pointer mismatch')
                    else:require(f['path'].endswith('/'+suffix),'JSON pointer/property mismatch')
                    key=(role,r['seq'],f['path']);node=dict(f,service=role,seq=r['seq'],kind='http-json',root_frame=r.get('frame'),message=r['message'],direction=r['direction'],phase=r['phase'],uri=r.get('uri'),parent_message=r.get('parent_message'))
                    self.add(key,node);self.json.append((key,r))
                    if r['phase']=='read':self.providers[(role,coord(f))].append(key)
        self.bridge()
        for role in self.plans:response_binding.sources(self,role)
        for role in self.plans:self.conversions(role)
        for role,plan in self.plans.items():
            if plan['profile']=='mapped-reduction':self.reductions(role,build,root)
            if plan['profile']=='field-copy':self.copies(role)
            if plan['profile'] in ('collection-computation','bounded-scalar'):self.collections(role)
            if plan['profile']=='execution-dependency':self.executions(role)
        for role in self.plans:response_binding.bind_outputs(self,role)
        # Same-process forwarding is only the same object/field/version. It does
        # not use matching payloads or business keys. Multiple candidates fail
        # closed rather than selecting the latest or an equal-valued candidate.
        for key,r in self.json:
            if r['phase']=='write':
                binding=self.plans[key[0]].get('response_binding')
                if binding and response_binding.matches(binding['path'],self.nodes[key]['path']):continue
                self.alias(key)

    def add(self,key,node,edges=None):
        require(key not in self.nodes,'Duplicate evidence node');self.nodes[key]=node
        if edges is not None:self.edges[key]=list(edges)
    def alias(self,key):
        n=self.nodes[key];possible=[k for k in self.providers[(n['service'],coord(n))] if self.nodes[k]['seq']<n['seq']]
        if self.plans[n['service']].get('response_binding'):
            frame=n.get('root_frame',n.get('frame'))
            root_messages=self.root_return_messages[n['service']].get(frame,[])
            require(len(root_messages)<=1,'Ambiguous root-return message for alias binding')
            message=n.get('message') or (root_messages[0]if root_messages else None)
            possible=[k for k in possible if (
                self.nodes[k].get('root_frame',self.nodes[k].get('frame'))==frame and frame is not None
                or self.nodes[k]['kind']=='http-json' and self.nodes[k].get('direction')=='response'
                and self.nodes[k].get('parent_message')==message and message is not None)]
        if len(possible)==1:
            if not equivalent(self.nodes[possible[0]]['observed'],n['observed']):
                n['unknown']='Value changed outside counted application writes; no forwarding edge';return
            self.edges[key]=possible
        elif len(possible)>1:n['unknown']='Multiple same-coordinate provider observations'
    def bridge(self):
        writes=defaultdict(list);reads=defaultdict(list)
        groups=defaultdict(dict)
        for key,r in self.json:
            group=(r['message'],r['direction'],r['phase']);role=key[0];event=(role,r['seq'])
            if group in groups and groups[group] and event not in groups[group]:raise ValueError('Duplicate transport event for same message/phase')
            groups[group][event]=True
            (writes if r['phase']=='write' else reads)[(r['message'],r['direction'],self.nodes[key]['path'])].append(key)
        for binding,receivers in reads.items():
            sources=writes.get(binding,[])
            if not sources:
                self.unpaired.append({'message':binding[0],'direction':binding[1],'path':binding[2]});continue
            require(len(sources)==len(receivers)==1,'Ambiguous message/property bridge')
            source,target=sources[0],receivers[0];s,t=self.nodes[source],self.nodes[target]
            require(s['service']!=t['service'],'Remote binding stayed in one service')
            if binding[1]=='response' and not any(r.get('transport_protocol')=='w3c-trace-context' for r in self.rows[t['service']]):
                row=next(r for r in self.rows[t['service']] if r['seq']==t['seq'])
                require(row.get('echo')==binding[0],'Missing/mismatched response message echo')
            require(equivalent(s['observed'],t['observed']),'JSON property changed; never rematch by value')
            self.edges[target]=[source]
    def reductions(self,role,build,root):
        p=self.plans[role];r=infer_service(p,root/role/'events.jsonl',rows=self.rows[role]);self.local_queries[role]=r
        entries={v['frame']:v for v in self.rows[role] if v['kind']=='enter'};exits={v['frame']:v for v in self.rows[role] if v['kind']=='exit'}
        for a in r['answers']:
            calc=entries[a['basis']['producer']];end=exits[a['root_frame']];leaves=[]
            fields={coord(f):f for item in calc['inputs'] for f in item['fields']}
            for owner,name,version in a['sources']:
                f=fields[(owner,name,version)];key=(role,'input',calc['frame'],owner,name,version)
                if key not in self.nodes:self.add(key,dict(f,service=role,seq=calc['seq'],kind='input-snapshot'));self.alias(key)
                leaves.append(key)
            key=(role,'reduction',a['root_frame'],a['field']);target=next(f for f in end['fields'] if f['field']==a['field'])
            self.add(key,dict(target,service=role,seq=end['seq'],kind='bytecode-reduction',root_frame=a['root_frame']),leaves)
            self.providers[(role,coord(target))].append(key)
    def copies(self,role):
        p=self.plans[role];rows=self.rows[role];entries={r['frame']:r for r in rows if r['kind']=='enter'};exits={r['frame']:r for r in rows if r['kind']=='exit'}
        for writer in entries.values():
            rule=next((v for v in p['copy_rules'] if v['writer']==writer['method'] and v['callsite']==writer.get('callsite')),None)
            if rule is None:continue
            root=entries.get(writer['parent']);require(root and root['method']==p['entry'],'Field-copy caller differs from static binding')
            require(writer['frame'] in exits and root['frame'] in exits,'Unclosed field-copy frame')
            writes=[r for r in rows if r['kind']=='write' and r['frame']==writer['frame'] and r['site']==rule['write_site'] and r['field']==rule['field']]
            require(len(writes)==1 and writes[0]['owner']==writer['receiver'],'Target field write differs')
            write=writes[0];source=rule['source'];leaves=[]
            if source['kind']=='constant':require(write['observed'].get('value')==source['value'],'Constant assignment differs')
            elif source['kind']=='field-read':
                reads=[r for r in rows if r['kind']=='read' and r['frame']==root['frame'] and r['site']==source['site'] and r['field']==source['field'] and r['seq']<writer['seq']]
                require(len(reads)==1,'Field-copy getter instance ambiguous');read=reads[0]
                require(read['observed']['object']==writer['args'][rule['parameter']]['object']==write['observed']['object'],'Getter/parameter/write identity differs')
                key=(role,'getter',read['seq']);self.add(key,dict(read,service=role,kind='field-read'));self.alias(key);leaves=[key]
            elif source['kind']=='argument':
                arg=root['args'][source['index']];require(arg['object']==writer['args'][rule['parameter']]['object']==write['observed']['object'],'Root argument/write identity differs')
                key=(role,'argument',root['frame'],source['index']);self.add(key,dict(service=role,seq=root['seq'],kind='argument',field='@argument:'+str(source['index']),owner=arg['object'],version=0,observed=arg));leaves=[key]
            key=(role,'copy-write',write['seq']);self.add(key,dict(write,service=role,kind='bytecode-copy',root_frame=root['frame'],constant=source['kind']=='constant'),leaves);self.providers[(role,coord(write))].append(key)
    def collections(self,role):
        result=infer_collection(self.plans[role],self.rows[role]);self.local_queries[role]=result
        fields={coord(f):f for f in result['fields']}
        for answer in result['answers']:
            leaves=[]
            for coordinate in answer['sources']:
                coordinate=tuple(coordinate);f=fields[coordinate];key=(role,'collection-input',answer['root_frame'],*coordinate)
                if key not in self.nodes:
                    # Reads are anchored before the completed root's output;
                    # only actual preceding HTTP reads can bind the coordinate.
                    self.add(key,dict(f,service=role,seq=answer['seq'],kind='input-snapshot',root_frame=answer['root_frame']));self.alias(key)
                leaves.append(key)
            key=(role,'collection-result',answer['root_frame'],answer['field'])
            if self.plans[role]['profile']=='bounded-scalar':key+= (answer['version'],answer['seq'])
            node=dict(answer,service=role,kind='bytecode-collection')
            if not answer['known']:node['unknown']='Opaque scalar or unsupported effect reached the target'
            self.add(key,node,leaves);self.providers[(role,coord(answer))].append(key)
    def executions(self,role):
        result=infer_execution(self.plans[role],self.rows[role]);self.local_queries[role]=result
        self.execution_outputs=getattr(self,'execution_outputs',{})
        for answer in result['answers']:
            key=(role,'execution-result',answer['seq'],answer['path'])
            leaves=[]
            for origin in answer['origins']:
                if len(origin)==2:seq,index=origin;leaves.append((role,'binding-source',seq,index))
                elif origin[0]=='field':leaves.append((role,'binding-source',origin[1],origin[2]))
                elif origin[0]=='http':leaves.append((role,origin[1],origin[2]))
                else:
                    require(origin[0]=='argument','Unknown execution origin type');frame,index=origin[1:];argument_key=(role,'argument',frame,index)
                    if argument_key not in self.nodes:
                        root=next(r for r in self.rows[role] if r['kind']=='enter' and r['frame']==frame);arg=root['args'][index]
                        self.add(argument_key,dict(service=role,seq=root['seq'],kind='argument',root_frame=frame,message=next((r.get('message') for r in self.rows[role] if r['kind']=='binding-return' and r['frame']==frame),None),field='@argument:'+str(index),owner=arg.get('object'),version=0,observed=arg))
                    leaves.append(argument_key)
            require(all(k in self.nodes for k in leaves),'Execution source witness absent from graph')
            node=dict(answer,service=role,kind='bytecode-execution')
            if not answer['known']:node['unknown']='Necessary unmodeled dependency/effect in execution'
            self.add(key,node,leaves)
            self.execution_outputs[(role,answer['seq'],answer['path'])]=key
    def conversions(self,role):
        for row in self.rows[role]:
            if row['kind']!='json-conversion':continue
            require(self.plans[role].get('json_conversion_methods'),'Undeclared JSON conversion')
            source={f['path']:f for f in row['input']};target={f['path']:f for f in row['output']}
            require(len(source)==len(row['input']) and len(target)==len(row['output']),'Duplicate conversion pointer')
            for path,f in target.items():
                if path not in source:continue
                s=source[path];require(equivalent(s['observed'],f['observed']),'Conversion scalar coercion unsupported')
                src=(role,'conversion-input',row['seq'],path);dst=(role,'conversion-output',row['seq'],path)
                self.add(src,dict(s,service=role,seq=row['seq'],kind='input-snapshot',root_frame=row.get('frame')));self.alias(src)
                self.add(dst,dict(f,service=role,seq=row['seq'],kind='json-conversion',root_frame=row.get('frame')),[src]);self.providers[(role,coord(f))].append(dst)
    def origins(self,key,trail=(),boundary=None):
        require(key not in trail,'Provenance cycle')
        n=self.nodes[key]
        boundaries=boundary if isinstance(boundary,list) else [boundary] if boundary is not None else []
        if any(all(n.get(k)==v for k,v in b.items()) for b in boundaries):return [key],True
        if n.get('unknown'):return [],False
        if key not in self.edges:
            unbound=n['kind']=='input-snapshot' or (n['kind']=='http-json' and n['phase']=='read')
            return [key],boundary is None and not unbound
        origins=set();known=True
        for parent in self.edges[key]:
            values,ok=self.origins(parent,trail+(key,),boundary);origins.update(values);known&=ok
        return sorted(origins,key=str),known
    def query(self,message,path,role,boundary=None):
        binding=self.plans[role].get('response_binding')
        if binding:require(response_binding.matches(binding['path'],path),'Query path outside frozen response binding')
        candidates=[key for key,r in self.json if key[0]==role and r['message']==message and r['phase']=='write' and r['direction']=='response' and self.nodes[key]['path']==path]
        require(len(candidates)==1,'Query target absent or duplicated: '+str((role,message,path)))
        key=candidates[0];origins,known=self.origins(key,boundary=boundary)
        return {'target':self.nodes[key],'target_key':list(key),'known':known,'sources':[self.nodes[k] for k in origins],'source_keys':[list(k) for k in origins]}
    def path_edges(self,key):
        seen=set();edges=[]
        def visit(k):
            if k in seen:return
            seen.add(k)
            for parent in self.edges.get(k,[]):edges.append([list(k),list(parent)]);visit(parent)
        visit(tuple(key));return edges
    def export(self):return {'nodes':[{'key':list(k),**n} for k,n in self.nodes.items()],'edges':[[list(k),list(p)] for k,ps in self.edges.items() for p in ps],
        'stats':self.stats,'unpaired_transport_properties':self.unpaired,'origin_matching_uses_values':False,'transport_matching':'validated W3C trace-id + concrete request span-id + direction + JSON pointer' if any(r.get('transport_protocol')=='w3c-trace-context' for rows in self.rows.values() for r in rows) else 'legacy message UUID', 'origin_matching_uses_trace_id_alone':False,'oracle_consumed':False}
