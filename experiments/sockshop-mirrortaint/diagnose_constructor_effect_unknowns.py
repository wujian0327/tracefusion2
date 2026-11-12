"""Diagnostic tracing only; no altered capture, origin, expectation or prediction."""
import argparse,json,sys
from pathlib import Path
from run_planned_service import ROOT,save,load,sha
from control_dependencies import Control
from run_public_control_semantics import checked

BASE=ROOT/'artifacts/public-control-semantics-20261112/frozen-composition'
CTOR='java/lang/IllegalArgumentException.<init>(Ljava/lang/String;)V'  # selected operation for diagnosis only

def value(v):return {'origins':sorted(v.origins),'selectors':sorted(v.selectors),'unknown':v.unknown,'observed':v.observed}

def run(out):
    out.mkdir(parents=True,exist_ok=False);plan=load(BASE/'plan.json');all_cases=[]
    for mode in ('full','static','selective'):
        truth=load(BASE/mode/'truth-before-prediction.json');rows=[json.loads(l)for l in(BASE/mode/'events.jsonl').read_text().splitlines()]
        targets={next(r['frame']for r in rows if r['kind']=='binding-return'and r['message']==t['message']):t for t in truth if t['scenario']in(14,16)}
        events={f:[]for f in targets};original=Control._field_effects
        def merge(self,region,condition,seq):
            n=len(self.state.control_barriers)
            result=original(self,region,condition,seq)
            if self.frame.invocation in targets:
                for at,c,keys in self.state.control_barriers[n:]:
                    events[self.frame.invocation].append({'kind':'potential-effect-merge','seq':at,'pc':self.frame.pc,'condition':value(c),'unclosed_calls':list(keys),'actual_write':False})
            return result
        Control._field_effects=merge
        def profile(frame,event,result):
            if event!='return':return
            scope=frame.f_locals
            if frame.f_code.co_name=='poison'and frame.f_code.co_filename.endswith('/infer_application_execution.py'):
                caller=frame.f_back
                while caller and 'fr'not in caller.f_locals:caller=caller.f_back
                active=caller.f_locals if caller else {}
                if 'fr'not in active:return
                f=active['fr'].invocation
                if f in targets:events[f].append({'kind':'actual-opaque-effect','seq':scope['seq'],'method':active['entry'],'pc':active['fr'].pc,'affected_objects':sorted(scope.get('affected',())),'argument_values':[value(v)for v in scope['values']if v is not None]})
            elif frame.f_code.co_name=='field_selection':
                if result is not None and result.unknown and not scope['value'].unknown:
                    # profile sees value after assignments; barrier trace above
                    # remains the authoritative first transition.
                    pass
        try:
            sys.setprofile(profile);prediction=checked(plan,rows)
        finally:sys.setprofile(None);Control._field_effects=original
        save(out/(mode+'-prediction.json'),prediction)
        for f,t in targets.items():
            scope=[r for r in rows if r.get('frame')==f]
            begins=[r for r in scope if r['kind']=='execution-constructor-enter'and r['callee']==CTOR]
            completed=[r for r in scope if r['kind']=='execution-constructed'and r.get('pc')in{r['pc']for r in begins}]
            answer=next(a for a in prediction['answers']if a['root_frame']==f)
            sources=[]
            for r in rows:
                if r['kind']=='binding-source'and r.get('frame')==f:
                    for i,field in enumerate(r['fields']):sources.append({'token':['field',r['seq'],i],**field})
            barriers=events[f];affected={x for e in barriers for x in e.get('affected_objects',[])}
            cases={'mode':mode,'scenario':t['scenario'],'input':t['input'],'frame':f,'capture':str(BASE/mode/'events.jsonl'),'capture_sha256':sha(BASE/mode/'events.jsonl'),'constructor_executed':bool(begins),'constructor_begin':begins,'constructor_completion':completed,'first_uncertainty':barriers[0]if barriers else None,'transitions':barriers,'affected_source_fields':[s for s in sources if s['owner']in affected],'potential_effect_scope':'preexisting heap versions established before branch seq; no actual write claimed for untaken constructor','expected_origins':t['origins'],'expected_selectors':t['selectors'],'answer':answer,'data_occurrences_match':set(map(tuple,answer['origins']))==set(map(tuple,t['origins'])),'selector_occurrences_match':set(map(tuple,answer['selectors']))==set(map(tuple,t['selectors'])),'complete_known':answer['known'],'missing_proofs':['JDK constructor bytecode/effect contract','exact dispatch of overridable fillInStackTrace','native effect scope and runtime configuration','class initialization and runtime implementation','actual successful new-field writes/reference graph (not in opaque capture)']}
            all_cases.append(cases)
    save(out/'cases.json',all_cases)
    print(json.dumps([{'mode':x['mode'],'scenario':x['scenario'],'input':x['input'],'executed':x['constructor_executed'],'first':{k:v for k,v in (x['first_uncertainty']or{}).items()if k in('seq','pc','kind')},'data_match':x['data_occurrences_match'],'selectors_match':x['selector_occurrences_match'],'known':x['complete_known']}for x in all_cases],ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
