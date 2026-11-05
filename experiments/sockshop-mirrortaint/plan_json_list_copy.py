"""Select only the reviewed Fastjson existing-element branch."""
import json
from pathlib import Path
from contract_applicability import select
def attach(plan,model):
    contract=json.loads(Path(__file__).with_name('json-list-copy-contracts-20261105.json').read_text())
    chosen=select(contract,model.get('library_inventory',{}))
    if chosen and plan.get('json_tree_observation'):plan['json_list_copy']=chosen
    return plan
