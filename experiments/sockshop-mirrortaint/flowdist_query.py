#!/usr/bin/env python3
"""Run an original method-level query on frozen traces in a fresh directory.

This reports the tool's candidate-flow decision, not field/path accuracy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from flowdist_preflight import CP, execute, save


def query(repo,source,out,text):
    out.mkdir(parents=True,exist_ok=False)
    traces=out/'work/traces/test1';traces.mkdir(parents=True)
    inputs={}
    for file in sorted((source/'work/traces/test1').glob('Remote*.em')):
        shutil.copyfile(file,traces/file.name);inputs[file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
    if len(inputs)!=2:raise ValueError('Expected two frozen process traces')
    result=execute(repo,out,'method-query',['-Xmx1g','-ea','-cp',CP,'disttaint.OTAnalysisAll',text,'/work/traces','/work','','-prec'])
    raw=(out/'method-query.log').read_text()
    length=re.search(r'\[The method path length\]: (\d+)',raw)
    negative='There is no flow path!' in raw
    if bool(length)==negative:raise ValueError('Missing or ambiguous query decision')
    result.update(query=text,input_trace_sha256=inputs,source_artifact=str(source),
        decision='candidate-flow' if length else 'no-candidate-flow',
        method_path_length=int(length.group(1)) if length else None)
    save(out/'result.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--query',required=True)
    a=p.parse_args();print(json.dumps(query(a.repo.resolve(),a.input.resolve(),a.out.resolve(),a.query),indent=2))
