"""Compare fixed-task answers after each JVM passed its own raw oracle."""
import argparse,json
from infer_execution_kernel import infer_execution
from run_planned_service import load,save,sha
from run_jvm_rule_revision import H,verify

def run(out):
 verify();out.mkdir(parents=True,exist_ok=False);checks=[]
 for tier in ('low','medium','high','related-high'):
  signatures={}
  for mode in ('full','selective'):
   root=H/'pilot'/(tier+'-'+mode);rows=[json.loads(s)for s in(root/'capture/events.jsonl').read_text().splitlines()]
   plan=load(H/'controlled-build-04'/tier/'plan.json');replay=infer_execution(plan,rows);by={r['seq']:r for r in rows};signatures[mode]=[]
   for answer in replay['answers']:
    if answer['path']!='/target':continue
    normalized=[]
    for token in answer['origins']:
     assert token[0]=='field';source=by[token[1]];field=source['fields'][token[2]]
     normalized.append((source['callee'],field['path'],field['field'],field['version']))
    # These fixed straight-line tasks carry no selection inputs. Do not claim
    # that this normalization supports arbitrary selector coordinate formats.
    assert not answer['selectors']
    signatures[mode].append((answer['known'],answer['version'],sorted(normalized),answer['selectors']))
   assert len(signatures[mode])==6
  assert signatures['full']==signatures['selective'],tier
  checks.append({'tier':tier,'paired_targets':6,'known_version_source_occurrences_selectors_equal':True,'origins_per_target':len(signatures['full'][0][2]),'target_version':signatures['full'][0][1],'selectors_empty_in_these_tasks':True})
 save(out/'results.json',{'checks':checks,'cross_jvm_object_ids_compared':False,'condition':'One declared Store.read occurrence per root; independently paired raw source facts and scored predictions retained in pilot audits.'})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=__import__('pathlib').Path);run(p.parse_args().out.resolve())
