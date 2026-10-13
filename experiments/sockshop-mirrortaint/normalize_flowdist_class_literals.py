#!/usr/bin/env python3
"""Repair descriptor-wrapped CONSTANT_Class names emitted by old Soot.

Clone UTF8 constants and change only CONSTANT_Class name references. Preserve
business strings, bytecode, branch probes and every original constant-pool index.
Always write a fresh output tree and an explicit change manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def canonical(name):
    while name.startswith('L') and name.endswith(';'):
        name=name[1:-1]
    if name.startswith('['):
        n=len(name)-len(name.lstrip('['));tail=name[n:]
        if tail.startswith('L') and tail.endswith(';'):
            name='['*n+'L'+canonical(tail[1:-1])+';'
    return name


def normalize(data):
    if data[:4]!=b'\xca\xfe\xba\xbe':raise ValueError('Invalid class file')
    count=struct.unpack_from('>H',data,8)[0];pos=10;i=1;utf={};refs=[]
    sizes={3:4,4:4,5:8,6:8,7:2,8:2,9:4,10:4,11:4,12:4,15:3,16:2,17:4,18:4,19:2,20:2}
    while i<count:
        tag=data[pos];pos+=1
        if tag==1:
            n=struct.unpack_from('>H',data,pos)[0];pos+=2;utf[i]=data[pos:pos+n];pos+=n
        elif tag in sizes:
            if tag==7:refs.append((i,pos,struct.unpack_from('>H',data,pos)[0]))
            pos+=sizes[tag]
            if tag in (5,6):i+=1
        else:raise ValueError('Unsupported constant pool tag: '+str(tag))
        i+=1
    pool=bytearray(data[10:pos]);extra=bytearray();changes=[];new_names={}
    for index,offset,name_index in refs:
        raw=utf[name_index]
        # Class names here are ASCII in the pinned inputs; leave other names
        # untouched rather than misinterpreting modified UTF-8 business data.
        try:name=raw.decode('ascii')
        except UnicodeDecodeError:continue
        fixed=canonical(name)
        if fixed==name:continue
        encoded=fixed.encode('ascii')
        if encoded not in new_names:
            if count+len(new_names)>=65535:raise ValueError('Constant pool overflow')
            new_names[encoded]=count+len(new_names)
            extra+=b'\x01'+struct.pack('>H',len(encoded))+encoded
        struct.pack_into('>H',pool,offset-10,new_names[encoded])
        changes.append({'class_constant_index':index,'original':name,'canonical':fixed})
    if not changes:return data,[]
    return data[:8]+struct.pack('>H',count+len(new_names))+pool+extra+data[pos:],changes


def run(source,out):
    out.mkdir(parents=True,exist_ok=False);changes={};hashes={}
    for file in sorted(source.rglob('*')):
        if not file.is_file():continue
        relative=file.relative_to(source);target=out/relative;target.parent.mkdir(parents=True,exist_ok=True)
        data=file.read_bytes()
        if file.suffix=='.class':
            fixed,rows=normalize(data)
            if rows:changes[str(relative)]=rows
        else:fixed=data
        target.write_bytes(fixed)
        hashes[str(relative)]={'input':hashlib.sha256(data).hexdigest(),'output':hashlib.sha256(fixed).hexdigest()}
    manifest={'kind':'soot-class-literal-compatibility','input':str(source),'changes':changes,
        'sha256':hashes,'original_bytecode_instructions_modified':False,'business_utf8_constants_modified':False,
        'accuracy_eligible':False,'performance_eligible':False}
    (out/'class-literal-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Repaired',sum(len(v) for v in changes.values()),'class references in',len(changes),'classes')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.input.resolve(),a.out.resolve())
