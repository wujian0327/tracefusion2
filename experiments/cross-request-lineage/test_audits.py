#!/usr/bin/env python3
"""Adversarial audit checks on disposable copies of actual captured evidence."""
import argparse
import copy
import json
from pathlib import Path
import shutil
from verify import verify,digest,load


def run(source,out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for name in ('oracle-change','duplicate-real-rpc','native-heap-restart','codec-wire-mismatch'):
        dest=out/name
        shutil.copytree(source,dest,copy_function=lambda a,b:Path(b).symlink_to(Path(a).resolve()))
        def change(relative,edit):
            p=dest/relative;old=p.read_text();p.unlink();p.write_text(edit(old))
            # Rehash the modified evidence to exercise semantics, not checksum detection.
            index=load(dest/'files.sha256.json');index[str(relative)]=digest(p)
            ip=dest/'files.sha256.json';ip.unlink();ip.write_text(json.dumps(index))
        if name=='oracle-change':
            change(Path('expected.json'),lambda text:text.replace('R1/value','R9/value'))
        elif name=='duplicate-real-rpc':
            rel=Path('captures/plain/1/cache-hit/A/http.jsonl')
            def edit(text):
                rs=[json.loads(l)for l in text.splitlines()];rs[0]['rpc_traceparent']=rs[1]['rpc_traceparent'];return ''.join(json.dumps(r)+'\n'for r in rs)
            change(rel,edit)
        elif name=='native-heap-restart':
            rel=Path('captures/mirrortaint/1/cache-hit/B/native.jsonl')
            def edit(text):
                rs=[json.loads(l)for l in text.splitlines()];rs.append(next(r for r in rs if r['kind']=='startup'));return ''.join(json.dumps(r)+'\n'for r in rs)
            change(rel,edit)
        else:
            rel=Path('captures/tracefusion/1/cache-hit/B/events.jsonl')
            def edit(text):
                rs=[json.loads(l)for l in text.splitlines()];next(r for r in rs if r['kind']=='http-json')['wire_sha256']='0'*64;return ''.join(json.dumps(r)+'\n'for r in rs)
            change(rel,edit)
        try:verify(dest)
        except (AssertionError,KeyError,ValueError) as e:results.append({'mutation':name,'rejected':True,'exception':type(e).__name__,'reason':str(e)})
        else:raise AssertionError('Invalid evidence accepted: '+name)
    (out/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.run.resolve(),a.out.resolve())
