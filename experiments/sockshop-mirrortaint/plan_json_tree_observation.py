"""Physical source-container observation, not Fastjson decoding semantics."""
import json
from pathlib import Path
from contract_applicability import select
def attach(plan,model):
    contract=json.loads(Path(__file__).with_name('json-tree-observation-contracts-20261105.json').read_text())
    selected=select(contract,model.get('library_inventory',{}))
    if selected:plan['json_tree_observation']=selected
    return plan
