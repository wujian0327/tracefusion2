"""Same complete captures, frozen/new lookup: graph and selection equivalence.

No profiler, timing, business deployment or independent-truth generation.
"""
import argparse,importlib,importlib.util,json,subprocess,sys
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from infer_distributed_fields import Reconstruction


def audit(home,out):
    out.mkdir(parents=True,exist_ok=False);reference=out/'infer_application_execution_c16.py'
    reference.write_bytes(subprocess.check_output(['git','show','c16ed34:experiments/sockshop-mirrortaint/infer_application_execution.py']))
    spec=importlib.util.spec_from_file_location('infer_application_execution_reference',reference);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    current=importlib.import_module('infer_application_execution');reports=[]
    try:
        for group in('C1','C2'):
            location=home/('final-'+group);facts=home/('facts-final-'+group)
            for q in load(location/'task-seal.json')['tasks']['ruoyi']:
                for mode in('full','selective'):
                    view=facts/(q['id']+'-'+mode);snapshots=[]
                    for name,module in(('reference',old),('current',current)):
                        sys.modules['infer_application_execution']=module
                        try:
                            graph=Reconstruction(view/'build',view/'capture',['role'])
                            result={'nodes':sorted([[repr(k),v]for k,v in graph.nodes.items()]),'edges':sorted([[repr(k),[repr(v)for v in vs]]for k,vs in graph.edges.items()])}
                        except ValueError as error:result={'rejected':type(error).__name__,'reason':str(error)}
                        save(out/(group+'-'+q['id']+'-'+mode+'-'+name+'.json'),result);snapshots.append(result)
                    assert snapshots[0]==snapshots[1],(group,q['id'],mode)
                    reports.append({'group':group,'query':q['id'],'mode':mode,'equal':True,'capture_sha256':sha(location/'runs'/q['id']/mode/'capture/events.jsonl'),'rejection':snapshots[0].get('reason')})
    finally:sys.modules['infer_application_execution']=current
    save(out/'summary.json',{'complete_captures':len(reports),'all_graph_nodes_edges_status_origins_selectors_equal':True,'runs':reports,'reference_sha256':sha(reference),'current_sha256':sha(HERE/'infer_application_execution.py'),'new_online_deployments':0,'performance_measured':False});print('Complete graph/selection equivalence:',len(reports))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.home.resolve(),a.out.resolve())
