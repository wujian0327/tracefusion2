#!/usr/bin/env python3
"""Build a separately disclosed boundary-label/native-export probe."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from run_planned_service import ROOT, HERE, load, save, sha
from run_query_planner import JARS
from experiment_environment import java8_target
from plan_distributed_fields import json_schema


def build(out, base):
    out.mkdir(parents=True, exist_ok=False)
    native = ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar'
    assert sha(native) == load(HERE/'sources.json')['mirrortaint']['agent_sha256']
    subprocess.run([sys.executable, str(HERE/'build_integration_adapter.py'), '--agent',str(native),'--out',str(out/'adapter')],check=True,stdout=(out/'adapter-build.log').open('w'))
    files=[HERE/n for n in ('MirrorCapabilityAgent.java','MirrorCapabilityTransport.java','W3CTraceContext.java')]
    snapshots=out/'source-snapshot';snapshots.mkdir()
    import shutil
    for source in files:shutil.copyfile(source,snapshots/source.name)
    classes=out/'classes';classes.mkdir()
    cmd=['javac',*java8_target()[1],'-cp',':'.join(map(str,[native,*JARS])),'-d',str(classes),*map(str,files)]
    p=subprocess.run(cmd,capture_output=True,text=True);(out/'compile.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise RuntimeError('Probe compile failed: '+p.stderr)
    jar=out/'capability.jar'
    with ZipFile(jar,'w',ZIP_DEFLATED) as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: MirrorCapabilityAgent\n\n')
        for p in classes.glob('*.class'):z.write(p,p.name)
        for dep in JARS:
            with ZipFile(dep) as lib:
                for n in lib.namelist():
                    if n.endswith('.class') and n.startswith(('org/objectweb/asm/','com/fasterxml/jackson/')):z.writestr(n,lib.read(n))
    for role in load(base/'build.json')['inputs']:
        model=load(base/role/'model.json');schema,rejected=json_schema(model)
        save(out/(role+'-schema.json'),{'json_schema':schema,'rejected_properties':rejected,
            'scope':'Shared original-bytecode default-serialization metadata ONLY; no planning or dependency propagation.'})
    save(out/'build.json',{'native_jar':str(native),'native_sha256':sha(native),'probe_sha256':sha(jar),
        'base':str(base),'base_sha256':sha(base/'build.json'),'sources_sha256':{str(p):sha(p) for p in files},
        'adapter_sha256':sha(out/'adapter/integration-adapter.jar'),'purpose':'Boundary source configuration plus native tag export. No dependency reconstruction.'})


def config(q, base):
    model=load(base/q['role']/'model.json')
    repos={o for o,c in model['classes'].items() if any(i.startswith('org/springframework/data/') and i.endswith('Repository') for i in c.get('interfaces',[]))}
    calls=set()
    for m in model['methods'].values():
        for i in m['instructions']:
            if i['op'] not in (182,185):continue
            if i['owner'] in repos and i['name'].startswith('find') or i['owner']=='org/springframework/web/client/RestTemplate' and i['name'] in ('exchange','getForObject','getForEntity'):
                calls.add(i['owner']+'.'+i['name']+i['desc'])
    prefix=q['entry'].split('/')[0]+'/'
    if q['application']=='sockshop':prefix='works/weave/socks/'
    return {'entry':q['entry'],'prefix':prefix,'source_calls':sorted(calls)}


def configure(spec,dest,base,bundle,q):
    manifest=load(bundle/'build.json');native=Path(manifest['native_jar'])
    assert sha(native)==manifest['native_sha256'] and sha(bundle/'capability.jar')==manifest['probe_sha256']
    role=q['role'];name=role if q['application']=='sockshop' else 'ts-'+role+'-service';cfg=spec['services'][name]
    capture=dest/role;capture.mkdir(exist_ok=True);capture.chmod(0o777)
    settings=config(q,base);save(dest/'mt-config.json',settings)
    # Remove TF only from this service. Other services, if present, provide raw
    # witness data; their answers are never inputs to the MT predictor.
    cfg['volumes']=[v for v in cfg.get('volumes',[]) if not any(x in v for x in ('/tf2/observer.jar','/tf2/plan.json',':/tf2/capture:'))]
    cfg['volumes'] += [str(capture)+':/tf2/capture:rw',str(native)+':/tf2/mirrorTaint.jar:ro',str(bundle/'adapter/integration-adapter.jar')+':/tf2/adapter.jar:ro',
        str(bundle/'capability.jar')+':/tf2/capability.jar:ro',str(bundle/(role+'-schema.json'))+':/tf2/schema.json:ro',str(dest/'mt-config.json')+':/tf2/mt-config.json:ro']
    options='-Xms32m -Xmx512m -Djava.security.egd=file:/dev/urandom -Dspring.zipkin.enabled=false'
    options+=' -Dtaint.env=remote -Dtaint.app='+settings['prefix'].rstrip('/').replace('/','.')+' -Dtaint.version=capability -Duser.home=/tf2/capture'
    options+=' -javaagent:/tf2/adapter.jar=strings -javaagent:/tf2/adapter.jar=streams -javaagent:/tf2/mirrorTaint.jar -javaagent:/tf2/adapter.jar=returns -javaagent:/tf2/adapter.jar=sources -javaagent:/tf2/adapter.jar=fields -javaagent:/tf2/adapter.jar=threads -javaagent:/tf2/adapter.jar=logging'
    options+=' -javaagent:/tf2/capability.jar -Dcapability.config=/tf2/mt-config.json -Dcapability.events=/tf2/capture/native-capability.jsonl'
    options+=' -javaagent:/tf2/capability.jar=transport -Dinstance.schema=/tf2/schema.json -Dinstance.events=/tf2/capture/instances.jsonl'
    cfg['environment']['JAVA_OPTS']=options


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);a=p.parse_args();build(a.out.resolve(),a.base.resolve())
