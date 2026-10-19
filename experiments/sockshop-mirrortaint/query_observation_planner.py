#!/usr/bin/env python3
"""Query-driven observation planning from a bounded application JVM model.

Enumerate acyclic application paths, derive field-origin expressions and kill sets,
then cover pairs of paths with different query answers using distinguishing branch
facts. Sufficiency is relative to the admitted model, not a general Java proof.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re

MAX_PATHS=256
MAX_DEPTH=12
READONLY_EXTERNAL={
    'java/lang/ThreadLocal.get()Ljava/lang/Object;',
    'java/lang/Boolean.booleanValue()Z',
}


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def require(test,message):
    if not test:raise ValueError(message)
def descriptors(desc):return re.findall(r'\[*L[^;]+;|\[*[ZBCSIJFD]',desc[1:desc.index(')')])
def scalar(desc):return desc in ('Z','B','C','S','I','J','F','D','Ljava/lang/String;')
def const(value):return {'op':'constant','value':value}
def unknown(reason):return {'op':'unknown','reason':reason}
def ref(name,owner):return {'op':'reference','ref':name,'owner':owner}
def source(name,field):return {'op':'source','ref':name,'field':field}


def sources(expr):
    if expr['op']=='source':return {(expr['ref'],expr['field'])},False
    if expr['op']=='unknown':return set(),True
    leaves=set();missing=False
    for arg in expr.get('args',[]):
        values,opaque=sources(arg);leaves|=values;missing|=opaque
    return leaves,missing


class Analyzer:
    def __init__(self,model,entry):
        self.model=model;self.entry=entry;self.methods=model['methods'];self.classes=model['classes']
        require(entry in self.methods,'Entry method is absent')
        self.reachable=set();self.path_count=0
        self.root=self.methods[entry];self.arguments=[]
        require(self.root['name']!='<init>','Constructor root boundaries are unsupported')
        if not self.root['access']&8:self.arguments.append('L'+self.root['owner']+';')
        self.arguments+=descriptors(self.root['desc'])

    def start(self):
        args=[ref('arg:'+str(i),d[1:-1]) if d.startswith('L') and d!='Ljava/lang/String;' else source('arg:'+str(i),'@argument') for i,d in enumerate(self.arguments)]
        state={'heap':{},'versions':{},'trace':[],'allocations':{},'steps':0}
        return self.execute(self.entry,args,state,[],self.entry)

    def execute(self,key,args,initial,trail,context):
        require(key not in trail and len(trail)<MAX_DEPTH,'Recursive/deep application call: '+key)
        method=self.methods[key];require(not method['try_catches'],'Exception handlers are outside the admitted model: '+key)
        require(method['instructions'],'Native/empty application method: '+key)
        require(not method['access']&32,'Synchronized method requires a stronger concurrency model')
        self.reachable.add(key);trail=trail+[key];code=method['instructions']
        locals_={};slot=0
        if not method['access']&8:locals_[0]=args[0];slot=1;args=args[1:]
        for desc,arg in zip(descriptors(method['desc']),args):
            locals_[slot]=arg;slot+=2 if desc in ('J','D') else 1
        work=[(0,[],locals_,copy.deepcopy(initial),set())];returns=[]
        while work:
            pc,stack,locals_,state,visited=work.pop()
            require(pc not in visited,'Loop/back edge is outside the admitted model: '+key)
            require(0<=pc<len(code),'Control leaves decoded method')
            require(len(work)+len(returns)<MAX_PATHS,'Path bound exceeded')
            visited=visited|{pc};state['steps']+=1;require(state['steps']<=4096,'Instruction bound exceeded')
            n=code[pc];op=n['op'];site=key+'@'+str(pc)
            def pop():
                require(stack,'Abstract operand stack underflow at '+site);return stack.pop()
            if op in (21,22,23,24,25):stack.append(copy.deepcopy(locals_.get(n['var'],unknown('undefined-local'))))
            elif op in (54,55,56,57,58):locals_[n['var']]=pop()
            elif op==1:stack.append(const(None))
            elif 2<=op<=8:stack.append(const(op-3))
            elif op in (9,10):stack.append(const(op-9))
            elif 11<=op<=13:stack.append(const(float(op-11)))
            elif op in (14,15):stack.append(const(float(op-14)))
            elif op in (16,17):stack.append(const(n['operand']))
            elif op==18:
                require(n['constant_type'] in ('String','Integer','Float','Long','Double'),'Unsupported constant')
                stack.append(const(n['constant']))
            elif op==89:stack.append(copy.deepcopy(stack[-1]))
            elif op==87:pop()
            elif op==187:
                allocation='allocation:'+context+'@'+str(pc)
                state['allocations'][allocation]=n['type'];stack.append(ref(allocation,n['type']))
            elif op==192:pass
            elif op==178:stack.append(unknown('ambient-static:'+n['owner']+'.'+n['name']))
            elif op in (180,181):
                value=pop() if op==181 else None;owner=pop()
                require(owner['op']=='reference','Unresolved heap owner at '+site)
                field=n['owner']+'.'+n['name'];location=(owner['ref'],field)
                require(scalar(n['desc']),'Nested/reference DTO fields need an explicit alias model: '+field)
                if op==181:
                    state['heap'][location]=copy.deepcopy(value);state['versions'][location]=state['versions'].get(location,0)+1
                else:
                    value=state['heap'].get(location)
                    if value is None:
                        value=source(owner['ref'],field) if owner['ref'].startswith('arg:') else const(None if n['desc']=='Ljava/lang/String;' else 0)
                    stack.append(copy.deepcopy(value))
                state['trace'].append({'kind':'write' if op==181 else 'read','site':site,'ref':owner['ref'],'field':field,
                                       'version_offset':state['versions'].get(location,0)})
            elif op in (96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111):
                right,left=pop(),pop();stack.append({'op':'arithmetic:'+str(op),'args':[left,right]})
            elif 133<=op<=147:
                stack.append({'op':'convert:'+str(op),'args':[pop()]})
            elif op in (182,183,184,185):
                parameters=[pop() for _ in descriptors(n['desc'])][::-1]
                if op!=184:parameters.insert(0,pop())
                callee=n['owner']+'.'+n['name']+n['desc'];ret=n['desc'].split(')')[1]
                if callee in self.methods:
                    require(op in (183,184) or self.classes[n['owner']]['access']&16 or self.methods[callee]['access']&(16|2),
                            'Unresolved virtual dispatch: '+callee)
                    child_returns=self.execute(callee,parameters,state,trail,context+'>'+site)
                    for child,value in child_returns:
                        child_stack=copy.deepcopy(stack)
                        if ret!='V':child_stack.append(value)
                        work.append((pc+1,child_stack,copy.deepcopy(locals_),child,set(visited)))
                    continue
                if callee=='java/lang/Object.<init>()V':
                    require(parameters and parameters[0]['op']=='reference','Unknown constructor receiver')
                elif callee in READONLY_EXTERNAL:
                    stack.append(unknown('readonly-external:'+callee))
                else:raise ValueError('Missing external effect/return model: '+callee)
            elif 153<=op<=166 or op in (198,199):
                condition=[pop()]
                if 159<=op<=166:condition.insert(0,pop())
                require(n['target']>pc,'Loop/back branch is unsupported')
                for taken in (False,True):
                    fork=copy.deepcopy(state);fork['trace'].append({'kind':'branch','site':site,'taken':taken})
                    work.append((n['target'] if taken else pc+1,copy.deepcopy(stack),copy.deepcopy(locals_),fork,set(visited)))
                continue
            elif op==167:
                require(n['target']>pc,'Loop/back jump is unsupported');work.append((n['target'],stack,locals_,state,visited));continue
            elif 172<=op<=177:
                value=None if op==177 else pop();require(not stack,'Nonempty return operand stack');returns.append((state,value));continue
            else:raise ValueError('Unsupported opcode '+str(op)+' at '+site)
            work.append((pc+1,stack,locals_,state,visited))
        return returns


def resolve_target(model,text):
    owner,field=text.rsplit('.',1);matches=[]
    for name,cls in model['classes'].items():
        canonical_name=name.replace('/','.').replace('$','.')
        if name!=owner and name.replace('/','.')!=owner and canonical_name!=owner and not canonical_name.endswith('.'+owner):continue
        for row in cls['fields']:
            if row['name']==field and not row['access']&8:matches.append((name+'.'+field,row['desc']))
    require(len(matches)==1,'Target field is absent or ambiguous: '+text)
    require(scalar(matches[0][1]),'Target type unsupported by scalar profile: '+matches[0][1]+' for '+text)
    return matches[0][0]


def abstract_answer(state,targets,arguments):
    result=[]
    for target in targets:
        owner=target.rsplit('.',1)[0]
        refs=['arg:'+str(i) for i,d in enumerate(arguments) if d=='L'+owner+';']
        require(refs,'Target owner must be a root object argument in this version: '+target)
        for name in refs:
            location=(name,target);expr=state['heap'].get(location,source(name,target));leaves,opaque=sources(expr)
            result.append({'target_ref':name,'field':target,'version_offset':state['versions'].get(location,0),
                           'sources':[list(v) for v in sorted(leaves)],'unknown':opaque})
    return result


def projected_trace(state,sites):
    return [{k:v for k,v in row.items() if k in ('kind','site','taken','ref','field','version_offset')}
            for row in state['trace'] if row['site'] in sites]


def plan(model,entry,targets):
    targets=sorted({resolve_target(model,t) for t in targets});analyzer=Analyzer(model,entry)
    returns=analyzer.start();states=[r[0] for r in returns]
    answers=[abstract_answer(s,targets,analyzer.arguments) for s in states]
    full_sites={r['site'] for s in states for r in s['trace']}
    mandatory={r['site'] for s in states for r in s['trace'] if r['kind']=='write' and r['field'] in targets}
    require(mandatory,'No reachable target field write')
    branches=sorted({r['site'] for s in states for r in s['trace'] if r['kind']=='branch'})
    pairs={(i,j) for i in range(len(states)) for j in range(i+1,len(states))
           if answers[i]!=answers[j] and projected_trace(states[i],mandatory)==projected_trace(states[j],mandatory)}
    original_pairs=len(pairs);selected=set();coverage={}
    for site in branches:
        coverage[site]={(i,j) for i,j in pairs if projected_trace(states[i],{site})!=projected_trace(states[j],{site})}
    while pairs:
        site=max(branches,key=lambda b:(len(coverage[b]&pairs),b))
        require(coverage[site]&pairs,'Available branch evidence cannot distinguish different answers')
        selected.add(site);pairs-=coverage[site]
    for site in sorted(selected):
        other=selected-{site}
        uncovered={(i,j) for i in range(len(states)) for j in range(i+1,len(states))
                   if answers[i]!=answers[j] and projected_trace(states[i],mandatory|other)==projected_trace(states[j],mandatory|other)}
        if not uncovered:selected=other
    needed_fields={field for answer in answers for q in answer for _,field in q['sources'] if field!='@argument'}|set(targets)
    all_fields={name+'.'+f['name'] for name,cls in model['classes'].items() for f in cls['fields'] if not f['access']&8 and scalar(f['desc'])}
    writable=sorted({int(row['ref'].split(':')[1]) for state in states for row in state['trace']
                     if row['kind']=='write' and row['ref'].startswith('arg:')})
    certificate={'candidate_paths':len(states),'different_answer_pairs_requiring_optional_evidence':original_pairs,
                 'remaining_ambiguous_pairs':0,'claim':'Sufficient relative to enumerated model and fixed runtime contracts; inclusion-minimal branch subset, not global minimum.'}
    return {'algorithm':'jvm-query-path-partition-v1','status':'partial' if any(q['unknown'] for a in answers for q in a) else 'planned',
            'entry':entry,'targets':targets,'root_arguments':analyzer.arguments,'model_sha256':digest(model),
            'class_sha256':{owner:cls['sha256'] for owner,cls in model['classes'].items()},
            'writable_arguments':writable,
            'reachable_methods':sorted(analyzer.reachable),'selected_sites':sorted(mandatory|selected),
            'mandatory_sites':sorted(mandatory),'selected_branch_sites':sorted(selected),'full_sites':sorted(full_sites),
            'snapshot_fields':sorted(needed_fields),'full_snapshot_fields':sorted(all_fields),
            'certificate':certificate,'path_candidates':[{'trace':s['trace'],'answer':a} for s,a in zip(states,answers)],
            'contracts':['Acyclic bounded decoded application methods, exact final/static dispatch and admitted opcode/effect models.',
                         'Root DTOs are thread-owned; mutable root arguments must not alias another root argument.',
                         'All writes to tracked scalar fields occur in the supplied application classes and are version-counted, including outside the root.',
                         'ThreadLocal.get and Boolean.booleanValue are declared read-only ambient accessors; their runtime results are not inferred.',
                         'Complete root entry/exit and selected observations; exceptional/incomplete calls fail closed.',
                         'Only root-object scalar/String target fields; no nested heap, arrays, reflection, recursion or general implicit flows.']}


def verify(plan_,model):
    require(plan_==plan(model,plan_['entry'],plan_['targets']),'Plan/certificate differs from regenerated plan')
    return True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True);p.add_argument('--entry',required=True)
    p.add_argument('--target',action='append',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=plan(json.loads(a.model.read_text()),a.entry,a.target)
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','targets','selected_branch_sites','certificate')},indent=2))
