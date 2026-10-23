#!/usr/bin/env python3
"""One frozen collector build and automatic plans for multiple original applications."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
from experiment_environment import java8_target
from zipfile import ZipFile,ZIP_DEFLATED
from run_query_planner import JARS,command
from run_planned_service import HERE,ROOT,save,load,sha
from plan_service_observations import plan_service
from plan_distributed_fields import augment,copy_plan
from plan_collection_service import plan_collection
from plan_response_binding import plan_response
from isolate_agent_jackson import agent_class, symbolic_types, OLD


def build(out,inputs):
    out.mkdir(parents=True,exist_ok=False);tools=out/'tools';tools.mkdir()
    sources=[HERE/n for n in ('QueryObservationAgent.java','QueryBytecodeModel.java','PlannedServiceAgent.java','CollectionServiceHooks.java','ConversionContractHooks.java','ExecutionKernelHooks.java','AsyncTaskHooks.java','FrameworkCallHooks.java','RequestEntityHooks.java','SaveEffectHooks.java','TemporalDateHooks.java','UuidProjectionHooks.java','ResponseBindingHooks.java','ReadEffectHooks.java','JdkContractProbe.java','SourceEvidenceHooks.java','SpringTransportAgent.java','W3CTraceContext.java')]
    sources.append(HERE/'BusinessJackson.java')
    # JDK 8 has no --release option; its own platform is already Java 8.
    compiler_version,target=java8_target()
    cp=':'.join(map(str,JARS));command(['javac',*target,'-cp',cp,'-d',str(tools),*map(str,sources)],out/'compile.log')
    jar=out/'distributed-observer.jar'
    with ZipFile(jar,'w',ZIP_DEFLATED) as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: SpringTransportAgent\n\n')
        for prefix in ('PlannedServiceAgent','CollectionServiceHooks','ConversionContractHooks','ExecutionKernelHooks','AsyncTaskHooks','FrameworkCallHooks','RequestEntityHooks','SaveEffectHooks','TemporalDateHooks','UuidProjectionHooks','ResponseBindingHooks','ReadEffectHooks','JdkContractProbe','SourceEvidenceHooks','SpringTransportAgent','W3CTraceContext'):
            for f in tools.glob(prefix+'*.class'):
                name,data=agent_class(f.name,f.read_bytes());z.writestr(name,data)
        for f in tools.glob('BusinessJackson*.class'):z.writestr(f.name,f.read_bytes())
        for dep in JARS:
            with ZipFile(dep) as dz:
                for n in dz.namelist():
                    if n.endswith('.class') and n.startswith(('org/objectweb/asm/','com/fasterxml/jackson/')):
                        name,data=agent_class(n,dz.read(n));z.writestr(name,data)
    with ZipFile(jar) as z:
        for name in z.namelist():
            assert not name.startswith('com/fasterxml/jackson/'),name
            if name.endswith('.class'):
                assert not any(OLD in t for t in symbolic_types(z.read(name))),('Unisolated Jackson type linkage',name)
    manifest={'compiler_version':compiler_version,'compiler_target':target,'transport_protocol':'w3c-trace-context','agent_sha256':sha(jar),'inputs':{},'sources':{str(p):sha(p) for p in sources+[HERE/n for n in ('experiment_environment.py','plan_distributed_fields.py','plan_service_observations.py','plan_collection_service.py','query_observation_planner.py','infer_planned_service.py','infer_distributed_fields.py','transport_context.py','run_distributed_paths.py','evaluate_distributed_paths.py','audit_distributed_paths.py')]},'dependencies':{str(p):sha(p) for p in JARS}}
    for role,config in inputs.items():
        source=Path(config['jar']).resolve()
        dest=out/role;dest.mkdir();app=dest/'app';app.mkdir();extra={}
        with ZipFile(source) as z:
            for n in z.namelist():
                if n.startswith('BOOT-INF/classes/') and n.endswith('.class'):
                    f=app/n[len('BOOT-INF/classes/'):];f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(z.read(n))
            # Query owner classes missing from BOOT-INF/classes are resolved in
            # actual dependency jars, not recompiled or replaced locally.
            for n in z.namelist():
                if n.startswith('BOOT-INF/lib/') and n.endswith('.jar'):
                    with ZipFile(BytesIO(z.read(n))) as dz:
                        for target in config.get('targets',[]):
                            requested=target.rsplit('.',1)[0].replace('.','/')+'.class'
                            if requested in dz.namelist():
                                f=app/requested;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(dz.read(requested));extra[requested]={'jar_entry':n,'sha256':sha(f)}
        command(['java','-cp',str(tools)+':'+cp,'QueryBytecodeModel',str(app),str(dest/'model.json')],dest/'model.log')
        model=load(dest/'model.json')
        from contract_applicability import library_inventory
        model['library_inventory']=library_inventory(source);save(dest/'model.json',model);local=None
        if config.get('entry'):
            entry=config['entry'];target=config['targets'][0]
            if config.get('response_path'):
                local=plan_response(model,entry,target,config['response_path'],config.get('source_calls'),config.get('read_forward_contracts',False),config.get('execution_kernel',False),config.get('application_calls',False))
            elif config.get('profile')=='collection-computation':local=plan_collection(model,entry,target)
            else:
                try:local=plan_service(model,entry,target)
                except ValueError:local=copy_plan(model,entry,target)
        p=augment(model,local)
        from plan_date_projection import attach_date_projection
        p=attach_date_projection(p,model)
        if config.get('source_evidence'):p['source_evidence']=True
        if config.get('async_evidence'):p['async_protocol']=load(HERE/'async-task-contracts-20261021.json')
        if config.get('async_dependencies'):
            from plan_async_dependencies import attach_async_dependencies
            p=attach_async_dependencies(p)
        if any(c.get('profile')=='collection-computation' for c in inputs.values()):p['collection_elements']=True
        if config.get('json_conversion_methods'):
            for key in config['json_conversion_methods']:
                if key not in model['methods'] or not model['methods'][key]['access']&8:raise ValueError('Conversion summary needs a modeled static method')
            p['json_conversion_methods']=config['json_conversion_methods']
            p['json_conversion_contract']='Explicit library summary: default Jackson object-to-JSON-to-object by relative JSON pointer; exact original library class pinned. No custom serializers or polymorphic coercion.'
        save(dest/'plan.json',p);shutil.copyfile(source,dest/'original.jar')
        manifest['inputs'][role]={'query_config':config,'original_source':str(source),'original_jar_sha256':sha(source),'plan_sha256':sha(dest/'plan.json'),'model_sha256':sha(dest/'model.json'),'extra_classes':extra,'profile':p['profile'],'schema_classes':len(p['json_schema'])}
        print(role,p['profile'],len(p['json_schema']),'DTO schemas',flush=True)
    manifest['sources'][str(HERE/'infer_collection_service.py')]=sha(HERE/'infer_collection_service.py')
    for name in ('plan_response_binding.py','infer_response_binding.py','plan_read_effects.py','read-forward-runtimes-20261020.json','plan_execution_kernel.py','infer_execution_kernel.py','execution_dependency_state.py','execution-kernel-runtimes-20261020.json','analysis_status.py','plan_application_calls.py','infer_application_execution.py','kernel-contract-runtimes-20261020.json','plan_constructor_effects.py','constructor-library-contracts-20261020.json','framework-wrapper-contracts-20261020.json','plan_date_projection.py','date-runtime-contracts-20261020.json','infer_date_projection.py','async-task-contracts-20261021.json','infer_async_protocol.py','plan_async_dependencies.py','request-entity-contracts-20261021.json','save-effect-contracts-20261021.json'):
        manifest['sources'][str(HERE/name)]=sha(HERE/name)
    manifest['sources'][str(HERE/'date-effects-contracts-20261021.json')]=sha(HERE/'date-effects-contracts-20261021.json')
    manifest['sources'][str(HERE/'save-provided-id-contracts-20261023.json')]=sha(HERE/'save-provided-id-contracts-20261023.json')
    manifest['sources'][str(HERE/'contract_applicability.py')]=sha(HERE/'contract_applicability.py')
    manifest['sources'][str(HERE/'contract_obligations.py')]=sha(HERE/'contract_obligations.py')
    manifest['sources'][str(HERE/'finite_string_values.py')]=sha(HERE/'finite_string_values.py')
    manifest['sources'][str(HERE/'plan_capability_policy.py')]=sha(HERE/'plan_capability_policy.py')
    manifest['sources'][str(HERE/'plan_execution_closure.py')]=sha(HERE/'plan_execution_closure.py')
    manifest['sources'][str(HERE/'infer_execution_closure.py')]=sha(HERE/'infer_execution_closure.py')
    manifest['sources'][str(HERE/'library-value-runtimes-20261022.json')]=sha(HERE/'library-value-runtimes-20261022.json')
    manifest['sources'][str(HERE/'plain-conversion-contracts-20261022.json')]=sha(HERE/'plain-conversion-contracts-20261022.json')
    for name in ('plan_uuid_projection.py','infer_uuid_projection.py','uuid-projection-contracts-20261022.json'):manifest['sources'][str(HERE/name)]=sha(HERE/name)
    manifest['sources'][str(HERE/'isolate_agent_jackson.py')]=sha(HERE/'isolate_agent_jackson.py')
    manifest['jackson_isolation']='Internal JSON relocated to tracefusion.internal.jackson; business inspection has no Jackson type linkage'
    manifest['builder_sha256']=sha(Path(__file__));save(out/'build.json',manifest)


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,required=True);a.add_argument('--inputs',type=Path,required=True);args=a.parse_args();build(args.out.resolve(),load(args.inputs))
