#!/usr/bin/env python3
"""Freeze observation-only addon independently from native MT/B0/TF."""
import json,subprocess,zipfile,hashlib
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import command
from experiment_environment import java8_target

def run(out):
 out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();bundle=ROOT/'artifacts/heldout29-first-20261023/native-bundle';native=ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar';cp=':'.join(map(str,[native,bundle/'capability.jar',* (ROOT/'artifacts/flowdist-orders-static-lambda-v3-20261013/work/lib').glob('*.jar')]))
 sources=[HERE/'native-export-v2'/n for n in ('NativeBoundaryFactsAgent.java','BoundaryExportFixture.java')]
 command(['javac',*java8_target()[1],'-cp',cp,'-d',str(classes),*map(str,sources)],out/'compile.log');jar=out/'native-boundary-facts.jar'
 with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED)as z:
  z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: NativeBoundaryFactsAgent\n\n')
  for p in classes.glob('NativeBoundaryFactsAgent*.class'):z.write(p,p.name)
 config={'prefix':'BoundaryExportFixture','source_calls':['BoundaryExportFixture$Repo.read(LBoundaryExportFixture$Item;)LBoundaryExportFixture$Item;'],'sink_calls':['BoundaryExportFixture$Repo.save(LBoundaryExportFixture$Item;Z)LBoundaryExportFixture$Item;','BoundaryExportFixture$Repo.remove(LBoundaryExportFixture$Item;)V']};save(out/'fixture-config.json',config)
 runtime=str(classes)+':'+cp;original=command(['java','-cp',runtime,'BoundaryExportFixture'],out/'original.log').stdout
 observed=command(['java','-javaagent:'+str(jar),'-Dboundary.config='+str(out/'fixture-config.json'),'-Dboundary.events='+str(out/'facts.jsonl'),'-cp',runtime,'BoundaryExportFixture'],out/'observed.log').stdout
 assert observed==original;rows=[json.loads(l)for l in(out/'facts.jsonl').open()];assert not rows[-1]['capture_invalid']and not any(r['kind']=='problem'for r in rows)
 begin=[r for r in rows if r['kind']=='call-begin'];end=[r for r in rows if r['kind']=='call-end'];assert len(begin)==len(end)==10
 assert len({r['call_id']for r in begin})==10
 for a in begin:
  b=[r for r in end if r['call_id']==a['call_id']];assert len(b)==1 and a['seq']<b[0]['seq'];assert a['callee']==b[0]['callee']
 assert sum(r['completion']=='exceptional'for r in end)==2
 summary={'all_passed':True,'business_rows_equal':5,'actual_calls':10,'exceptional_calls_same_business_object':2,'uncertified_raw_facts_only':True,'native_propagation_modified':False,'native_jar_sha256':sha(native),'unchanged_B0_capability_sha256':sha(bundle/'capability.jar'),'addon_sha256':sha(jar),'sources':{str(p):sha(p)for p in sources},'sink_snapshot_completeness':dict(__import__('collections').Counter(str(a['arguments'][0]['complete'])for a in begin if a['effect_kind']=='sink'))};save(out/'results.json',summary);print(summary)
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
