#!/usr/bin/env python3
"""Fresh JVM protection suites plus immutable prototype certificate faults."""
import argparse,copy,json,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save
import build_distributed_plans as builder
from plan_capability_policy import specialize_transport
from plan_execution_closure import attach_execution_closure
from infer_execution_closure import validate


def install():
    original=builder.plan_response
    def wrapped(*args,**kwargs):
        plan=specialize_transport(original(*args,**kwargs))
        if plan.get('profile')=='execution-dependency':attach_execution_closure(plan,args[0] if args else kwargs['model'])
        return plan
    builder.plan_response=wrapped


def certificate_faults(root,out):
    reports={}
    for mode in ('full','selective'):
        d=root/'prototype-cart-first'/(mode+'-sockshop-carts-getItems-each-itemId')
        plan=load(d/'build/carts/plan.json');rows=[json.loads(v)for v in(d/'capture/carts/events.jsonl').read_text().splitlines()]
        original=validate(plan,rows);assert original['elided_writes']==(18 if mode=='selective'else 0)
        faults={};site=next(iter(plan['execution_observation_closure']['candidate_write_sites']))
        for fault in ('missing-certificate','unknown-site','negative-count','wrong-scope','required-field','wrong-class','mutable-field','full-elision','missing-call-completion'):
            p=copy.deepcopy(plan);r=copy.deepcopy(rows);event=next(v for v in r if 'execution_closure'in v);c=p['execution_observation_closure'];candidate=c['candidate_write_sites'][site]
            if fault=='missing-certificate':event.pop('execution_closure')
            elif fault=='unknown-site':event['execution_closure']['elided_writes']['unplanned-site']=1
            elif fault=='negative-count':event['execution_closure']['elided_writes'][site]=-1
            elif fault=='wrong-scope':event['execution_closure']['elided_writes'][site]=1;next(v for v in r if v['kind']=='collection-call-enter'and v['call_id']==event['call_id'])['callee']='unmodeled.effect()V'
            elif fault=='required-field':c['needed_fields'][candidate['field']]=['new target obligation']
            elif fault=='wrong-class':candidate['class_sha256']='0'*64
            elif fault=='mutable-field':candidate['descriptor']='Ljava/util/List;'
            elif fault=='full-elision':r[0]['mode']='full';event['execution_closure']['elided_writes'][site]=1
            elif fault=='missing-call-completion':r.remove(event)
            try:
                if fault=='missing-call-completion':
                    from infer_execution_kernel import infer_execution
                    infer_execution(p,r)
                else:validate(p,r)
            except (ValueError,KeyError):faults[fault]=True
            else:raise AssertionError((mode,'invalid certificate accepted',fault))
        reports[mode]={'original':original,'refusals':faults}
    save(out/'certificate-refusals.json',{'all_passed':True,'modes':reports})


def run(root):
    install();out=root/'closure-controls';out.mkdir();certificate_faults(root,out)
    base=root/'controls-build-01';previous=load(root/'prototype-build-01/build.json');builder.build(base,{k:v['query_config']for k,v in previous['inputs'].items()})
    from experiment_environment import java8_target
    classes=out/'probe-classes';classes.mkdir();cp=str(base/'distributed-observer.jar')
    subprocess.run(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'ExecutionClosureProbe.java')],check=True)
    p=subprocess.run(['java','-cp',str(classes)+':'+cp,'ExecutionClosureProbe'],text=True,capture_output=True,check=True);(out/'probe.log').write_text(p.stdout+p.stderr);assert 'EXECUTION_CLOSURE_GUARDS_PASSED=15'in p.stdout
    import run_kernel_contract_semantics as kernel
    kernel.run(out/'kernel')
    # Existing transport, custom serializer, Date, mutation, collection and
    # request/async controls use the same newly compiled observer sources.
    import run_transport_observation_revision as legacy
    legacy.controls(root);legacy.guards(root)
    save(out/'results.json',{'all_passed':True,'certificate_faults':18,'runtime_scope_guards':15,'new_kernel_and_legacy_controls':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);run(p.parse_args().root.resolve())
