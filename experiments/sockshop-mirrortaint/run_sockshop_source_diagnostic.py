#!/usr/bin/env python3
"""One legal association experiment; no business JAR or TF inference oracle."""
import argparse,copy,json
from run_planned_service import save,load,sha
import run_sockshop_model_revision as n


def run(out,base):
    old=n.old;q=next(q for q in old.queries('development') if q['id']=='sockshop-orders-newOrder-customer-firstName')
    out.mkdir();plan=old.plan_response(load(base/'orders/model.json'),q['entry'],q['target'],q['path'],read_forward_contracts=True);plan['source_evidence']=True
    build=out/'build';old.query_build(build,base,q,plan);dest=out/'capture';dest.mkdir();save(out/'query.json',q)
    original_spec=old.spec_for;original_prepare=old.prepare
    def spec(*args):
        value=original_spec(*args);value['services']['user']['ports']=['127.0.0.1:18584:80'];return value
    def prepare(case,case_id,cd,front,cart):
        prepared=original_prepare(case,case_id,cd,front,cart)
        if case_id!='group-0':return prepared
        cl=prepared[1];fixture=prepared[2];url='http://127.0.0.1:18584';uid=fixture['customer_id'];facts={}
        for kind in ('addresses','cards'):facts['before-'+kind]=cl.request('GET',url+'/customers/'+uid+'/'+kind,label='independent-before-association')
        facts['created-address']=cl.request('POST',url+'/addresses',{**fixture['address'],'userID':uid},label='legal-associate-address')
        facts['created-card']=cl.request('POST',url+'/cards',{**fixture['card'],'userID':uid},label='legal-associate-card')
        for path in ('customers/'+uid,'customers/'+uid+'/addresses','customers/'+uid+'/cards'):
            facts['after-'+path]=cl.request('GET',url+'/'+path,label='independent-after-association')
        save(cd/'legal-association.json',facts);return prepared
    old.spec_for=spec;old.prepare=prepare
    try:old.capture_sock(dest,build,q,20261020)
    finally:old.spec_for=original_spec;old.prepare=original_prepare
    rows={'orders':[json.loads(x) for x in (dest/'orders/events.jsonl').read_text().splitlines()]};result=[]
    for case in load(dest/'run.json')['cases']:
        for path in ('/card/id','/customer/id','/address/id','/customer/username'):
            item={'case':case['case'],'path':path,'expected':n.oracle(q,case,path,rows)};result.append(item)
    save(out/'independent-four-query-oracles.json',{'items':result,'oracle_available':len(result),'uses_tf_propagation':False,
        'ignored_id_contract':'Raw id is ignored by original ResourceSupport/Jackson unwrapped content; expected default-null data source is empty.',
        'library_probe':'HateoasOracleProbe.java, run without TF agent on each captured original response.'})
    old.oracle=n.oracle;old.evaluate(dest,build,q)
    print({'oracle_targets':len(result),'capture':str(dest)},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=n.Path,required=True);p.add_argument('--base',type=n.Path,required=True);a=p.parse_args();run(a.out.resolve(),a.base.resolve())
