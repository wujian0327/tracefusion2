"""Run the two presealed repository REST entries without adapting the kernel."""
import argparse,json,subprocess,time,csv
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from run_generic_observation_rules import AGENT
import run_jvm_rule_revision as revision

H=revision.H

def run():
    revision.verify();protocol=load(H/'new-app-protocol-before-planning.json');results=[]
    image='maven:3.8.6-eclipse-temurin-8';container_prefix='tf2-jvm-rule-reuse-'
    for query in protocol['queries']:
      for mode in ('full','selective'):
        out=H/'new-app-first-runs'/(query['id']+'-'+mode);out.mkdir(parents=True,exist_ok=False)
        cap=out/'capture';cap.mkdir();cap.chmod(0o777);name=container_prefix+query['id']+'-'+mode
        plan=H/'new-app-first-planning'/(query['id']+'-plan.json')
        cmd=['docker','run','-d','--name',name,'--network','tf2-jvm-rule-guide','-v',protocol['jar']+':/app.jar:ro','-v','/usr/lib/jvm/java-8-openjdk-amd64:/approved-jdk:ro','-v','/etc/java-8-openjdk:/etc/java-8-openjdk:ro','-v',str(AGENT)+':/agent.jar:ro','-v',str(plan)+':/plan.json:ro','-v',str(cap)+':/capture:rw',image,'/approved-jdk/bin/java','-Xms64m','-Xmx384m','-javaagent:/agent.jar','-Dservice.plan=/plan.json','-Dservice.events=/capture/events.jsonl','-Dservice.mode='+mode,'-jar','/app.jar']
        save(out/'command.json',cmd);requests=[]
        try:
          subprocess.run(cmd,check=True,capture_output=True,text=True)
          for _ in range(60):
            logs=subprocess.run(['docker','logs',name],text=True,capture_output=True).stdout
            if 'Started Application' in logs:break
            if 'APPLICATION FAILED' in logs:raise RuntimeError('Original application startup failed')
            time.sleep(1)
          else:raise RuntimeError('Startup timeout')
          for index,seed in enumerate(protocol['seed_before_queries']):
            r=subprocess.run(['docker','exec',name,'curl','-sS','--max-time','30','-X','POST','-H','Content-Type: application/json','-d',json.dumps(seed),'http://127.0.0.1:8080/people'],text=True,capture_output=True,check=True);(out/('seed-'+str(index)+'.json')).write_text(r.stdout)
          for index,url in enumerate(query['urls']):
            r=subprocess.run(['docker','exec',name,'curl','-sS','--max-time','30','-w','\n%{http_code}','http://127.0.0.1:8080'+url],text=True,capture_output=True,check=True);(out/('request-'+str(index)+'.http')).write_text(r.stdout);body,status=r.stdout.rsplit('\n',1);requests.append({'url':url,'status':int(status),'body':json.loads(body)})
          save(out/'requests.json',requests)
        except Exception as e:
          save(out/'failure.json',{'error':type(e).__name__+': '+str(e)})
        finally:
          subprocess.run(['docker','stop','-t','10',name],capture_output=True)
          log=subprocess.run(['docker','logs',name],text=True,capture_output=True);(out/'console.log').write_text(log.stdout+log.stderr)
          subprocess.run(['docker','rm',name],capture_output=True)
        rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()]if(cap/'events.jsonl').exists()else[]
        problems=[r for r in rows if r['kind']=='problem'];bindings=[r for r in rows if r['kind']=='binding-return'];sources=[r for r in rows if r['kind']=='binding-source']
        state='evidence_invalid'if problems or any(r.get('capture_invalid')for r in rows)else'unknown'
        results.append({'query':query['id'],'mode':mode,'requests':requests,'state':state,'first_problem':problems[0]if problems else None,'binding_returns':len(bindings),'binding_sources':len(sources),'capture_sha256':sha(cap/'events.jsonl')if rows else None,'core_changed':False,'oracle_adequate':False,'known_correct':0})
        save(H/'new-app-first-run-results.json',results)
    revision.verify()

if __name__=='__main__':run()
