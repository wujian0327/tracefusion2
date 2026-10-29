"""Select versioned observation obligations, never propagation or source answers."""
import json
from pathlib import Path
from contract_applicability import select

def attach(plan,model):
    contract=json.loads(Path(__file__).with_name('communication-identity-contracts-20261029.json').read_text())
    selected=select(contract,model.get('library_inventory',{}))
    if selected:
        plan['communication_identity']=selected
        plan.setdefault('contracts',[]).append('Communication v2: actual client attempts, request/response identity lineage and codec roles; no coordinates synthesized for legacy captures.')
    return plan
