"""Real-JVM state/queue controls, separate from provenance replay captures."""
import argparse,json
from pathlib import Path
from run_planned_service import ROOT,HERE,save,load,sha
from run_query_planner import command,JARS
from identity_lifecycle_protocol import validate


def run(out,agent,before=False):
    out.mkdir(parents=True,exist_ok=False);save(out/'protocol-before-jvm.json',{'fixture_sha256':sha(HERE/'LifecycleStateFixture.java'),'Agent_sha256':sha(agent),'scope':'Component state controls; explicit Collector API calls, no fabricated provenance roots or answers. Terminal GC witnesses use PhantomReference queues, bounded 80 retries; cumulative120000 and 4000 concurrent separate from event limit.','before':before})
    java=ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64/bin/java';classes=out/'classes';classes.mkdir();deps=sorted((ROOT/'artifacts/ruoyi-request-scope-20261104/scope-controls-02/deps').glob('*.jar'));cp=':'.join(map(str,[classes,agent,*JARS,*deps]))
    command([str(java.with_name('javac')),'-cp',cp,'-d',str(classes),str(HERE/'LifecycleStateFixture.java'),*([]if before else[str(HERE/'LifecycleMapFixture.java')])],out/'compile.log')
    plan={'profile':'execution-dependency','entry':'LifecycleDiagnostic.unused()V','class_sha256':{},'frame_methods':[],'snapshot_fields':[],'mapper_fields':[],'full_snapshot_fields':[],'selected_read_sites':[],'json_schema':{},'reduction':{},'execution_kernel':{'version':8,'methods':{}},'async_protocol':{'version':1,'observation_only':True,'class_sha256':{}}};save(out/'plan.json',plan)
    cmd=[str(java),'-Xms64m','-Xmx256m','-javaagent:'+str(agent),'-Dservice.mode=full','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(out/'events.jsonl'),'-cp',cp,'LifecycleStateFixture',*(['before']if before else[])];save(out/'command.json',cmd)
    if not before:
        unit=cmd[:-1]+['LifecycleMapFixture'];unit[unit.index('-Dservice.events='+str(out/'events.jsonl'))]='-Dservice.events='+str(out/'map-events.jsonl');save(out/'map-command.json',unit);save(out/'map-results.json',json.loads(command(unit,out/'map-stdout.log').stdout.splitlines()[-1]))
    reports=json.loads(command(cmd,out/'stdout.log').stdout.splitlines()[-1]);rows=[json.loads(l)for l in(out/'events.jsonl').read_text().splitlines()];validate(rows);save(out/'results.json',{'gate':True,'before':before,'checks':reports,'events':len(rows),'metrics':rows[-1]})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);p.add_argument('--before',action='store_true');a=p.parse_args();run(a.out.resolve(),a.agent.resolve(),a.before)
