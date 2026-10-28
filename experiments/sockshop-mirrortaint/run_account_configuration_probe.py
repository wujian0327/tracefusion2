#!/usr/bin/env python3
"""Separate diagnostic capture. No provenance score or FIRST overwrite."""
import argparse,subprocess
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import JARS
import portability_tool_config as config
from run_monitor_revision_recipient import run

def main(root,build):
 root.mkdir(parents=True);classes=root/'probe-classes';classes.mkdir();source=HERE/'LibraryConfigurationProbe.java';subprocess.run(['javac','-cp',str(build/'distributed-observer.jar'),'-d',str(classes),str(source)],check=True);(root/'manifest.txt').write_text('Premain-Class: LibraryConfigurationProbe\n\n');jar=root/'probe.jar';subprocess.run(['jar','cfm',str(jar),str(root/'manifest.txt'),'-C',str(classes),'.'],check=True)
 original=config.configure
 def configure(r,out,cfg,q,mode,index):
  original(r,out,cfg,q,mode,index);cfg['volumes']+=[str(jar)+':/tf2/configuration-probe.jar:ro'];pos=cfg['command'].index('-jar');cfg['command'][pos:pos]=['-javaagent:/tf2/configuration-probe.jar='+q['entry'],'-Dlibrary.probe.output=/tf2/capture/library-configuration.log'];save(out/'configuration-probe-receipt.json',{'diagnostic_only':True,'not_acceptance_capture':True,'source_sha256':sha(source),'jar_sha256':sha(jar),'business_JAR_unmodified':True})
 config.configure=configure;run(root,build,'full',11,'piggymetrics-2')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();main(a.root.resolve(),a.build.resolve())
