"""Wire only frozen binaries; no propagation/model/Agent changes."""
from pathlib import Path
from run_portability_first import BASE,TASK_ROOT,verify
from run_planned_service import ROOT,load,save,sha
from plan_distributed_fields import json_schema
BUNDLE=ROOT/'artifacts/heldout29-first-20261023/native-bundle'

def configure(root,out,cfg,q,mode,index=None):
    verify(root);cap=out/'capture';cap.mkdir(exist_ok=True);cap.chmod(0o777)
    volumes=cfg.setdefault('volumes',[]);options=[]
    if mode=='mirrortaint':
        schema=out/'schema.json';props,reject=json_schema(load(root/'metadata'/q['role']/'model.json'));save(schema,{'json_schema':props,'rejected_properties':reject,'scope':'Unchanged frozen adapter metadata, not independent truth or support selection'})
        sources=sorted({s['callee']for s in q['read_source_candidates']});config=out/'mt-config.json';prefix=q['entry'].split('/controller/')[0]+'/'if'/controller/'in q['entry']else q['entry'].rsplit('/',1)[0]+'/'
        if q['application']=='piggymetrics':prefix='com/piggymetrics/'
        save(config,{'entry':q['entry'],'prefix':prefix,'source_calls':sources})
        native=ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar';mounts={native:'/tf2/mirrorTaint.jar',BUNDLE/'adapter/integration-adapter.jar':'/tf2/adapter.jar',BUNDLE/'capability.jar':'/tf2/capability.jar',BUNDLE/'runtime-witness.jar':'/tf2/runtime-witness.jar',schema:'/tf2/schema.json',config:'/tf2/mt-config.json'}
        options=['-javaagent:/tf2/runtime-witness.jar','-Dnative.library.events=/tf2/capture/native-library.jsonl','-Dtaint.env=remote','-Dtaint.app='+prefix.rstrip('/').replace('/','.'),'-Dtaint.version=capability','-Duser.home=/tf2/capture']
        options+=['-javaagent:/tf2/adapter.jar='+s for s in('strings','streams')]+['-javaagent:/tf2/mirrorTaint.jar']+['-javaagent:/tf2/adapter.jar='+s for s in('returns','sources','fields','threads','logging')]
        options+=['-javaagent:/tf2/capability.jar','-Dcapability.config=/tf2/mt-config.json','-Dcapability.events=/tf2/capture/native-capability.jsonl','-javaagent:/tf2/capability.jar=transport','-Dinstance.schema=/tf2/schema.json','-Dinstance.events=/tf2/capture/instances.jsonl']
    else:
        plan=root/'planning-first'/q['id']/('%03d-plan.json'%index);assert plan.exists();mounts={BASE/'distributed-observer.jar':'/tf2/observer.jar',plan:'/tf2/plan.json'}
        options=['-javaagent:/tf2/observer.jar','-Dservice.plan=/tf2/plan.json','-Dservice.events=/tf2/capture/events.jsonl','-Dservice.mode='+mode]
    volumes+=[str(p)+':'+name+':ro'for p,name in mounts.items()]+[str(cap)+':/tf2/capture:rw'];cmd=cfg['command'];position=cmd.index('-jar');cfg['command']=cmd[:position]+options+cmd[position:]
    save(out/'tool-binaries.json',{'mode':mode,'fixed_core':load(root/'protocol-start.json')['TF_commit'],'files':{str(p):sha(p)for p in mounts},'no_core_agent_or_contract_changes':True,'native_propagation_changed':False,'fixed_adapter_limit':'Return/root/source exporter is unchanged; arbitrary void DB/message sinks and primitive roots may not have instance output.'})
