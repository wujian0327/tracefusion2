#!/usr/bin/env python3
"""Adapt the historical two-request control's input schema for feasibility probes.

Its run.json predates case/http_status fields; successful client responses and
frozen source answers are unchanged. Preserve first probe KeyError receipts.
"""
import argparse,importlib
from pathlib import Path
from run_planned_service import load,save,sha


def run(root,out,kind):
    out.mkdir(parents=True,exist_ok=False);inputs=out/'inputs';inputs.mkdir();(inputs/'cart-create-pair').symlink_to(root/'cart-create-pair',target_is_directory=True)
    module=importlib.import_module('probe_query_output_projection'if kind=='projection'else 'probe_transport_observation_scope');original=module.load
    def adapted(path):
        value=original(path)
        if path.name=='run.json'and 'cart-create-pair'in str(path):
            for c in value['cases']:c.setdefault('http_status',200);c.setdefault('case','request-'+str(c['index']))
        return value
    module.load=adapted
    save(out/'adapter.json',{'scope':'Historical successful two-request schema adapter for in-memory before/after answer equality only; no capture, truth, algorithm or HTTP request changed.','original_run_sha256':{mode:sha(root/'cart-create-pair'/mode/'capture/run.json')for mode in ('full','selective')},'module_sha256':sha(Path(module.__file__)),'adapter_sha256':sha(Path(__file__))})
    module.probe(inputs,out/'results')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--kind',choices=('projection','scope'),required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve(),a.kind)
