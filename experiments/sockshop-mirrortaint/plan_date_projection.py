"""Finite exact Date projection; never a save/async preservation summary."""
import json
from pathlib import Path

def attach_date_projection(plan,model):
    if not plan.get('target'):return plan
    target=plan['target'];owner,name=target.rsplit('.',1)
    field=next(f for f in model['classes'][owner]['fields'] if f['name']==name)
    methods=plan.get('execution_kernel',{}).get('methods',{})
    needed=field['desc']=='Ljava/util/Date;' or any(i.get('owner') in ('java/util/Date','java/util/Calendar') for m in methods.values() for i in m['instructions'])
    if needed and 'date_projection' not in plan:
        plan['date_projection']=json.loads(Path(__file__).with_name('date-runtime-contracts-20261020.json').read_text())
        if plan.get('read_forward_contracts'):
            plan['read_forward_contracts']['runtime_profiles']+=plan['date_projection'].get('read_runtime_profiles',[])
        plan['contracts'].append('Exact Date identity plus observed epoch; modeled read/copy/newDate(long), fresh default Calendar time is environment-derived. Unexplained mutation/save/async never establishes preservation.')
    if needed:
        plan['date_effects']=json.loads(Path(__file__).with_name('date-effects-contracts-20261021.json').read_text())
    return plan
