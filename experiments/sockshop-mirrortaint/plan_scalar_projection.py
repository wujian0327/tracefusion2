"""Select a finite actual-library projection, independent of target answers."""
import json
from pathlib import Path

def attach(plan,model):
 contract=json.loads(Path(__file__).with_name('scalar-projection-contracts-20261028.json').read_text());actual=model.get('library_inventory',{}).get('classes',{})
 if plan.get('execution_kernel')and all(actual.get(k)==v for k,v in contract['class_sha256'].items()):plan['scalar_projection']=contract
 return plan
