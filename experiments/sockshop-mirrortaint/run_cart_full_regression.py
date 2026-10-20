#!/usr/bin/env python3
"""Full collector correctness only, on separate ports/subnet from selective."""
import argparse
from pathlib import Path
import run_sockshop_model_revision as n


def run(out,base):
    old=n.old;original_spec=old.spec_for;original_prepare=old.prepare;original_raw=old.request_raw
    def spec(*args):
        s=original_spec(*args)
        for cfg in s['services'].values():
            cfg['ports']=[p.replace('18580','19580').replace('18581','19581').replace('18582','19582').replace('18583','19583') for p in cfg.get('ports',[])]
            if 'JAVA_OPTS' in cfg.get('environment',{}):cfg['environment']['JAVA_OPTS']=cfg['environment']['JAVA_OPTS'].replace('-Dservice.mode=selective','-Dservice.mode=full')
        s['networks']={'default':{'ipam':{'config':[{'subnet':'10.254.247.0/24'}]}}};return s
    def prepare(case,ident,dest,front,cart):return original_prepare(case,ident,dest,front.replace(':18580',':19580'),cart.replace(':18581',':19581'))
    def raw(client,method,url,body=None):return original_raw(client,method,url.replace(':18581',':19581'),body)
    old.spec_for=spec;old.prepare=prepare;old.request_raw=raw
    try:n.capture(out,base)
    finally:old.spec_for=original_spec;old.prepare=original_prepare;old.request_raw=original_raw

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.base.resolve())
