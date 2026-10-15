#!/usr/bin/env python3
"""One frozen collector build and automatic plans for multiple original applications."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
from zipfile import ZipFile,ZIP_DEFLATED
from run_query_planner import JARS,command
from run_planned_service import HERE,ROOT,save,load,sha
from plan_service_observations import plan_service
from plan_distributed_fields import augment,copy_plan


def build(out,inputs):
    out.mkdir(parents=True,exist_ok=False);tools=out/'tools';tools.mkdir()
    sources=[HERE/n for n in ('QueryObservationAgent.java','QueryBytecodeModel.java','PlannedServiceAgent.java','SpringTransportAgent.java','W3CTraceContext.java')]
    cp=':'.join(map(str,JARS));command(['javac','--release','8','-cp',cp,'-d',str(tools),*map(str,sources)],out/'compile.log')
    jar=out/'distributed-observer.jar'
    with ZipFile(jar,'w',ZIP_DEFLATED) as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: SpringTransportAgent\n\n')
        for prefix in ('PlannedServiceAgent','SpringTransportAgent','W3CTraceContext'):
            for f in tools.glob(prefix+'*.class'):z.write(f,f.name)
        for dep in JARS:
            with ZipFile(dep) as dz:
                for n in dz.namelist():
                    if n.endswith('.class') and n.startswith(('org/objectweb/asm/','com/fasterxml/jackson/')):z.writestr(n,dz.read(n))
    manifest={'transport_protocol':'w3c-trace-context','agent_sha256':sha(jar),'inputs':{},'sources':{str(p):sha(p) for p in sources+[HERE/n for n in ('plan_distributed_fields.py','plan_service_observations.py','query_observation_planner.py','infer_planned_service.py','infer_distributed_fields.py','transport_context.py','run_distributed_paths.py','evaluate_distributed_paths.py','audit_distributed_paths.py')]},'dependencies':{str(p):sha(p) for p in JARS}}
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
        model=load(dest/'model.json');local=None
        if config.get('entry'):
            entry=config['entry'];target=config['targets'][0]
            try:local=plan_service(model,entry,target)
            except ValueError:local=copy_plan(model,entry,target)
        p=augment(model,local);save(dest/'plan.json',p);shutil.copyfile(source,dest/'original.jar')
        manifest['inputs'][role]={'query_config':config,'original_source':str(source),'original_jar_sha256':sha(source),'plan_sha256':sha(dest/'plan.json'),'model_sha256':sha(dest/'model.json'),'extra_classes':extra,'profile':p['profile'],'schema_classes':len(p['json_schema'])}
        print(role,p['profile'],len(p['json_schema']),'DTO schemas',flush=True)
    manifest['builder_sha256']=sha(Path(__file__));save(out/'build.json',manifest)


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,required=True);a.add_argument('--inputs',type=Path,required=True);args=a.parse_args();build(args.out.resolve(),load(args.inputs))
