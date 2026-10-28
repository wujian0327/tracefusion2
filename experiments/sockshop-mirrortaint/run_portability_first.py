#!/usr/bin/env python3
"""40-entry portability ledger; ae7fe8d core and native propagation stay fixed.

Source discovery and metadata extraction are not query-planning successes.
Historical proxy versions are never presented as the unidentified paper commits.
"""
import argparse,datetime,hashlib,json,re,subprocess,shutil
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
from run_planned_service import ROOT,HERE,load,save,sha

CORE='ae7fe8d8b9e23d8ce197870ff0069c7f1bee84eb'
BASE=ROOT/'artifacts/contract-routing-revision-20261023/final-v2/frozen-base'
TASK_ROOT=ROOT/'artifacts/portability-first-20261028'
OWNERS={
 'apollo':['NamespaceController','ReleaseController','InstanceConfigController','NamespaceBranchController','InstanceController'],
 'piggymetrics':['AccountController','AccountController','UserController','UserController','RecipientController'],
 'ZLT-MP':['ClientController','SysUserController','SysUserController','SysUserController','SysUserController'],
 'SockShop':['OrdersController','CartsController','CartsController','CartsController','ShippingController'],
 'FEBS-Cloud':['OauthClientDetailsController','JobController','UserController','UserController','UserController'],
 'goodsKill':['SeckillServiceImpl','SeckillMockController','SeckillController','SeckillController','AdminController'],
 'mall-swarm':['UmsMemberController','UmsMemberController','UmsAdminController','UmsAdminController','UmsAdminController'],
 'SuperMarket':['CartController','CartController','OrderController','ProductController','UserController']}
MODULES={'apollo':['apollo-portal','apollo-portal','apollo-adminservice','apollo-portal','apollo-portal'],
 'piggymetrics':['account-service','account-service','auth-service','auth-service','notification-service'],
 'ZLT-MP':['zlt-uaa','user-center','user-center','user-center','user-center'],
 'FEBS-Cloud':['febs-auth','febs-server-job','febs-server-system','febs-server-system','febs-server-system'],
 'goodsKill':['goodskill-service','goodskill-web','goodskill-web','goodskill-web','goodskill-web'],
 'mall-swarm':['mall-portal','mall-portal','mall-admin','mall-admin','mall-admin'],
 'SuperMarket':['cart','cart','order','product','user']}
PREFIX={'apollo':'com/ctrip/framework/apollo/','piggymetrics':'com/piggymetrics/','ZLT-MP':'com/central/','SockShop':'works/weave/socks/','FEBS-Cloud':'cc/mrbird/febs/','goodsKill':'com/goodskill/','mall-swarm':'com/macro/mall/','SuperMarket':'com/supermarket/'}
ROLES={'apollo':['apollo-proxy']*5,'piggymetrics':['piggy-account','piggy-account','piggy-auth','piggy-auth','piggy-notification'],'ZLT-MP':['zlt-uaa']+['zlt-user']*4,'SockShop':['sock-orders','sock-carts','sock-carts','sock-carts','sock-shipping'],'FEBS-Cloud':['febs-auth','febs-job','febs-system','febs-system','febs-system'],'goodsKill':['goods-service']+['goods-web']*4,'mall-swarm':['mall-portal']*2+['mall-admin']*3,'SuperMarket':['cart','cart','order','product','user']}


def verify(root):
    protocol=load(root/'protocol-start.json');assert protocol['TF_commit']==CORE
    assert sha(root/'task-original.json')==protocol['task_sha256']
    for file,h in protocol['core_sources'].items():assert sha(Path(file))==h,file
    assert sha(ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar')==protocol['native_jar_sha256']
    task=load(root/'task-original.json');assert len(task['methods'])==40 and Counter(m['application']for m in task['methods'])=={a['application']:5 for a in task['applications']}
    return task


def log(root,node,details):
    save(root/'logs'/(node+'.json'),{'node':node,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**details})


def declarations(path,name):
    text=path.read_text(errors='replace');package=re.search(r'\bpackage\s+([\w.]+)\s*;',text);out=[]
    for m in re.finditer(r'\bpublic\s+[^;{}=]{0,500}?\b'+re.escape(name)+r'\s*\(',text):
        start=m.start();pos=m.end();depth=1;quoted=False;escaped=False
        while pos<len(text)and depth:
            c=text[pos]
            if c=='"'and not escaped:quoted=not quoted
            if not quoted:
                if c=='(':depth+=1
                if c==')':depth-=1
            escaped=(c=='\\'and not escaped);pos+=1
        if depth:continue
        end=text.find('{',pos);semi=text.find(';',pos)
        if end<0 or 0<=semi<end:continue
        previous=text[max(0,start-700):start];annotations=previous[previous.rfind('}')+1:]
        out.append({'owner':package.group(1)+'.'+path.stem if package else None,'method':name,'line':text[:start].count('\n')+1,'declaration':text[start:end].strip(),'annotations_context':annotations.strip(),'file_sha256':sha(path),'file':str(path),'return_type':re.sub(r'\s+',' ',text[m.start()+len('public'):text.rfind(name,m.start(),m.end())].strip())})
    return out


def discover(root):
    task=verify(root);versions={a['application']:a for a in load(root/'version-selection-before-source-inspection.json')['applications']};author=root/'upstream/mirrortaint/Instrumenter/FlowDroidConfigFiles/entrypoints.config';hints=[]
    for line in author.read_text().splitlines():
        m=re.search(r'<([^:]+):\s+(.+?)\s+(\w+)\((.*?)\)>',line)
        if m:hints.append({'owner':m[1],'return_type':m[2],'method':m[3],'parameters':m[4]})
    items=[]
    for q in task['methods']:
        app=q['application'];number=int(q['id'].rsplit('-',1)[1])-1;owner=OWNERS[app][number];module=MODULES.get(app,[None]*5)[number];home=root/'upstream'/('FEBS-archive'if app=='FEBS-Cloud'else app);candidates=[]
        if app=='SockShop':
            role={'Orders':'orders','Carts':'carts','Shipping':'shipping'}[q['paper_service']];model=load(BASE/role/'model.json')
            for key,m in model['methods'].items():
                if m['owner'].endswith('/'+owner)and m['name']==q['paper_method']:candidates.append({'owner':m['owner'].replace('/','.'),'method':m['name'],'entry':key,'descriptor':m['desc'],'basis':'Original image JAR bytecode at existing locked tag/digest','model_sha256':sha(BASE/role/'model.json'),'role':role})
        elif home.exists():
            for path in home.rglob(owner+'.java'):
                if '/src/main/java/'not in str(path)or module and module not in path.parts:continue
                candidates.extend(declarations(path,q['paper_method']))
        hint=[h for h in hints if h['owner'].endswith('.'+owner)and h['method']==q['paper_method']]
        if hint:
            exact=[c for c in candidates if c['owner']==hint[0]['owner']]
            if exact:candidates=exact
        selected=candidates[0]if len(candidates)==1 else None
        version=versions[app]
        if app=='FEBS-Cloud':version=load(root/'FEBS-archive-selection.json')
        items.append({**q,'version_evidence':version,'source_candidates':candidates,'selected_source':selected,'author_signature_hints':hint,'mapping_status':'unique_source_candidate'if selected else'entry_mapping_ambiguous'if candidates else'entry_not_found_in_locked_candidate','paper_service_spelling_preserved':True,'paper_version_reproduced':False,'target_definition_status':'pending_original_jar_and_source_sink_review','original_preflight':{'state':'not_executed'},'tools':{m:{'state':'not_executed'}for m in ('mirrortaint','full','selective')}})
    save(root/'discovery40.json',{'task_sha256':sha(root/'task-original.json'),'selection_protocol_sha256':sha(root/'version-selection-before-source-inspection.json'),'entries':items,'not_an_execution_result':True,'not_TF_planning':True})
    log(root,'02-source-discovery',{'methods':40,'mapping':dict(Counter(x['mapping_status']for x in items))})
    print([(q['id'],q['mapping_status'],len(q['source_candidates']))for q in items])


def metadata(root,app,jar,role):
    """Flatten actual app-owned class files only; no query/profile generation."""
    verify(root);out=root/'metadata'/role
    if(out/'receipt.json').exists():
        assert load(out/'receipt.json')['jar_sha256']==sha(jar);return
    out.mkdir(parents=True);classes=out/'classes';classes.mkdir();inventory={};prefix=PREFIX[app]
    def extract(z,provider,boot=False):
        for n in z.namelist():
            relative=n[len('BOOT-INF/classes/'):]if n.startswith('BOOT-INF/classes/')else n
            if not relative.startswith(prefix)or not relative.endswith('.class'):continue
            data=z.read(n)
            if relative in inventory:
                assert inventory[relative]['sha256']==hashlib.sha256(data).hexdigest(),('Ambiguous application class',relative)
                continue
            p=classes/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);inventory[relative]={'provider':provider,'sha256':sha(p)}
    with ZipFile(jar)as z:
        extract(z,'root')
        for n in z.namelist():
            if n.startswith('BOOT-INF/lib/')and n.endswith('.jar'):
                with ZipFile(BytesIO(z.read(n)))as dep:extract(dep,n)
        manifest=z.read('META-INF/MANIFEST.MF').decode(errors='replace')if'META-INF/MANIFEST.MF'in z.namelist()else''
        dependencies=[n for n in z.namelist()if n.startswith('BOOT-INF/lib/')and n.endswith('.jar')]
    from run_query_planner import JARS
    cmd=['java','-cp',str(BASE/'tools')+':'+':'.join(map(str,JARS)),'QueryBytecodeModel',str(classes),str(out/'model.json')]
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=180);(out/'metadata.log').write_text(proc.stdout+proc.stderr);assert proc.returncode==0,proc.stderr[-1500:]
    model=load(out/'model.json')
    from contract_applicability import library_inventory
    model['library_inventory']=library_inventory(jar);save(out/'model.json',model)
    save(out/'receipt.json',{'application':app,'role':role,'original_jar':str(jar),'jar_sha256':sha(jar),'manifest':manifest,'dependency_entries':dependencies,'classes':inventory,'metadata_command':cmd,'TF_planning_executed':False,'metadata_did_not_recompile_or_modify_business_classes':True})
    print({'role':role,'application_classes':len(inventory),'methods':len(model['methods']),'jar_sha256':sha(jar)})


def original_jars(root):
    task=verify(root);spec={
      'piggymetrics':{'piggy-account':'account-service','piggy-auth':'auth-service','piggy-notification':'notification-service'},
      'mall-swarm':{'mall-admin':'mall-admin','mall-portal':'mall-portal'},
      'ZLT-MP':{'zlt-user':'zlt-business/user-center','zlt-uaa':'zlt-uaa'},
      'apollo':{'apollo-proxy':'apollo-assembly'},
      'SuperMarket':{k:k for k in ('cart','order','product','user')},
      'goodsKill':{'goods-web':'goodskill-web','goods-service':'goodskill-spring-boot-provider/goodskill-service'},
      'FEBS-Cloud':{'febs-auth':'febs-auth','febs-job':'febs-server/febs-server-job','febs-system':'febs-server/febs-server-system'}}
    receipts=[];out=root/'business-jars';out.mkdir(exist_ok=True)
    for app,roles in spec.items():
        for role,module in roles.items():
            home=root/'upstream'/('FEBS-archive'if app=='FEBS-Cloud'else app)/module/'target';candidates=[]
            for p in home.glob('*.jar'):
                try:
                    with ZipFile(p)as z:
                        if any(n.startswith('BOOT-INF/lib/')for n in z.namelist()):candidates.append(p)
                except Exception:continue
            if len(candidates)!=1:
                receipts.append({'application':app,'role':role,'state':'business_jar_unavailable','candidate_paths':list(map(str,candidates))});continue
            source=candidates[0];dest=out/(role+'.jar')
            if not dest.exists():shutil.copyfile(source,dest)
            assert sha(dest)==sha(source)
            try:metadata(root,app,dest,role);receipts.append({'application':app,'role':role,'state':'original_source_build_available','jar':str(dest),'sha256':sha(dest)})
            except Exception as e:receipts.append({'application':app,'role':role,'state':'metadata_failed','jar':str(dest),'sha256':sha(dest),'error':str(e)})
    for role in ('orders','carts','shipping'):
        dest=out/('sock-'+role+'.jar');shutil.copyfile(BASE/role/'original.jar',dest);metadata(root,'SockShop',dest,'sock-'+role);receipts.append({'application':'SockShop','role':'sock-'+role,'state':'author_compose_tag_existing_locked_image','jar':str(dest),'sha256':sha(dest),'paper_source_commit_not_known':True})
    save(root/'business-jars/index.json',receipts)


def methods(root):
    """Native reflection against original dependencies; no TF admission filter."""
    verify(root);out=root/'method-metadata';out.mkdir(exist_ok=True);items=[]
    for q in load(root/'discovery40.json')['entries']:
        role=ROLES[q['application']][int(q['id'].rsplit('-',1)[1])-1];meta=root/'metadata'/role;dest=out/q['id'];dest.mkdir(exist_ok=True);record={'id':q['id'],'role':role,'application':q['application']}
        if not(meta/'receipt.json').exists()or not q['selected_source']:
            record.update(state='metadata_unavailable');items.append(record);continue
        jar=Path(load(meta/'receipt.json')['original_jar']);libs=meta/'libs';libs.mkdir(exist_ok=True)
        with ZipFile(jar)as z:
            for name in z.namelist():
                if name.startswith('BOOT-INF/lib/')and name.endswith('.jar'):(libs/Path(name).name).write_bytes(z.read(name))
        owner=q['selected_source']['owner'];cp=':'.join(map(str,[root/'probe-classes',meta/'classes']))+':'+str(libs/'*');cmd=['java','-cp',cp,'PortabilityMethodProbe',owner,q['paper_method']]
        if q['application']in ('goodsKill','SuperMarket'):cmd=['docker','run','--rm','--network','none','-v',str(root)+':'+str(root)+':ro','--entrypoint','java','maven:3.8.6-eclipse-temurin-11',*cmd[1:]]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(dest/'stdout.log').write_text(p.stdout+p.stderr);save(dest/'command.json',cmd)
        try:
            assert p.returncode==0,p.stderr[-2000:];m=json.loads(p.stdout.splitlines()[-1]);save(dest/'reflection.json',m);assert len(m['methods'])==1,'Ambiguous or absent reflected entry';entry=m['methods'][0];model=load(meta/'model.json');assert entry['entry']in model['methods'];record.update(state='signature_verified',entry=entry['entry'],reflection_sha256=sha(dest/'reflection.json'),return_type=entry['return_generic'],business_jar_sha256=sha(jar))
        except Exception as e:record.update(state='method_metadata_failed',error=str(e))
        items.append(record);save(out/'index.json',items)
    save(out/'index.json',items);log(root,'03-method-signatures',{'methods':40,'states':dict(Counter(q['state']for q in items)),'admission_or_business_execution':False})


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,default=TASK_ROOT);a.add_argument('--stage',choices=('verify','discover','jars','methods'),required=True);v=a.parse_args();r=v.root.resolve();{'verify':verify,'discover':discover,'jars':original_jars,'methods':methods}[v.stage](r)
