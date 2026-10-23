#!/usr/bin/env python3
"""Inspect original raw facts for12 heldout unknowns, without TF graph queries."""
import argparse,base64,hashlib,json
from pathlib import Path
from urllib.parse import urlparse
from run_planned_service import ROOT,load,save,sha


def run(out):
    out.mkdir(parents=True,exist_ok=False);root=ROOT/'artifacts/heldout29-first-20261023/orders-first';records=[]
    for mode in ('full','selective'):
        for field in ('id','customerId'):
            d=root/(mode+'-sockshop-orders-newOrder-'+field);file=d/'capture/orders/events.jsonl';rows=[json.loads(l)for l in file.open()];starts={r['call_id']:r for r in rows if r['kind']=='collection-call-enter'}
            for c in load(d/'capture/run.json')['cases']:
                ret=next(r for r in rows if r['kind']=='binding-return'and r.get('message')==c['message']);entry=next(r for r in rows if r['kind']=='enter'and r['frame']==ret['frame']);local=[r for r in rows if entry['seq']<=r['seq']<=ret['seq']];record={'mode':mode,'field':field,'case':c['case'],'message':c['message'],'events_sha256':sha(file),'can_decide_independent_source_set':False}
                if field=='id':
                    facts=[r for r in local if r['kind']=='mongo-save-effect'and r.get('id_write',{}).get('observed',{}).get('value')==c['response']['id']];assert len(facts)==1;s=facts[0];w=s['id_write'];assert s['entity']==s['result']and s['id_before'].get('value')is None and s['valid']and s['callback_invocations']==0
                    record.update(target_write=w,save_call_id=s['call_id'],native_generator_configuration=[v['id_generator']for v in s['date_codecs']],generator_configuration_class_hashes=[v['class_sha256']['org/bson/codecs/ObjectIdGenerator']for v in s['date_codecs']],missing='Actual ID-generator invocation/result/document binding, distinct from observing a configured generator and the later target ID write. No target write is moved to the source boundary.')
                else:
                    facts=[r for r in rows if r['kind']=='http-source-fact'and r.get('parent_message')==c['message']and urlparse(r.get('uri','')).path=='/customers/'+c['fixture']['customer_id']];assert len(facts)==1;s=facts[0];raw=base64.b64decode(s['raw_base64']);assert s['document_complete']and hashlib.sha256(raw).hexdigest()==s['raw_sha256'];href=json.loads(raw)['_links']['self']['href']
                    links=[r for r in local if r.get('request_entity_contract',{}).get('kind')=='resource-link'and starts[r['call_id']]['receiver']['object']==s['body_object']];assert len(links)==1;link=links[0]
                    hrefs=[r for r in local if r.get('request_entity_contract',{}).get('kind')=='link-href'and starts[r['call_id']]['receiver']['object']==link['result']['object']];assert len(hrefs)==1 and hrefs[0]['result']['value']==href
                    assert urlparse(href).path.rstrip('/').rsplit('/',1)[-1]==c['response']['customerId'];physical=[f for f in s['fields']if f['path']=='/_links/self/href'];assert not physical
                    record.update(wire_path='/_links/self/href',raw_sha256=s['raw_sha256'],rpc_message=s['message'],decoded_resource=s['body_object'],actual_link_object=link['result']['object'],link_call_id=link['call_id'],href_call_id=hrefs[0]['call_id'],missing='Decoded Link.href field/read-stage coordinate and verified association to the actual incoming message projection. Raw value plus later matching return is not a physical source-field version.')
                records.append(record)
    assert len(records)==24
    save(out/'audit.json',{'completed':True,'targets_per_mode':12,'raw_target_instances_inspected':24,'new_source_answers':0,'TF_propagation_or_graph_called':False,'existing_oracle_unavailable_not_relabelled':True,'records':records,'script_sha256':sha(Path(__file__))})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out.resolve())
