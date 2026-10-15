#!/usr/bin/env python3
"""Read original JARs directly from the digest-locked cached images, without starting them."""
import argparse
import json
from pathlib import Path
import posixpath
import re
import subprocess
import tempfile
from run_planned_service import load,save,sha


def verify(out,build):
    records=[];commands=[]
    def command(args):
        commands.append(args);return subprocess.run(args,capture_output=True,text=True,check=True,timeout=45).stdout
    for app,roles in [('sockshop',['orders','carts','shipping']),('trainticket',['station','basic','ticketinfo'])]:
        compose=load(out/app/'compose.lock.json')
        for role in roles:
            service=role if app=='sockshop' else 'ts-'+role+'-service';image=compose['services'][service]['image'];info=json.loads(command(['docker','image','inspect',image]))[0]
            config=info['Config'];args=(config.get('Entrypoint') or [])+(config.get('Cmd') or [])
            candidates=re.findall(r'[^\s\[\]"\']+\.jar',' '.join(args));assert len(candidates)==1,candidates
            jar=posixpath.normpath(posixpath.join(config.get('WorkingDir') or '/',candidates[0]));container=command(['docker','create',image]).strip()
            with tempfile.TemporaryDirectory(prefix='original-jar-verify-') as td:
                path=Path(td)/'app.jar'
                try:command(['docker','cp',container+':'+jar,str(path)])
                finally:command(['docker','rm',container])
                expected=sha(build/role/'original.jar');actual=sha(path);assert actual==expected,(role,actual,expected)
            records.append({'application':app,'role':role,'image':image,'image_id':info['Id'],'jar_path':jar,'image_jar_sha256':actual,'analysis_jar_sha256':expected,'matched':True})
    save(out/'original-image-verification.json',{'all_matched':True,'records':records,'commands':commands,'containers_started':False,'temporary_containers_removed':True})
    print('Original image JARs matched:',len(records))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();verify(a.out.resolve(),a.build.resolve())
