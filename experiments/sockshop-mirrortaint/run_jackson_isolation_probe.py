#!/usr/bin/env python3
"""Check a private Agent JSON runtime and two original application Jackson sets."""
import argparse,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,save,load,sha
from run_query_planner import command
from experiment_environment import java8_target


def run(out,build):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    agent=build/'distributed-observer.jar'
    with ZipFile(agent)as z:
        assert not any(n.startswith('com/fasterxml/jackson/')for n in z.namelist())
        private=sum(n.startswith('tracefusion/internal/jackson/')for n in z.namelist());assert private>700
    command(['javac',*java8_target()[1],'-cp',str(agent),'-d',str(classes),str(HERE/'JacksonIsolationFixture.java')],out/'compile.log')
    dirs=[];expected=[]
    for role in ('carts','basic'):
        d=out/role;d.mkdir();original=ROOT/'artifacts/library-gap-revision-20261022/final-capability/frozen-base'/role/'original.jar'
        with ZipFile(original)as z:
            for n in z.namelist():
                if n.startswith('BOOT-INF/lib/jackson-')and n.endswith('.jar'):(d/Path(n).name).write_bytes(z.read(n))
        expected.append({'role':role,'original_jar_sha256':sha(original),'jars':{p.name:sha(p)for p in d.glob('*.jar')}});dirs.append(str(d))
    command(['java','-javaagent:'+str(agent),'-Dservice.plan='+str(build/'fixture/plan.json'),'-Dservice.mode=selective','-Dservice.events='+str(out/'events.jsonl'),'-cp',str(classes)+':'+str(agent),'JacksonIsolationFixture',*dirs],out/'stdout.json')
    result=json.loads((out/'stdout.json').read_text().splitlines()[-1]);assert result['no_original_Jackson_in_system_loader'] and all(r['separate_loader']for r in result['native_loaders'])
    assert {r['version']for r in result['native_loaders']}=={'2.8.6','2.8.11-3'}
    result.update(all_passed=True,agent_sha256=sha(agent),private_classes=private,inputs=expected)
    save(out/'results.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--build',required=True,type=Path);a=p.parse_args();print(json.dumps(run(a.out.resolve(),a.build.resolve()),indent=2))
