#!/usr/bin/env python3
"""Historical original-JAR regression, with an explicitly isolated lab subnet."""
import argparse
from pathlib import Path
import run_distributed_paths as paths
from run_planned_service import save,sha


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('application',choices=('sockshop','trainticket'));p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args()
    original_pin=paths.pin_images
    def pin(spec,application):
        spec=original_pin(spec,application)
        if application=='trainticket':spec['networks']={'default':{'ipam':{'config':[{'subnet':'10.254.248.0/24'}]}}}
        return spec
    paths.pin_images=pin
    save(a.out/'regression-network.json',{'driver_sha256':sha(Path(__file__)),'train_subnet':'10.254.248.0/24','reason':'Isolate correctness deployment from other task-owned lab projects; no performance comparison.'})
    if a.application=='sockshop':paths.capture_sockshop(a.out.resolve(),a.build.resolve())
    else:paths.capture_train(a.out.resolve(),a.build.resolve())
