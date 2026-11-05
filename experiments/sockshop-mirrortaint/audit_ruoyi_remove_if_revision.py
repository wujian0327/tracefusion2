"""Re-score the fixed three-query subset; never derive truth from TF diagnostics."""
import argparse, collections, csv, json
from pathlib import Path
from run_planned_service import ROOT, load, save, sha
from run_ruoyi_request_scope_revision import score
from diagnose_source_loss import run as diagnose


def run(home, out):
    out.mkdir(parents=True, exist_ok=False)
    freeze=load(home/'algorithm-freeze.json')
    offline=load(home/'offline-freeze.json')
    for name, digest in offline['sources'].items():
        assert sha(Path(name)) == digest, name
    for name, digest in load(home/'protocol-before-change.json')['old_files'].items():
        assert sha(ROOT/name) == digest, name
    assert sha(home/'candidate/distributed-observer.jar') == freeze['agent_sha256']
    rows=[]; receipts=[]; diagnostics=[]; lost=[]
    for query in ('ruoyi-2', 'ruoyi-3', 'ruoyi-1'):
        dest=out/query
        score(home/'final-C1', dest, query)
        rows.extend(load(dest/'instances.json')); receipts.extend(load(dest/'receipts.json'))
        for mode in ('full', 'selective'):
            capture=home/'final-C1/runs'/query/mode/'capture/events.jsonl'
            events=[json.loads(line) for line in capture.read_text().splitlines()]
            diagnostics.extend(dict(query=query, mode=mode, **r) for r in events
                               if r['kind']=='binding-unsupported-list')
            if query == 'ruoyi-2':
                target=out/('loss-'+mode)
                diagnose(home/'final-C1/plans'/query/'plan.json', capture, target)
                losses=load(target/'source-first-loss.json')['first_losses']
                for item in load(dest/'instances.json'):
                    if item['mode'] != mode: continue
                    expected=item.get('expected', [])
                    matches=[v for v in losses for s in expected if
                             (v['source_seq'], v['source_owner'], v['source_field'], v['source_version'])
                             == (s[2], s[4], s[5], s[6])]
                    lost.append(dict(mode=mode, case=item['case'], path=item['path'],
                                     state=item['state'], first_losses=matches))
    with (ROOT/'experiments/sockshop-mirrortaint/ruoyi-request-scope-paired-20261104.csv').open() as f:
        previous={(r['query'],r['mode'],int(r['case']),r['path']):r for r in csv.DictReader(f)}
    for r in rows:
        old=previous[(r['query'],r['mode'],r['case'],r['path'])]
        r['previous_TF_state']=old['state'];r['historical_MT_state']=old['reference_MT_state']
    normalized=lambda r:(r['query'],r['case'],r['path'],r['state'],
                         sorted((s[0],s[3],s[5]) for s in r.get('predicted',[])))
    assert sorted(normalized(r) for r in rows if r['mode']=='full') == sorted(
        normalized(r) for r in rows if r['mode']=='selective')
    assert all(r['business_preserved']==r['business_requests']==6 for r in receipts)
    assert all(r['state']=='known_correct' for r in rows if r['query']=='ruoyi-1')
    assert len([r for r in rows if r['query']=='ruoyi-1'])==10
    summary={'online_freeze':freeze['commit'], 'offline_freeze':offline['commit'], 'agent_sha256':freeze['agent_sha256'],
             'full_selective_states_and_logical_sources_equal':True,
             'states':{q:{m:dict(collections.Counter(r['state'] for r in rows if
                       r['query']==q and r['mode']==m)) for m in ('full','selective')}
                       for q in ('ruoyi-1','ruoyi-2','ruoyi-3')},
             'dictionary_runtime_classes':sorted({r['runtime_class'] for r in diagnostics
                                                  if r['query']=='ruoyi-3'}),
             'business_receipts':receipts, 'original_files_unchanged':True,
             'scope':'New Agent deployments for three exposed C1 tasks only; no complete five-query or historical reacceptance, no performance measurements.'}
    save(out/'summary.json', summary); save(out/'instances.json', rows)
    save(out/'unsupported-list-events.json', diagnostics); save(out/'target-first-loss.json',lost)
    with (out/'instances.csv').open('w') as f:
        fields=list(dict.fromkeys(k for r in rows for k in r))
        writer=csv.DictWriter(f,fields,lineterminator='\n');writer.writeheader();writer.writerows(rows)
    print(summary['states'], summary['dictionary_runtime_classes'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    run(a.home.resolve(),a.out.resolve())
