"""Capture-scoped immutable field versions; request execution State remains local.

Only verified replay can publish a write. Values are consistency checks, never
lookup keys. A missing exact version stays unknown. No process-global cache.
"""
from dataclasses import dataclass
import hashlib
import json
from execution_dependency_state import Value
from query_observation_planner import require
from infer_execution_kernel import coordinate, same_value


@dataclass(frozen=True)
class Version:
    namespace: tuple
    coordinate: tuple
    observed_json: str
    origins: frozenset
    selectors: frozenset
    unknown: bool
    write_seq: int
    frame: str
    site: str
    descriptor: str
    completion: str
    support: tuple
    dependency_complete: bool
    effects_complete: bool

    def value(self):
        return Value(json.loads(self.observed_json),self.origins,self.selectors,self.unknown)


class SessionHistory:
    def __init__(self,plan,rows):
        self.config=plan['session_history'];version=self.config.get('version');require(version in (1,2),'Unsupported session history plan')
        require(self.config.get('scope')==('sequential-http-external-input-and-application-roots'if version==1 else'sequential-http-intermediate-input-and-application-roots'),'Unsupported session history scope')
        if version==2:
            require(plan.get('http_exchange',{}).get('input_role')=='intermediate','Historical HTTP dependencies need an intermediate boundary')
            from http_exchange_protocol import validate_local
            validate_local(plan,rows)
        require(not plan.get('response_binding',{}).get('source_calls'),'Session history excludes method-return sources')
        require(not any(r['kind']=='http-rpc-enter'for r in rows),'Session history excludes outbound RPC')
        require(rows and rows[0]['kind']=='start','Session history start absent')
        header=rows[0];self.namespace=(header.get('capture_session'),header.get('process_instance'))
        require(header.get('plan_sha256')==hashlib.sha256((json.dumps(plan,indent=2)+'\n').encode()).hexdigest(),'Frozen session history plan differs')
        require(all(isinstance(x,str) and x for x in self.namespace),'Session history namespace absent')
        require([r['seq']for r in rows]==list(range(1,len(rows)+1)),'Session history event sequence gap')
        require(all(r.get('session_history_version')==version and (r.get('capture_session'),r.get('process_instance'))==self.namespace for r in rows),'Session history capture/process identity differs')
        footers=[r for r in rows if r['kind']=='metrics'];require(len(footers)==1 and footers[0].get('session_history_event_count')==len(rows),'Session history event count differs')
        require(header.get('mode')=='full'and not any(r['kind']=='problem'or r.get('capture_invalid')for r in rows),'Invalid session history capture')
        from transport_context import validate_protocol
        validate_protocol(rows)
        self.roots=set(self.config['roots']);require(plan['entry']in self.roots,'Query entry absent from session roots')
        require(self.roots<=set(plan['execution_kernel']['methods']),'Session root bytecode absent')
        self.versions={};self.reads=[];self.bindings=[];self.barriers={};self.rows={r['seq']:r for r in rows}
        self.external={}
        for row in rows:
            if row['kind']=='http-json' and row.get('direction')=='request' and row.get('phase')=='read':
                require(row.get('message'),'External source HTTP identity absent')
                for field in row['fields']:
                    key=(row['message'],coordinate(field));self.external.setdefault(key,[]).append((row,field))
        for row in rows:
            if row['kind']=='binding-input':
                for field in row['fields']:self.input(row,field,row['seq']+1)
        self.root_intervals=[]

    def root(self,start,end):
        require(start['method']in self.roots and start.get('parent')is None,'Session roots must be real top-level invocations')
        require(not self.root_intervals or self.root_intervals[-1][1]<start['seq'],'Overlapping session roots unsupported')
        self.root_intervals.append((start['seq'],end['seq'],start['frame']))

    def input(self,row,field,before):
        # Duplicate method snapshots are aliases of ONE actual external field,
        # never new sources and never selected by equal payload values.
        matches=[(r,f)for r,f in self.external.get((row.get('message'),coordinate(field)),[])if r['seq']<row['seq']<before]
        if len(matches)!=1:return Value(field['observed'],unknown=True)
        source,physical=matches[0];same_value(physical['observed'],field['observed'])
        require(physical['observed']==field['observed'],'External input field value/reference changed without a counted write')
        require(physical.get('descriptor')==field.get('descriptor'),'External source field descriptor differs')
        name=field['field'];origin=('http',source['seq'],physical['path'])
        fact={'namespace':list(self.namespace),'binding_seq':row['seq'],'source_seq':source['seq'],'source_path':physical['path'],'coordinate':list(coordinate(field)),'frame':row['frame']}
        if fact not in self.bindings:self.bindings.append(fact)
        if name in self.config['data_fields']:return Value(field['observed'],frozenset({origin}))
        if name in self.config['control_fields']:return Value(field['observed'],selectors=frozenset({origin}))
        return Value(field['observed'],unknown=True)

    def lookup(self,field,before,root_frame):
        if 'capture_session'in field or 'process_instance'in field:
            require((field.get('capture_session'),field.get('process_instance'))==self.namespace,'Foreign session/process historical read')
        key=(self.namespace,coordinate(field));record=self.versions.get(key)
        if record is None:return None
        require(record.write_seq<before,'Historical read precedes establishing write')
        same_value(record.value().observed,field['observed'])
        if record.descriptor.startswith(('L','[')):require(record.value().observed.get('object')==field['observed'].get('object'),'Historical reference identity differs')
        require(record.descriptor==field.get('descriptor'),'Historical field descriptor differs')
        value=record.value()
        if self.barriers.get(field['owner'],-1)>=record.write_seq:value=Value(field['observed'],unknown=True)
        if field.get('kind')=='read':
            proof={'namespace':list(self.namespace),'read_seq':field['seq'],'root_frame':root_frame,'coordinate':list(record.coordinate),
                   'write_seq':record.write_seq,'write_frame':record.frame,'known':not value.unknown,'origins':[list(x)for x in sorted(value.origins,key=str)]}
            if proof not in self.reads:self.reads.append(proof)
        return value,record.write_seq

    def publish(self,write,value,completion,support=()):
        coord=coordinate(write);key=(self.namespace,coord)
        require(key not in self.versions,'Historical field version established twice')
        require(write['kind']=='write'and write.get('descriptor'),'Historical write requires actual value/descriptor evidence')
        require(write['version']>0,'Historical write version invalid')
        require(self.rows.get(write['seq']) is write,'Historical write belongs to another evidence stream')
        require((write.get('capture_session'),write.get('process_instance'))==self.namespace,'Foreign session/process historical write')
        require(completion in ('normal','aborted'),'Historical completion missing')
        complete=completion=='normal' and self.barriers.get(write['owner'],-1)<write['seq']
        record=Version(self.namespace,coord,json.dumps(value.observed,sort_keys=True),frozenset(value.origins),frozenset(value.selectors),value.unknown or not complete,
                       write['seq'],write['frame'],write['site'],write['descriptor'],completion,tuple(support),not value.unknown,complete)
        self.versions[key]=record

    def invalidate(self,owners,seq):
        # A prior root may have published a reference that the current local
        # State has not read yet. Unknown effects must cross those historical
        # edges too. Retaining old edges is deliberately conservative.
        pending=list(owners);seen=set()
        while pending:
            owner=pending.pop()
            if owner in seen:continue
            seen.add(owner);self.barriers[owner]=max(seq,self.barriers.get(owner,-1))
            for record in self.versions.values():
                if record.coordinate[0]!=owner or record.write_seq>=seq:continue
                observed=json.loads(record.observed_json)
                if observed.get('object')and 'value'not in observed:pending.append(observed['object'])

    def export(self):
        return {'version':self.config['version'],'origin_scope':'external-http-input'if self.config['version']==1 else'service-local-http-intermediate-dependency','namespace':list(self.namespace),'bindings':self.bindings,'reads':self.reads,
                'versions':[{'namespace':list(v.namespace),'coordinate':list(v.coordinate),'observed':json.loads(v.observed_json),
                  'origins':[list(x)for x in sorted(v.origins,key=str)],'selectors':[list(x)for x in sorted(v.selectors,key=str)],'known':not v.unknown,
                  'write_seq':v.write_seq,'frame':v.frame,'site':v.site,'descriptor':v.descriptor,'completion':v.completion,'support':list(v.support),
                  'dependency_complete_at_publish':v.dependency_complete,'effects_complete_at_publish':v.effects_complete}for v in self.versions.values()],
                'effect_barriers':dict(self.barriers)}
