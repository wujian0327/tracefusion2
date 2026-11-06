"""Independent expected accept/reject cases for raw candidate indexing."""
import copy
from raw_source_call_facts import RawSourceCallFacts
from audit_zlt_foundation_revision import tf_pair

def run():
 checks=[]
 for scope in('planned','observation-only-call'):
  start={'kind':'collection-call-enter','call_id':7,'seq':1,'frame':'f1','callee':'Store.read()Ljava/lang/Object;','method':'Root.go()V','pc':4};end={**start,'kind':'collection-call-exit','seq':3};source={'kind':'binding-source','source_call_id':7,'seq':2,'frame':'f1','callee':start['callee'],'source_caller_method':start['method'],'source_pc':4,'source_scope':scope}
  if scope=='observation-only-call':
   for row,kind in((start,'source-call-enter'),(end,'source-call-exit')):row.update(kind=kind,source_call_id=7,observation_frame='o1',caller_method='Root.go()V')
   source['source_observation_frame']='o1'
  for fault in('valid','duplicate-start','duplicate-end','missing-end','wrong-frame','wrong-caller','wrong-pc','wrong-callee','wrong-interval','missing-call-id'):
   rows=copy.deepcopy([start,source,end]);s=rows[1]
   if fault=='duplicate-start':rows.insert(0,copy.deepcopy(rows[0]))
   elif fault=='duplicate-end':rows.append(copy.deepcopy(rows[-1]))
   elif fault=='missing-end':rows.pop()
   elif fault=='wrong-frame':s['frame']='other'
   elif fault=='wrong-caller':s['source_caller_method']='Wrong.go()V'
   elif fault=='wrong-pc':s['source_pc']=5
   elif fault=='wrong-callee':s['callee']='Wrong.read()Ljava/lang/Object;'
   elif fault=='wrong-interval':s['seq']=4
   elif fault=='missing-call-id':s.pop('source_call_id')
   index=RawSourceCallFacts(rows);out=[]
   for candidate_rows in(rows,index.matching(rows,s)):
    try:out.append(('accepted',tf_pair(candidate_rows,s)))
    except ValueError as error:out.append(('rejected',str(error)))
   assert out[0]==out[1]and(out[0][0]=='accepted')==(fault=='valid'),(scope,fault,out)
   checks.append({'scope':scope,'fault':fault,'state':out[0][0]})
  try:RawSourceCallFacts(rows).matching(list(rows),s)
  except ValueError:pass
  else:raise AssertionError('Cross-capture index reused')
 return checks
if __name__=='__main__':
 import json
 print(json.dumps({'checks':run(),'cross_capture_rejected':True},indent=2))
