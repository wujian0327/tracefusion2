"""Finite framework tail forwarding, never a business aspect summary."""
import json
from pathlib import Path
from contract_applicability import select

def attach(plan,model):
    contract=json.loads(Path(__file__).with_name('before-dispatch-contracts-20261105.json').read_text())
    supported=select(contract,model.get('library_inventory',{}))
    dispatch=plan.get('execution_kernel',{}).get('direct_dispatch_contract')
    if supported and dispatch: dispatch['before_only']=supported
    return plan
