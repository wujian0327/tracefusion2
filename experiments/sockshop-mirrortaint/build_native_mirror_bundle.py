#!/usr/bin/env python3
"""Isolate only the fixed baseline exporter's private JSON; native MT unchanged."""
import argparse,copy,json,shutil,subprocess
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from run_planned_service import ROOT,HERE,load,save,sha
from experiment_environment import java8_target
from run_query_planner import JARS
import isolate_agent_jackson as isolation


def build(out,base):
    prior=ROOT/'artifacts/baseline-capability-20261020/mirror-build-09'
    out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(prior/'adapter',out/'adapter')
    original=load(prior/'build.json');native=Path(original['native_jar']);assert sha(native)==original['native_sha256']
    old_new=isolation.NEW;isolation.NEW=b'baseline/internal/jackson/'
    try:
        with ZipFile(prior/'capability.jar') as src,ZipFile(out/'capability.jar','w',ZIP_DEFLATED) as dest:
            for name in src.namelist():
                data=src.read(name)
                if name.startswith('com/fasterxml/jackson/'):
                    name=name.replace('com/fasterxml/jackson/','baseline/internal/jackson/',1);data=isolation.relocate(data)
                elif name.startswith('MirrorCapabilityTransport$Evidence') and name.endswith('.class'):data=isolation.relocate(data)
                dest.writestr(name,data)
    finally:isolation.NEW=old_new
    with ZipFile(out/'capability.jar') as z:
        assert not any(n.startswith('com/fasterxml/jackson/') for n in z.namelist())
        for name in z.namelist():
            if name.endswith('.class'):assert not any(isolation.OLD in t for t in isolation.symbolic_types(z.read(name))),name
    # The extra witness returns null from every transformer call: it observes
    # original mapper definitions and cannot create sources or taint labels.
    classes=out/'witness-classes';classes.mkdir()
    subprocess.run(['javac',*java8_target()[1],'-d',str(classes),str(HERE/'NativeLibraryWitness.java')],check=True)
    with ZipFile(out/'runtime-witness.jar','w',ZIP_DEFLATED) as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: NativeLibraryWitness\n\n')
        for p in classes.glob('*.class'):z.write(p,p.name)
    from plan_distributed_fields import json_schema
    for role in load(base/'build.json')['inputs']:
        schema,rejected=json_schema(load(base/role/'model.json'));save(out/(role+'-schema.json'),{'json_schema':schema,'rejected_properties':rejected,'scope':'Default original-bytecode field metadata only; no origins.'})
    result={**original,'base':str(base),'base_sha256':sha(base/'build.json'),'probe_sha256':sha(out/'capability.jar'),'adapter_sha256':sha(out/'adapter/integration-adapter.jar'),
            'native_library_witness_sha256':sha(out/'runtime-witness.jar'),'historical_probe_sha256':sha(prior/'capability.jar'),'native_propagation_changed':False,'private_JSON_relocation':'baseline.internal.jackson',
            'packaging_sources':{str(HERE/n):sha(HERE/n) for n in ['build_native_mirror_bundle.py','NativeLibraryWitness.java','isolate_agent_jackson.py']}}
    save(out/'build.json',result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);a=p.parse_args();build(a.out.resolve(),a.base.resolve())
