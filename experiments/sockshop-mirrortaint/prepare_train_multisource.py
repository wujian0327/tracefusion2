#!/usr/bin/env python3
"""Prepare immutable original Train Ticket inputs in a fresh directory."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from run_planned_service import save,sha

IMAGES={
    'basic':'codewisdom/ts-basic-service@sha256:5d9c0dd7bf47e8575e8d9b456cc6576abac836d62c69ab1989f97bdcc716b102',
    'station':'codewisdom/ts-station-service@sha256:1e9ea348b30926c3a31dde87f063a4325f854b123e70c307abe33ea17137f0ea',
    'train':'codewisdom/ts-train-service@sha256:5b49d42e8daf389d4f0a787f76f7c424a9aa698a4d711704589b74e84fac54c1',
    'route':'codewisdom/ts-route-service@sha256:fc5947172659ad347c6ed56e1b825ee58cb6221aa9ab34b77eb727e232dbbbd5',
    'price':'codewisdom/ts-price-service@sha256:5a77b41ee671501f664b88cafb10c1332ade4aba5354ad6dabe2ce0f4dbdbf42'}


def prepare(out,pull=False):
    out.mkdir(parents=True,exist_ok=False);inputs={};images={}
    def command(args):
        with (out/'commands.jsonl').open('a') as f:f.write(json.dumps(args)+'\n')
        return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=300)
    for role,image in IMAGES.items():
        if pull:command(['docker','pull',image])
        info=json.loads(command(['docker','image','inspect',image]))[0]
        if image not in info['RepoDigests']:raise ValueError('Immutable digest missing')
        config=info['Config'];args=(config.get('Entrypoint') or [])+(config.get('Cmd') or [])
        candidates=re.findall(r'[^\s\[\]"\']+\.jar',' '.join(args))
        if len(candidates)!=1 or not candidates[0].startswith('/'):raise ValueError('Original image JAR path ambiguous')
        cid=command(['docker','create',image]).strip();dest=out/(role+'.jar')
        try:command(['docker','cp',cid+':'+candidates[0],str(dest)])
        finally:command(['docker','rm',cid])
        targets=['edu.fudan.common.util.Response.data']
        inputs[role]={'image':image,'jar':str(dest),'targets':targets}
        images[role]={'image':image,'id':info['Id'],'jar_sha256':sha(dest),'image_jar_path':candidates[0]}
    inputs['basic'].update(entry='fdse/microservice/service/BasicServiceImpl.queryForTravel(Lfdse/microservice/entity/Travel;Lorg/springframework/http/HttpHeaders;)Ledu/fudan/common/util/Response;',
        targets=['fdse.microservice.entity.TravelResult.prices','edu.fudan.common.util.Response.data','edu.fudan.common.util.JsonUtils.LOGGER'],profile='collection-computation',
        json_conversion_methods=['edu/fudan/common/util/JsonUtils.conveterObject(Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;'])
    save(out/'inputs.json',inputs);save(out/'images.json',images)
    print(out/'inputs.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--pull',action='store_true');a=p.parse_args();prepare(a.out.resolve(),a.pull)
