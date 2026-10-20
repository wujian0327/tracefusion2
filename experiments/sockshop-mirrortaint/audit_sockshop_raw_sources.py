#!/usr/bin/env python3
"""Decode original HTTP bytes with original libraries and NO provenance Agent."""
import argparse,base64,hashlib,json,subprocess
from pathlib import Path
from zipfile import ZipFile
from experiment_environment import java8_target
from run_planned_service import HERE,load,save,sha


def run(out,capture,build):
    out.mkdir();lib=out/'lib';lib.mkdir()
    original=build/'orders/original.jar'
    with ZipFile(original) as z:
        for name in z.namelist():
            if name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):(lib/Path(name).name).write_bytes(z.read(name))
    cp=str(build/'orders/app')+':'+str(lib/'*')
    proc=subprocess.run(['javac',*java8_target()[1],'-cp',cp,'-d',str(out),str(HERE/'HateoasOracleProbe.java')],text=True,capture_output=True,check=True);(out/'compile.log').write_text(proc.stdout+proc.stderr)
    rows=[json.loads(x) for x in (capture/'orders/events.jsonl').read_text().splitlines()];checks=[]
    for r in rows:
        if r['kind']!='http-source-fact' or r['body_type']!='org.springframework.hateoas.Resource':continue
        raw=base64.b64decode(r['raw_base64']);assert r['capture_version']==2 and r['document_complete'] and hashlib.sha256(raw).hexdigest()==r['raw_sha256']
        file=out/(str(r['seq'])+'.json');file.write_bytes(raw)
        p=subprocess.run(['java','-cp',str(out)+':'+cp,'HateoasOracleProbe',r['content_type'],str(file)],text=True,capture_output=True,check=True)
        (out/(str(r['seq'])+'.stdout')).write_text(p.stdout+p.stderr);decoded=json.loads(p.stdout.splitlines()[-1]);fields=decoded['decoded_fields']
        assert all(fields[f['path'][1:]]==f['observed'].get('value') for f in r['fields'])
        checks.append({'seq':r['seq'],'message':r['message'],'parent_message':r['parent_message'],'uri':r['uri'],'content_object':r['content_object'],
                       'all_observed_fields_match':True,'raw_id':decoded['raw_json'].get('id'),'decoded_id':fields.get('id'),
                       'raw_file':str(file),'raw_sha256':sha(file),'lists':{k:v for k,v in fields.items() if isinstance(v,list)}})
    assert len(checks)==18 and all(c['raw_id'] is not None and c['decoded_id'] is None for c in checks)
    result={'all_passed':True,'probe_without_tf_agent':True,'uses_tf_propagation':False,'capture':str(capture),'original_jar_sha256':sha(original),
            'probe_sha256':sha(HERE/'HateoasOracleProbe.java'),'java_version':subprocess.run(['java','-version'],text=True,capture_output=True).stderr,'checks':checks}
    save(out/'checks.json',result);print({'original_library_checks':len(checks),'all_passed':True},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--capture',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.capture.resolve(),a.build.resolve())
