"""Tamper certificates, including consistent substitutions across copied witnesses."""
import argparse,copy,json
from pathlib import Path
from run_planned_service import load,save
from infer_execution_kernel import infer_execution

def audit(root,out):
 out.mkdir(parents=True,exist_ok=False);plan=load(root/'build/fixture/plan.json');report={}
 for mode in ('full','selective'):
  rows=[json.loads(s)for s in(root/mode/'events.jsonl').read_text().splitlines()]
  original=infer_execution(plan,rows);checks={}
  for fault in ('missing-config','factory-matches-used-type','custom-factory-modifier','wrong-callback-hash','custom-introspector','wrong-property-decoder','missing-object-token','wrong-caller-depth','wrong-thread','wrong-birth-kind','wrong-graph-type','wrong-method-corridor','fake-cache-scope','missing-source-finish','missing-source-fact','wrong-source-call-id','unknown-type-modifier','missing-type-modifiers','parameterized-root','root-value-handler','annotation-proof','mixin-proof','property-lookup-proof','handler-used'):
   bad=copy.deepcopy(rows);end=next(r for r in bad if r['kind']=='locality-end'and r['valid']);oid=end['ownership_id'];fam=[r for r in bad if r.get('ownership_id')==oid];read=next(r for r in fam if r['kind']=='locality-reader');dec=next(r for r in fam if r['kind']=='locality-decoded');factory=next(r for r in fam if r['kind']=='locality-factory-config');confs=[read,dec['reader_configuration'],end['reader_configuration']]
   if fault=='missing-config':bad.remove(factory)
   elif fault in ('factory-matches-used-type','custom-factory-modifier','wrong-callback-hash'):
    configs=[c['factory_configuration']for c in confs]+[factory]
    for c in configs:
     if fault=='custom-factory-modifier':c['_modifiers']=[{'class':'custom'}]
     else:c['_additionalDeserializers']=[{'class':'com/fasterxml/jackson/databind/module/SimpleDeserializers','class_sha256':'bad'if fault=='wrong-callback-hash'else plan['execution_kernel']['source_locality']['class_sha256']['com/fasterxml/jackson/databind/module/SimpleDeserializers'],'rule':'exact-map-no-used-type','mapped_types':[read['bean']]if fault=='factory-matches-used-type'else[]}]
   elif fault in ('unknown-type-modifier','missing-type-modifiers','parameterized-root','root-value-handler','annotation-proof','mixin-proof','property-lookup-proof','handler-used'):
    for c in confs:
     if fault=='unknown-type-modifier':c['type_factory_configuration']['modifiers']=[{'class':'custom','class_sha256':'bad'}]
     elif fault=='missing-type-modifiers':c['type_factory_configuration'].pop('modifiers',None)
     elif fault=='parameterized-root':c['root_type_configuration']['binding_count']=1
     elif fault=='root-value-handler':c['root_type_configuration']['value_handler']='custom'
     elif fault=='annotation-proof':c['annotation_free']=False
     elif fault=='mixin-proof':c['mixin_configuration']['local_count']=1
    if fault in ('property-lookup-proof','handler-used'):
     for c in (dec,end):c['property_lookup_consistent']=False if fault=='property-lookup-proof'else True;c['handler_uses']=1 if fault=='handler-used'else 0
   elif fault=='custom-introspector':
    for c in confs:c['introspectors']=['custom']
   elif fault=='wrong-property-decoder':
    for c in (dec,end):c['properties'][0]['decoder']='custom'
   elif fault=='missing-object-token':
    for c in (dec,end):c['object_token']=False
   elif fault=='wrong-caller-depth':
    for c in (dec,end):c['caller_bottom']+=1
   elif fault=='wrong-thread':read['thread']=-1
   elif fault=='wrong-birth-kind':next(r for r in fam if r['kind']=='locality-birth'and r['object']==end['body'])['birth_kind']='unproved'
   elif fault=='wrong-graph-type':
    for c in (dec,end):c['objects'][0]['type']='other'
   elif fault=='wrong-method-corridor':
    for c in (dec,end):c['corridor'][0]='feign/SynchronousMethodHandler.unreviewed'
   elif fault=='fake-cache-scope':
    for c in (dec,end):c['cache_scope']=True
   elif fault=='missing-source-finish':bad.remove(next(r for r in bad if r['kind']=='collection-call-exit'and r['call_id']==end['call_id']))
   elif fault=='missing-source-fact':bad.remove(next(r for r in bad if r['kind']=='binding-source'and r.get('source_call_id')==end['call_id']))
   elif fault=='wrong-source-call-id':next(r for r in bad if r['kind']=='binding-source'and r.get('source_call_id')==end['call_id'])['source_call_id']=-1
   try:infer_execution(plan,bad)
   except ValueError as e:checks[fault]={'rejected':True,'reason':str(e)}
   else:raise AssertionError('Corrupted certificate accepted: '+fault)
  # Module and custom-factory cases are actual executions, not edited logs.
  ends=[r for r in rows if r['kind']=='locality-end'and r['readers']]
  require=lambda b: b or (_ for _ in ()).throw(AssertionError('Factory controls missing'))
  require(any(r['valid']and len(r['reader_configuration']['introspectors'])>1 for r in ends))
  for n in (13,14,19,23):
   frames={r['frame']for r in rows if r['kind']=='enter'and r['method']==plan['entry']and r['args'][0].get('value')==n}
   require(sum(not r['valid']and bool(r['reason'])for r in ends if r['caller_frame']in frames)==2)
  for n,valid in ((15,True),(16,False),(17,False)):
   frames={r['frame']for r in rows if r['kind']=='enter'and r['method']==plan['entry']and r['args'][0].get('value')==n}
   require(sum(r['valid']==valid for r in ends if r['caller_frame']in frames)==2)
  constants=[]
  for r in rows:
   if r['kind']!='enter'or r['method']!=plan['entry']or r['args'][0].get('value')!=4:continue
   source=next(x for x in rows if x['kind']=='binding-source'and x['frame']==r['frame']);field=next(f for f in source['fields']if f['field']=='SourceLocalityFixture$Result.message')
   writes=[x for x in rows if x['kind']=='write'and x['owner']==field['owner']and x['field']==field['field']and x['seq']>source['seq']]
   require(len(writes)==1 and writes[0]['version']>field['version']and writes[0]['observed']['value']==field['observed']['value']);constants.append(True)
  require(len(constants)==2)
  report[mode]={'context_escape_with_actual_object_identity_denied':True,'source_exception_scope_closes':True,'same_value_overwrite_new_version':2,'actual_cache_negative':True,'targets':len(original['answers']),'guards':checks,'actual_module_and_callback_controls':True}
 save(out/'results.json',{'all_passed':True,'modes':report});print({m:len(r['guards'])for m,r in report.items()})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.root,a.out)
