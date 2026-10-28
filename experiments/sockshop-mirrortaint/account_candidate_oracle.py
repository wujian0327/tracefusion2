"""Independent original-code/DB/raw-instance oracle. No inference/tag imports."""
import portability_piggy_oracle as original

def expected(case,home,rows,path):
 checks=original.account_return_checks(case,home);before=original.database(home/(case['api']+'-'+case['case']+'-database-before.jsonl'));name=case['body']['username']
 assert all(not[d for d in before.get(k,[])if d['_id']==name]for k in(('piggy-account','accounts'),('piggy-auth','users'))),'Related original reads differ'
 roots=[r for r in rows if r['kind']=='binding-return'and r.get('message')==case['message']];assert len(roots)==1
 targets=[f for f in roots[0]['fields']if f['path']==path];assert len(targets)==1
 rule=original.return_rule('piggymetrics-2',path);assert rule['source']!='unresolved';sources=[]
 if rule['source']:
  args=[r for r in rows if r['kind']=='binding-input'and r['frame']==roots[0]['frame']and r['argument']==0];assert len(args)==1
  fields=[f for f in args[0]['fields']if f['path']=='/username'];assert len(fields)==1 and fields[0]['observed']['value']==case['body']['username'];f=fields[0];sources=[('piggy-account',args[0].get('message'),args[0]['frame'],args[0]['seq'],f['owner'],f['field'],f['version'],f['path'])]
 return {'rule':rule,'checks':checks,'sources':sources,'target':targets[0],'root_frame':roots[0]['frame']}
