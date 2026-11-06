"""Count actual observer work on identical JVM fixtures; not a business speed claim."""
import argparse,json,subprocess
from pathlib import Path
from run_planned_service import ROOT,load,save
from run_query_planner import JARS

def run(home):
 out=home/'snapshot-work-controls-02';out.mkdir(exist_ok=False);old=ROOT/'artifacts/ruoyi-tolist-20261105/final-candidate/historical/frozen-base/distributed-observer.jar';new=home/'build-online-02/distributed-observer.jar';probe=home/'snapshot-probe/snapshot-probe.jar';reports=[]
 fixtures={'dto':ROOT/'artifacts/ruoyi-tolist-20261105/controls-final-02','scalar':ROOT/'artifacts/ruoyi-tolist-20261105/scalar-final-5f0c647'}
 for kind,fixture in fixtures.items():
  name='JsonListCopyFixture'if kind=='dto'else'JsonListScalarFixture'
  for mode in('full','selective'):
   outputs=[]
   for version,agent in(('old',old),('new',new)):
    d=out/(kind+'-'+mode+'-'+version);d.mkdir();cp=':'.join(map(str,[fixture/'classes',agent,*JARS,*sorted((fixture/'deps').glob('*.jar'))]))
    cmd=['/usr/lib/jvm/java-8-openjdk-amd64/bin/java','-javaagent:'+str(probe)+'='+str(d/'work.json'),'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(fixture/'plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(d/'events.jsonl'),'-cp',cp,name]
    save(d/'command.json',cmd);r=subprocess.run(cmd,capture_output=True,text=True);(d/'stdout.log').write_text(r.stdout);(d/'stderr.log').write_text(r.stderr);assert r.returncode==0,r.stderr
    business=json.loads(r.stdout.splitlines()[-1]);business=[{k:v for k,v in row.items()if k!='message'}for row in business];outputs.append(business);reports.append({'fixture':kind,'mode':mode,'version':version,'counts':load(d/'work.json'),'business':business})
   assert outputs[0]==outputs[1]
 save(out/'results.json',{'records':reports,'business_equal':True,'scope':'Actual JVM observer diagnostics with identical additional probe; not production timing or application capability.'});print(reports)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);run(p.parse_args().home.resolve())
