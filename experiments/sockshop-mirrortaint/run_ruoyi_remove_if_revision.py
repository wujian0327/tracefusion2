"""Original C1 inputs; list filtering, dictionary diagnosis and positive preservation."""
import argparse
from pathlib import Path
from run_planned_service import load
from run_ruoyi_request_scope_revision import prepare, run

QUERIES=('ruoyi-2','ruoyi-3','ruoyi-1')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage', choices=('prepare','run'))
    p.add_argument('--home',type=Path,required=True);a=p.parse_args();h=a.home.resolve()
    assert load(h/'algorithm-freeze.json')['selected_queries']==list(QUERIES)
    if a.stage=='prepare': prepare(h/'final-C1', h/'candidate')
    else:
        for q in QUERIES: run(h/'final-C1', h/'candidate', q)
