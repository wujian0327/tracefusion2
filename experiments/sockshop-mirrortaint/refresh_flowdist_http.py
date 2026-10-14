#!/usr/bin/env python3
"""Refresh HTTP adapter classes in validated full-method application copies.

Preserve every previously instrumented application/runtime entry byte-for-byte.
The new base must use the same original business JARs.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


def digest(data):return hashlib.sha256(data).hexdigest()


def refresh(previous, base, out):
    old=json.loads((previous/'manifest.json').read_text());new=json.loads((base/'manifest.json').read_text())
    out.mkdir(parents=True,exist_ok=False);result=copy.deepcopy(old);changes={}
    for role in ('orders','carts','shipping'):
        if old['apps'][role]['original_sha256']!=new['apps'][role]['original_sha256']:raise ValueError('Different original app')
        source=previous/(role+'-flowdist.jar')
        if digest(source.read_bytes())!=old['apps'][role]['adapted_sha256']:raise ValueError('Previous app changed')
        with ZipFile(base/(role+'-flowdist.jar')) as fresh:
            replacements={n:fresh.read(n) for n in fresh.namelist() if n.startswith('BOOT-INF/classes/disttaint/http/') and n.endswith('.class')}
        if not replacements:raise ValueError('No refreshed HTTP adapter')
        output=out/(role+'-flowdist.jar');changed=[]
        with ZipFile(source) as original,ZipFile(output,'w') as target:
            for entry in original.infolist():
                before=original.read(entry.filename);after=replacements.pop(entry.filename,before)
                if before!=after:changed.append(entry.filename)
                target.writestr(entry,after)
            for name,data in replacements.items():target.writestr(name,data)
        with ZipFile(source) as original,ZipFile(output) as target:
            for name in original.namelist():
                if not name.startswith('BOOT-INF/classes/disttaint/http/') and original.read(name)!=target.read(name):
                    raise ValueError('Application/runtime entry changed')
        result['apps'][role]['adapted_sha256']=digest(output.read_bytes());changes[role]=changed
    result.update(carts_http_response_clock_available=True,http_refresh_source=str(base),
                  previous_fullmethod_build=str(previous),http_adapter_replaced_entries=changes,
                  http_refresh_source_sha256=new['source_sha256'],
                  http_clock_policy='Original process/first-receive clock; Carts reply stamped after actual serialization; no per-request trace inference')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('previous','base','out'):parser.add_argument('--'+flag,type=Path,required=True)
    a=parser.parse_args();refresh(a.previous.resolve(),a.base.resolve(),a.out.resolve())
