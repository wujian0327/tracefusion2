#!/usr/bin/env python3
"""Seal new root-method queries from declared business response contracts only."""
import argparse,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
from run_planned_service import ROOT,HERE,load,save,sha


def seal(out):
    out.mkdir(parents=True,exist_ok=False)
    base=ROOT/'artifacts/transport-observation-shared-20261023/frozen-base'
    catalogue=[('station','fdse/microservice/service/StationServiceImpl','create','fdse.microservice.entity.Station','POST /api/v1/stationservice/stations'),
               ('station','fdse/microservice/service/StationServiceImpl','update','fdse.microservice.entity.Station','PUT /api/v1/stationservice/stations'),
               ('route','route/service/RouteServiceImpl','createAndModify','route.entity.Route','POST /api/v1/routeservice/routes'),
               ('price','price/service/PriceServiceImpl','createNewPriceConfig','price.entity.PriceConfig','POST /api/v1/priceservice/prices'),
               ('price','price/service/PriceServiceImpl','updatePriceConfig','price.entity.PriceConfig','PUT /api/v1/priceservice/prices')]
    old=load(HERE/'query-coverage-pool-20261019.json');old_entries={q['entry']for q in old['candidates']+old['excluded_known_targets']}
    candidates=[];models={};jars={}
    for role,owner,name,dto,http in catalogue:
        model=load(base/role/'model.json');models[role]=sha(base/role/'model.json');jars[role]=sha(base/role/'original.jar')
        methods=[k for k,m in model['methods'].items()if m['owner']==owner and m['name']==name and m['access']&1]
        assert len(methods)==1 and methods[0]not in old_entries
        for f in model['classes'][dto.replace('.','/')]['fields']:
            if f['access']&8:continue
            # Every declared domain DTO field is included; list fields use a
            # wildcard family. No planner, instruction support test or runtime.
            path='/data/'+f['name']+('/*'if f['desc']=='Ljava/util/List;'else '')
            candidates.append({'id':'heldout-closure-'+role+'-'+name+'-'+f['name'],'application':'trainticket','role':role,'entry':methods[0],'target':dto+'.'+f['name'],'path':path,'http':http,'novelty':'new service entry with creation/update semantics; class may have been inspected before','source_boundary':{'scope':'Original entry arguments, repository read-return fields/elements and actual RPC reads; save/output are not new sources','selection_origins':'separate, not merged into data dependencies'},'manual_configuration':{'entry':1,'target_path':1,'source_boundary':1,'per_query_propagation_rules':0}})
    assert len(candidates)==21
    result={'schema':1,'sealed_at_utc':datetime.now(timezone.utc).isoformat(),'parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'parent_algorithm':'e78cc04cd1319ed8a7cd28c1441b261a04715cca','eligibility':'Non-void, domain-DTO-bearing create/update business service methods in the nine deployed original JARs, with a known public HTTP route. Exclude health/welcome, void mutations, scalar acknowledgements, thin controller wrappers and helper methods without their own endpoint. Catalogue selected by API/response review, before any planner attempt.','selection':'Include all declared instance fields of all five eligible methods, no acceptance-based replacement. Lists are wildcard families, not one candidate per index.','candidate_counts':{'sockshop':0,'trainticket':21},'sockshop_shortfall':'All remaining Cart methods return void; Orders has no unused domain response controller; remaining Shipping GETs are fixed strings. No new application/method is invented.','entry_count':5,'models_sha256':models,'original_jars_sha256':jars,'queries':candidates,'first_run_rules':{'planner_invocations_at_seal':0,'business_requests_at_seal':0,'unseal':'Only after the execution-closure implementation/support declaration is frozen. Rejections/unknown/analysis_limited/evidence_invalid/N/A are retained; no test-based core change overwrites first results.','input_shapes':'Six cases per accepted family: create missing, duplicate/existing, update existing/missing, repeated/equal field values and boundary empty/zero cases as applicable; actual valid HTTP shapes and independent original-code truth rules fixed before first run.','independent_truth':'Original bytecode plus actual input/DB/RPC/object/call facts; never TF graph propagation or baseline labels. Nullable/empty output is counted by actual JSON presence, not expected success.','novelty_limit':'Author-selected new entries in familiar classes, not third-party blind applications. Previously used 62+29 queries are regression only.'}}
    save(out/'protocol.json',result);save(HERE/'execution-closure-heldout-20261023.json',result)
    save(out/'seal.json',{'protocol_sha256':sha(out/'protocol.json'),'planner_invocations':0,'business_requests':0,'core_changed':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);seal(p.parse_args().out.resolve())
