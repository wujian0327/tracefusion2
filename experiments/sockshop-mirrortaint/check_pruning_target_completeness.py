"""Business-response target denominator, independent of provenance and labels."""
import argparse,json,collections
from pathlib import Path
from run_planned_service import load,save,sha
from infer_response_binding import matches

def scalar_paths(value,prefix=''):
 if isinstance(value,dict):
  for key,item in value.items():yield from scalar_paths(item,prefix+'/'+str(key).replace('~','~0').replace('/','~1'))
 elif isinstance(value,list):
  for i,item in enumerate(value):yield from scalar_paths(item,prefix+'/'+str(i))
 else:yield prefix

def run(trial,planfile):
 pattern=load(planfile)['response_binding']['path'];cases=load(trial/'warmup.json')['requests']+load(trial/'measure.json')['requests'];rows=[json.loads(x)for x in(trial/'capture/events.jsonl').read_text().splitlines()];bound=collections.defaultdict(list)
 for r in rows:
  if r['kind']=='binding-return':bound[r.get('message')].extend(f['path']for f in r['fields']if matches(pattern,f['path']))
 checks=[]
 for c in cases:
  expected=sorted(p for p in scalar_paths(c['response'])if matches(pattern,p));actual=sorted(bound[c['message']]);assert actual==expected,(c['case'],expected,actual)
  checks.append({'case':c['case'],'expected_target_paths':expected,'bound_target_paths':actual})
 result={'passed':True,'pattern':pattern,'requests':len(cases),'expected_targets':sum(len(c['expected_target_paths'])for c in checks),'no_target_requests':sum(not c['expected_target_paths']for c in checks),'null_is_scalar_empty_list_has_no_member':True,'provenance_graph_or_labels_used_as_truth':False,'plan_sha256':sha(planfile),'checks':checks}
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--trial',required=True,type=Path);p.add_argument('--plan',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();save(a.out,run(a.trial,a.plan))
