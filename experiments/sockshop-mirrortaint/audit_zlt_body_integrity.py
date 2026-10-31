"""Final read-only source/capture/resource audit, outside timed processes."""
import argparse,json,statistics
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from run_zlt_body_cost import verify,FINAL


def run(home,out):
    out.mkdir(parents=True,exist_ok=False);freeze=verify();driver=load(home/'formal-driver-freeze.json')
    for name,digest in driver['sources'].items():assert sha(ROOT/name)==digest,name
    plans=load(FINAL/'final-protocol-before-business.json')['plans']
    for name,digest in plans.items():assert sha(FINAL/name)==digest,name
    from run_sockshop_cost import ROLES
    records=[];files={}
    for job in load(home/'protocol-before-calibration.json')['jobs']:
        trial=home/('round-%02d-%s-%s'%(job['round'],job['task'],job['mode']));mall=job['task']=='mall'
        raw=trial/'resources.jsonl';rows=[json.loads(s)for s in raw.read_text().splitlines()]
        phase=load(trial/('measure.json'if mall else'steady.json'));start=phase['start_ns'];end=phase['end_ns']if mall else phase['scheduled_end_ns']
        actual=load(trial/'resource-summary.json')if mall else load(trial/'metrics.json')['resources'];expected={};members=list(rows[0])
        for role in members:
            selected=[r[role]for r in rows if start<=r[role]['monotonic_ns']<=end];assert len(selected)>=2
            cpu=(selected[-1]['cpu_ns']-selected[0]['cpu_ns'])/(selected[-1]['monotonic_ns']-selected[0]['monotonic_ns'])*100
            expected[role]={'samples':len(selected),'cpu_one_core_percent_mean':cpu,
                'rss_bytes_mean':statistics.mean(r['rss_bytes']for r in selected),'rss_bytes_peak':max(r['rss_bytes']for r in selected)}
            assert expected[role]==actual[role],(trial.name,role)
        business=('admin','auth','portal')if mall else ROLES
        for group,roles in [('observed_jvms',business),('deployment',members)]:
            selected=[r for r in rows if all(start<=r[m]['monotonic_ns']<=end for m in roles)];assert len(selected)>=2
            values={'cpu_one_core_percent_mean':sum(expected[m]['cpu_one_core_percent_mean']for m in roles),
                'rss_bytes_mean':statistics.mean(sum(r[m]['rss_bytes']for m in roles)for r in selected),
                'rss_bytes_peak':max(sum(r[m]['rss_bytes']for m in roles)for r in selected)}
            assert values==actual[group],(trial.name,group)
        if mall:assert load(trial/'result.json')['cleanup_returncode']==0
        else:assert load(trial/'cleanup.json')['returncode']==0
        files[str(raw.relative_to(home))]=sha(raw)
        for role in ([]if mall else['orders','carts']):
            for p in(trial/'sockshop'/role).rglob('*'):
                if p.is_file():files[str(p.relative_to(home))]=sha(p)
        if mall:
            for p in(trial/'capture').rglob('*'):
                if p.is_file():files[str(p.relative_to(home))]=sha(p)
        records.append({**job,'resources_strictly_equal':True,'original_role_order_retained':True})
    save(out/'capture-manifest.json',{'files':files})
    save(out/'summary.json',{'all_passed':True,'core_sources':len(freeze['sources']),'formal_drivers_unchanged':True,
        'frozen_plans':len(plans),'resource_summaries_strict_equal':len(records),'no_tolerance_or_raw_value_change':True,
        'capture_files':len(files),'capture_manifest_sha256':sha(out/'capture-manifest.json'),'checks':records})
    print('Final integrity passed',len(records),'resource summaries',len(files),'raw files')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
