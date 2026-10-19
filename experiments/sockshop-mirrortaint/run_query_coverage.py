#!/usr/bin/env python3
"""First-pass held-out query experiment, without changes to frozen TF inference.

Pool construction uses javap declarations and reviewed endpoint contracts, never
planner acceptance. Plan attempts run only after the pool's git seal is saved.
"""
import argparse
from collections import defaultdict, deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / 'artifacts/query-coverage-first-20261019'


def load(p): return json.loads(p.read_text())
def save(p, value): p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def declarations(out, role):
    text = (out / 'inventory' / role / 'declarations.txt').read_text()
    classes = {}
    for block in text.split('Compiled from '):
        match = re.search(r'public class (\S+)', block)
        if not match: continue
        owner = match[1]
        fields = []
        for line in block.splitlines():
            if '(' in line or not re.match(r'  (?:private|public|protected) ', line) or not line.endswith(';'): continue
            body = line.strip().removesuffix(';')
            if ' static ' in ' ' + body + ' ': continue
            type_, name = body.split(' ', 1)[1].rsplit(' ', 1)
            getter = 'get' + name[0].upper() + name[1:]
            is_getter = 'is' + name[0].upper() + name[1:]
            if not (line.startswith('  public ') or re.search(r'\b(?:' + getter + '|' + is_getter + r')\(\)', block)): continue
            fields.append((name, type_))
        methods = []
        lines = block.splitlines()
        for i, line in enumerate(lines[:-1]):
            if line.startswith('  public ') and '(' in line and 'descriptor:' in lines[i+1]:
                name = line.split('(')[0].rsplit(' ', 1)[-1]
                methods.append((name, owner.replace('.', '/') + '.' + name + lines[i+1].split('descriptor:')[1].strip()))
        classes[owner] = {'fields': fields, 'methods': methods}
    return classes


def endpoints():
    # Reviewed original controller/service response contracts; no planner result.
    return [
        ('orders','works.weave.socks.orders.controllers.OrdersController','newOrder','POST /orders','works.weave.socks.orders.entities.CustomerOrder',''),
        ('carts','works.weave.socks.cart.controllers.CartsController','get','GET /carts/{customerId}','works.weave.socks.cart.entities.Cart',''),
        ('carts','works.weave.socks.cart.controllers.ItemsController','get','GET /carts/{customerId}/items/{itemId}','works.weave.socks.cart.entities.Item',''),
        ('carts','works.weave.socks.cart.controllers.ItemsController','getItems','GET /carts/{customerId}/items','java.util.List<works.weave.socks.cart.entities.Item>',''),
        ('carts','works.weave.socks.cart.controllers.ItemsController','addToCart','POST /carts/{customerId}/items','works.weave.socks.cart.entities.Item',''),
        ('shipping','works.weave.socks.shipping.controllers.ShippingController','postShipping','POST /shipping','works.weave.socks.shipping.entities.Shipment',''),
        ('station','fdse.microservice.service.StationServiceImpl','query','GET /api/v1/stationservice/stations','java.util.List<fdse.microservice.entity.Station>','/data'),
        ('station','fdse.microservice.service.StationServiceImpl','queryById','GET /api/v1/stationservice/stations/name/{id}','java.lang.String','/data'),
        ('station','fdse.microservice.service.StationServiceImpl','queryForIdBatch','POST /api/v1/stationservice/stations/idlist','java.util.List<java.lang.String>','/data'),
        ('station','fdse.microservice.service.StationServiceImpl','queryByIdBatch','POST /api/v1/stationservice/stations/namelist','java.util.List<java.lang.String>','/data'),
        ('basic','fdse.microservice.service.BasicServiceImpl','queryForTravel','POST /api/v1/basicservice/basic/travel','fdse.microservice.entity.TravelResult','/data'),
        ('ticketinfo','ticketinfo.service.TicketInfoServiceImpl','queryForTravel','POST /api/v1/ticketinfoservice/ticketinfo','ticketinfo.entity.TravelResult','/data'),
        ('train','train.service.TrainServiceImpl','retrieve','GET /api/v1/trainservice/trains/{id}','train.entity.TrainType','/data'),
        ('train','train.service.TrainServiceImpl','query','GET /api/v1/trainservice/trains','java.util.List<train.entity.TrainType>','/data'),
        ('route','route.service.RouteServiceImpl','getRouteById','GET /api/v1/routeservice/routes/{id}','route.entity.Route','/data'),
        ('route','route.service.RouteServiceImpl','getRouteByStartAndTerminal','GET /api/v1/routeservice/routes/{start}/{terminal}','java.util.List<route.entity.Route>','/data'),
        ('route','route.service.RouteServiceImpl','getAllRoutes','GET /api/v1/routeservice/routes','java.util.List<route.entity.Route>','/data'),
        ('price','price.service.PriceServiceImpl','findByRouteIdAndTrainType','GET /api/v1/priceservice/prices/{route}/{train}','price.entity.PriceConfig','/data'),
        ('price','price.service.PriceServiceImpl','findAllPriceConfig','GET /api/v1/priceservice/prices','java.util.List<price.entity.PriceConfig>','/data'),
    ]


def pool(out):
    assert not (out / 'pool.json').exists(), 'Pool is immutable; use a fresh experiment'
    classes = {r: declarations(out, r) for r in load(out/'freeze.json')['jars']}
    prior = set()
    history = []
    for app, role in [('sockshop','orders'),('trainticket','ticketinfo')]:
        f = ROOT/'artifacts/distributed-paths-final-20261015'/app/'field-results.json'
        d = load(f); history.append({'file': str(f.relative_to(ROOT)), 'sha256': sha(f)})
        for q in d['queries']:
            p = re.sub(r'/\d+(?=/|$)', '/*', q['path'])
            prior.add((role, 'newOrder' if role == 'orders' else 'queryForStationId', p))
    prior.update({('shipping','postShipping','/id'),('shipping','postShipping','/name'),
                  ('station','queryForId','/data'),('basic','queryForStationId','/data'),
                  ('basic','queryForTravel','/data/prices/economyClass'),('basic','queryForTravel','/data/prices/confortClass')})
    # Explicit earlier background-debug target; not promoted to a new query.
    background = {('orders','newOrder','/items/*/id')}
    candidates = []; exclusions = []
    def leaves(role, type_, path, parent=None, depth=0):
        assert depth < 8
        if type_.startswith('java.util.List<') or type_.startswith('java.util.Collection<'):
            yield from leaves(role, type_[type_.index('<')+1:-1], path+'/*', parent, depth+1); return
        if type_.startswith('java.util.Map<'):
            for key in ('economyClass','confortClass'):
                yield path+'/'+key, parent, 'declared Map price key from original bytecode'
            return
        if type_ not in classes[role]:
            yield path, parent or 'edu.fudan.common.util.Response.data', 'scalar or built-in leaf'; return
        for name, child in classes[role][type_]['fields']:
            yield from leaves(role, child, path+'/'+name, type_+'.'+name, depth+1)
    for role, owner, method, http, type_, prefix in endpoints():
        entry = [key for name,key in classes[role][owner]['methods'] if name == method]
        assert len(entry) == 1, (role, method)
        for path, target, note in leaves(role,type_,prefix):
            app = 'sockshop' if role in ('orders','carts','shipping') else 'trainticket'
            item = {'application': app, 'role': role, 'entry': entry[0], 'http': http,
                    'target': target, 'path': path, 'shape_note': note,
                    'source_boundary': {'scope': 'entry arguments, concrete entity field/element reads after repository return, and actual downstream RPC response reads; database histories excluded',
                                        'selection_origins': 'separate; not counted as data origins'},
                    'manual_configuration': {'entry':1,'target_field_or_map_path':1,'source_boundary':1,
                                             'profile_attempts':'same two frozen attempts for every query','new_library_summaries':0,'core_changes':0}}
            identity = (role, method, path)
            if identity in prior or identity in background or (role=='carts' and path.endswith('/id')):
                exclusions.append({**item, 'reason':'previously evaluated or explicitly debugged target'}); continue
            item['id'] = app+'-'+role+'-'+method+'-'+path.strip('/').replace('/','-').replace('*','each')
            item['rank'] = hashlib.sha256(('query-coverage-20261019\n'+item['id']).encode()).hexdigest()
            candidates.append(item)
    assert len({(q['role'],q['entry'],q['path']) for q in candidates}) == len(candidates)
    selected = []
    for app in ('sockshop','trainticket'):
        buckets = defaultdict(list)
        for q in candidates:
            if q['application'] == app: buckets[q['role']].append(q)
        buckets = {r:deque(sorted(qs,key=lambda q:q['rank'])) for r,qs in sorted(buckets.items())}
        chosen = []
        while len(chosen)<10 and any(buckets.values()):
            for bucket in buckets.values():
                if bucket and len(chosen)<10:chosen.append(bucket.popleft())
        selected.extend(q['id'] for q in chosen)
    protocol = {'algorithm_commit':load(out/'freeze.json')['algorithm_commit'],
        'eligibility':'Reviewed public domain-response endpoints of the nine historically deployed original Java services. Exclude health/welcome, transport status/msg, authenticated admin mutations, void responses and previously evaluated/debugged entry+target paths. Lists use one wildcard query family, not a new query per index. Nested DTO fields are leaves; built-in Date/UUID are single fields.',
        'inventory_boundary':'Bounded reviewed endpoint catalogue, not all APIs or all applications. TicketInfo travel response shape is inherited from the original Basic RPC; actual generic deserialization may reject evidence.',
        'selection':'Sort service names; round-robin services; within each service SHA256(query-coverage-20261019\\n+id); stop at10 per application. No replacements after planning.',
        'novelty':'New declared/evaluated entry+target query relative to retained development evidence, not proof authors never inspected its class or used the field as an input. No numeric-only variants. Not third-party blind selection.',
        'planning':load(out/'freeze.json')['planning_policy'],'history_sources':history,
        'excluded_known_targets':exclusions,'candidates':candidates,'selected_ids':selected,
        'created_at_utc':datetime.now(timezone.utc).isoformat()}
    save(out/'pool.json',protocol)
    save(out/'logs/01-pool-sealed-before-planning.json',{'pool_sha256':sha(out/'pool.json'),'selected':selected,
        'candidate_counts':{app:sum(q['application']==app for q in candidates) for app in ('sockshop','trainticket')},
        'planner_invocations':0})
    print(json.dumps({'candidates':len(candidates),'selected':selected},indent=2))


def check_freeze(out):
    frozen = load(out/'freeze.json')
    assert sha(out/'frozen-code.tar') == frozen['source_archive_sha256']
    for name, expected in frozen['sources'].items():
        assert sha(out/'code'/name) == expected, name
    for name, expected in frozen['dependencies'].items():
        assert sha(ROOT/name) == expected, name
    for value in frozen['jars'].values():
        assert sha(ROOT/value['frozen']) == value['sha256']
    seal = load(out/'logs/01-pool-sealed-before-planning.json')
    assert sha(out/'pool.json') == seal['pool_sha256']
    return frozen


def plan(out):
    frozen = check_freeze(out); pool_ = load(out/'pool.json')
    assert not (out/'planning.json').exists(), 'First-pass results are immutable'
    preregistered = subprocess.check_output(['git','show','dfd929c:experiments/sockshop-mirrortaint/query-coverage-pool-20261019.json'],cwd=ROOT)
    assert hashlib.sha256(preregistered).hexdigest() == sha(out/'pool.json')
    stage = out/'planning'; stage.mkdir()
    # Frozen module ROOT resolves artifacts here; its source files stay untouched.
    artifact_link=out/'code/artifacts'
    if artifact_link.is_symlink():
        assert artifact_link.resolve()==(ROOT/'artifacts').resolve()
    else:
        assert not artifact_link.exists()
        artifact_link.symlink_to(ROOT/'artifacts',target_is_directory=True)
    inputs = {}
    for role, jar in frozen['jars'].items():
        targets = sorted({q['target'] for q in pool_['candidates'] if q['role']==role})
        if role not in ('orders','carts','shipping'):
            targets += ['edu.fudan.common.util.Response.data']
        if role == 'basic': targets += ['edu.fudan.common.util.JsonUtils.LOGGER']
        inputs[role] = {'jar':str(ROOT/jar['frozen']), 'targets':sorted(set(targets))}
    save(stage/'boundary-inputs.json',inputs)
    for command, filename in [(['java','-version'],'java-version.txt'),(['javac','-version'],'javac-version.txt')]:
        r=subprocess.run(command,capture_output=True,text=True);(stage/filename).write_text(r.stdout+r.stderr)
    cmd=[sys.executable,str(out/'code/experiments/sockshop-mirrortaint/build_distributed_plans.py'),
         '--out',str(stage/'build'),'--inputs',str(stage/'boundary-inputs.json')]
    save(stage/'build-command.json',cmd)
    with (stage/'build-console.log').open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    sys.path.insert(0,str(out/'code/experiments/sockshop-mirrortaint'))
    from plan_service_observations import plan_service
    from plan_distributed_fields import copy_plan,augment
    from plan_collection_service import plan_collection
    results=[]
    for query_id in pool_['selected_ids']:
        query=next(q for q in pool_['candidates'] if q['id']==query_id)
        dest=stage/query_id;dest.mkdir();model=load(stage/'build'/query['role']/'model.json')
        result={'id':query_id,'application':query['application'],'query':query,'attempts':[],
                'status':'planning-rejected','chosen_plan':None}
        for mode,functions in [('native-default',[plan_service,copy_plan]),('explicit-collection',[plan_collection])]:
            accepted=False
            for function in functions:
                started=time.perf_counter()
                record={'configuration':mode,'function':function.__name__}
                try:
                    local=function(model,query['entry'],query['target']);p=augment(model,local)
                    if mode=='explicit-collection':p['collection_elements']=True
                    if query['role']=='basic':
                        p['json_conversion_methods']=['edu/fudan/common/util/JsonUtils.conveterObject(Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;']
                        p['json_conversion_contract']='Existing frozen default Jackson object-to-JSON-to-object relative pointer contract'
                    filename=mode+'.plan.json';save(dest/filename,p)
                    record.update(status='accepted',profile=p['profile'],plan_sha256=sha(dest/filename))
                    if result['chosen_plan'] is None:
                        result['chosen_plan']=str((dest/filename).relative_to(out));result['status']='planning-accepted'
                    accepted=True
                except Exception as error:
                    record.update(status='rejected' if isinstance(error,ValueError) else 'experiment-error',
                                  error_type=type(error).__name__,reason=str(error))
                    (dest/(mode+'-'+function.__name__+'.traceback.txt')).write_text(traceback.format_exc())
                record['elapsed_seconds']=time.perf_counter()-started;result['attempts'].append(record)
                if accepted:break
        save(dest/'result.json',result);results.append(result)
        print(query_id,result['status'],[(x['function'],x.get('reason',x.get('profile'))) for x in result['attempts']],flush=True)
    check_freeze(out)
    save(out/'planning.json',{'algorithm_commit':frozen['algorithm_commit'],'pool_commit':'dfd929c',
                            'pool_sha256':sha(out/'pool.json'),'results':results,'frozen_source_check':'passed'})
    save(out/'logs/02-first-planning-completed.json',{'queries':len(results),
        'accepted':sum(r['status']=='planning-accepted' for r in results),'all_attempts_preserved':True,
        'planning_sha256':sha(out/'planning.json'),'recorded_at_utc':datetime.now(timezone.utc).isoformat()})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['pool','plan'])
    parser.add_argument('--out',type=Path,default=DEFAULT)
    args=parser.parse_args()
    {'pool':pool,'plan':plan}[args.stage](args.out.resolve())
