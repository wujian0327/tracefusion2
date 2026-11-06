"""Reproduce scoring/core attribution from completed fresh-exec measurements."""
import argparse,csv
from pathlib import Path
from run_planned_service import load,save
from summarize_shared_work_revision import paired

def run(home,out):
 result=load(home/'indexed-oracle-paired/results.json')
 assert result['all_answers_and_independent_coordinates_equal']
 out.mkdir(parents=True,exist_ok=False);data={}
 for group in ('score-only','combined-core'):
  rows=[]
  for r in result['records']:
   if r['group']!=group:continue
   assert not r['profile'] and not r['diagnostic_graph_export'] and r['correct']==r['targets']
   row={k:r[k]for k in ('task','mode','version','repeat','targets','correct','process_wall_seconds','process_cpu_seconds','VmHWM_KiB')}
   for k,v in r['phases_seconds'].items():row[k+'_wall_seconds']=v
   for k,v in r['cpu_phases_seconds'].items():row[k+'_cpu_seconds']=v
   rows.append(row)
  assert len(rows)==40
  data[group]={'rows':rows,'paired':paired(rows,[k for k in rows[0]if k.endswith(('_seconds','KiB'))])}
  with (out/(group+'.csv')).open('w')as f:
   w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
 save(out/'oracle-summary.json',data)
 print('Validated 80 measurements; separate scoring and reconstruction comparisons')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.home,a.out)
