import json
from pathlib import Path
from contract_applicability import select
def attach(plan,model):
    contract=json.loads(Path(__file__).with_name('commons-literal-contracts-20261105.json').read_text())
    selected=select(contract,model.get('library_inventory',{}))
    if selected and plan.get('execution_kernel'):
        calls={}
        for method in plan['execution_kernel']['methods'].values():
            for ins in method['instructions']:
                if ins['op']!=184:continue
                suffix=ins.get('name','')+ins.get('desc','')
                target={'split(Ljava/lang/String;Ljava/lang/String;)[Ljava/lang/String;':'org/apache/commons/lang3/StringUtils',
                        'contains([Ljava/lang/Object;Ljava/lang/Object;)Z':'org/apache/commons/lang3/ArrayUtils'}.get(suffix)
                if not target:continue
                owner=ins['owner'];chain=[];seen=set()
                while owner!=target and owner in model['classes']and owner not in seen:
                    seen.add(owner)
                    if owner+'.'+suffix in model['methods']:break
                    cls=model['classes'][owner];chain.append({'class':owner,'sha256':cls['sha256']});owner=cls['super']
                if owner==target:calls[ins['owner']+'.'+suffix]={'declaring':target,'chain':chain}
        selected['resolved_calls']=calls
        plan['execution_kernel']['commons_literals']=selected
    return plan
