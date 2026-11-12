"""Pinned installed bytecode plus pinned upstream sources; no native license."""
import argparse,json,zipfile,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,save,load,sha
from run_query_planner import JARS,command
from run_generic_observation_rules import FROZEN
from constructor_effect_scope_audit import summarize


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    base=ROOT/'artifacts/galette-static-baselines-20261111/runtime-base/java-8-openjdk-amd64'
    classes=out/'classes';classes.mkdir();rt=base/'jre/lib/rt.jar';owners=['java/lang/'+x for x in ('Object','Throwable','Exception','RuntimeException','IllegalArgumentException')]
    with zipfile.ZipFile(rt)as z:
        for owner in owners:
            p=classes/(owner+'.class');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(owner+'.class'))
    tool=FROZEN/'frozen-base/tools';cmd=['/usr/lib/jvm/java-8-openjdk-amd64/bin/java','-cp',':'.join(map(str,[tool,*JARS])),'QueryBytecodeModel',str(classes),str(out/'model.json')]
    save(out/'model-command.json',cmd);command(cmd,out/'model.log')
    model=load(out/'model.json');reviews=[]
    for owner in owners:
        name=owner.replace('/','.')
        command([str(base/'bin/javap'),'-p','-c',name],out/(name+'.javap'))
    for key in ('java/lang/IllegalArgumentException.<init>(Ljava/lang/String;)V','java/lang/RuntimeException.<init>(Ljava/lang/String;)V','java/lang/Exception.<init>(Ljava/lang/String;)V','java/lang/Throwable.<init>(Ljava/lang/String;)V'):
        reviews.append(summarize(model,key))
    save(out/'reviews.json',reviews)
    flags=command([str(base/'bin/java'),'-XX:+PrintFlagsFinal','-version'],out/'VM-flags.log')
    save(out/'receipt.json',{'java':sha(base/'bin/java'),'rt_jar':sha(rt),'libjvm':sha(base/'jre/lib/amd64/server/libjvm.so'),'libjava':sha(base/'jre/lib/amd64/libjava.so'),'class_sha256':{n:sha(classes/(n+'.class'))for n in owners},'metadata_JDK':'host8u512; original bytecode from restored8u504','native_contract_activated':False,'runtime_flags_are_independent_probe_not_old_request_evidence':True,'reviews_have_runtime_license':any(r['runtime_license']for r in reviews)})
    print(json.dumps({'class_count':len(owners),'IAE_static_candidate':reviews[0]['static_local_candidate'],'runtime_license':False,'unclosed_calls':reviews[0]['unclosed']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
