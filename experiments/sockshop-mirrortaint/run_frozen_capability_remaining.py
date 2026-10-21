#!/usr/bin/env python3
"""Wait for the isolated Orders phase, then run disjoint capability workers."""
import argparse,os,signal,subprocess,time
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save

def run(root):
    orders=root/'all62-orders-serial';jobs=[]
    while not (orders/'cleanup.json').exists():time.sleep(5)
    cleanup=load(orders/'cleanup.json');result=load(orders/'results.json')
    if cleanup['status']!='completed' or cleanup['cleanup_returncode'] or not result['complete']:
        save(root/'remaining-phase.json',{'status':'orders-needs-review','cleanup':cleanup});raise ValueError('Orders phase requires review before scheduling the remaining workers')
    from run_frozen_orders_business_repeats import run as repeat_business
    repeat_business(root)
    commands=[('reads',['python3',str(HERE/'run_frozen_capability_acceptance.py')],{'TF2_CAPABILITY_ROLES':'station,train,price','TF2_CAPABILITY_PORT':'18820'}),('route',['python3',str(HERE/'run_frozen_capability_acceptance.py')],{'TF2_CAPABILITY_ROLES':'route','TF2_CAPABILITY_PORT':'18920'}),('travel',['python3',str(HERE/'run_frozen_capability_acceptance.py')],{'TF2_CAPABILITY_ROLES':'basic,ticketinfo','TF2_CAPABILITY_PORT':'19020'}),('cart',['python3',str(HERE/'run_frozen_capability_sock.py'),'carts'],{}),('pair',['python3',str(HERE/'run_frozen_capability_pair.py')],{})]
    try:
        for name,cmd,env in commands:
            dest=root/('cart-create-pair'if name=='pair'else'all62-'+name);log=(root.parent/'logs'/('16-final-'+name+'.log')).open('w');p=subprocess.Popen(cmd+['--out',str(dest),'--base-build',str(root/'frozen-base')],cwd=ROOT,env={**os.environ,**env},stdout=log,stderr=subprocess.STDOUT,start_new_session=True);jobs.append((name,p,log));print({'started':name,'pid':p.pid},flush=True)
        while any(p.poll()is None for _,p,_ in jobs):
            save(root/'remaining-phase.json',{'status':'running','workers':{n:p.poll()for n,p,_ in jobs}});time.sleep(5)
        codes={n:p.returncode for n,p,_ in jobs};save(root/'remaining-phase.json',{'status':'completed'if not any(codes.values())else'needs-review','workers':codes});assert not any(codes.values()),codes
    finally:
        for _,p,log in jobs:
            if p.poll()is None:os.killpg(p.pid,signal.SIGINT)
        for _,p,log in jobs:
            if p.poll()is None:p.wait(timeout=180)
            log.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();run(a.root.resolve())
