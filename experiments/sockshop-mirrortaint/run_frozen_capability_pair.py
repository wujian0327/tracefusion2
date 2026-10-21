#!/usr/bin/env python3
"""Exact two original create/repeat inputs, using the pre-frozen query plan."""
import argparse,copy
from pathlib import Path
import run_cart_reread_baseline_pair as pair
import run_frozen_capability_acceptance as frozen
q=next(q for q in frozen.QUERIES if q['id']=='sockshop-carts-get-customerId')
pair.plan_response=lambda *args,**kw:copy.deepcopy(frozen.plan(q))
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--base-build',type=Path,required=True);a=p.parse_args();frozen.check();pair.run(a.out.resolve(),a.base_build.resolve())
