#!/usr/bin/env python3
"""A user mapper override must not run while its loader metadata is recorded."""
import argparse,json
from pathlib import Path
from run_planned_service import HERE,save,sha
from run_query_planner import command,JARS
from experiment_environment import java8_target


def run(out,build):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();agent=build/'distributed-observer.jar';cp=':'.join(map(str,[agent,*JARS]))
    command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),str(HERE/'JacksonObserverPurityFixture.java')],out/'compile.log')
    command(['java','-javaagent:'+str(agent),'-Dservice.plan='+str(build/'fixture/plan.json'),'-Dservice.events='+str(out/'events.jsonl'),'-cp',str(classes)+':'+cp,'JacksonObserverPurityFixture'],out/'stdout.json')
    result=json.loads((out/'stdout.json').read_text().splitlines()[-1]);assert result['all_passed'] and result['user_override_calls']==0;result['agent_sha256']=sha(agent);result['driver_sha256']=sha(Path(__file__));save(out/'results.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.out.resolve(),a.build.resolve()),indent=2))
