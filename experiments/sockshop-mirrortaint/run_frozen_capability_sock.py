#!/usr/bin/env python3
import argparse
from pathlib import Path
import run_frozen_capability_acceptance as driver
p=argparse.ArgumentParser();p.add_argument('worker',choices=['carts','orders']);p.add_argument('--out',required=True,type=Path);p.add_argument('--base-build',required=True,type=Path);a=p.parse_args();getattr(driver,a.worker)(a.out.resolve(),a.base_build.resolve())
