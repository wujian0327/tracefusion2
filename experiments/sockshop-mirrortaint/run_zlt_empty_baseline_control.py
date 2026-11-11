"""Separate empty-page control; never replaces the original six paging inputs."""
import argparse, copy, json
from pathlib import Path
from run_planned_service import load, save
from run_galette_static_calibration import verify, fixed_runtime
from seal_galette_static_baselines import H
from tf_static_baseline import configure


def run(mode):
    import run_target_closure_cost as zlt
    from run_planned_service import ROOT
    verify(); protocol = load(H/'empty-control-before-runs.json')
    ref = ROOT/'artifacts/shared-transfer-optimization-20261106/final-candidate'
    zlt.FINAL = ref
    zlt.BASE = ROOT/'artifacts/pruning-contribution-audit-20261106/final-candidate/historical/frozen-base'
    zlt.verify = verify; zlt.fresh = lambda *a: None
    spec = zlt.zlt_spec
    actual_mode = 'selective' if mode == 'static' else mode
    def configured(home, out, task, arm, projection_off=False):
        cfg, query = spec(home, out, task, arm, projection_off)
        query = copy.deepcopy(query); query['inputs'] = [protocol['input']]
        if mode in ('full', 'static', 'selective'):
            service = cfg['services'][query['role']]
            plan = ref/'zlt/planning-first/ZLT-MP-4/000-plan.json'
            policy = configure(load(plan), mode); cmd = service['command']
            cmd[:] = [a for a in cmd if not a.startswith(('-Dservice.mode=', '-Dservice.target.observation=', '-Dservice.body.observation=', '-Dservice.write.observation='))]
            cmd[cmd.index('-jar'):cmd.index('-jar')] = policy['jvm_options']
            save(out/'baseline-policy.json', policy)
        return fixed_runtime(cfg), query
    zlt.zlt_spec = configured
    out = H/'empty-control'/mode
    zlt.zlt_trial(out.parent, out.name, 'zlt-user', actual_mode, 0, 3, sample=False)
    cases = load(out/'measure.json')['requests']
    assert len(cases) == 6 and all(c['http_status'] == 200 and c['response']['data'] == [] for c in cases), 'Preselected high page was not empty; do not replace it'
    if mode != 'original':
        original = load(H/'empty-control/original/measure.json')['requests']
        assert all(c['response'] == original[i]['response'] for i, c in enumerate(cases))
    paired = []
    if mode in ('full', 'static', 'selective'):
        from external_transfer_oracle import require_complete_raw_capture
        rows = [json.loads(l) for l in (out/'capture/events.jsonl').read_text().splitlines()]
        require_complete_raw_capture(rows)
        starts = [r for r in rows if r['kind'] == 'collection-call-enter' and r.get('callee') == protocol['source']]
        assert len(starts) == 6
        for a in starts:
            ends = [r for r in rows if r['kind'] == 'collection-call-exit' and r.get('call_id') == a['call_id']]
            assert len(ends) == 1; b = ends[0]
            assert a['seq'] < b['seq'] and all(a[k] == b[k] for k in ('frame', 'method', 'pc', 'thread')) and b['result'].get('object')
            paired.append({'call_id': a['call_id'], 'start': a['seq'], 'end': b['seq'], 'frame': a['frame'], 'caller': a['method'], 'pc': a['pc'], 'result': b['result']})
        assert not any(f['path'].endswith('/username') for r in rows if r['kind'] == 'binding-return' for f in r['fields'])
        # Validate the entire capture, not only its empty field list.
        from infer_distributed_fields import Reconstruction
        plan = ref/'zlt/planning-first/ZLT-MP-4/000-plan.json'
        b = out/'audit/build/role'; b.mkdir(parents=True); (b/'plan.json').write_bytes(plan.read_bytes())
        c = out/'audit/capture/role'; c.mkdir(parents=True); (c/'events.jsonl').symlink_to((out/'capture/events.jsonl').resolve())
        Reconstruction(out/'audit/build', out/'audit/capture', ['role'])
    elif mode == 'mirrortaint':
        from native_source_protocol import validate
        from run_mirror_capability_probe import read_events
        view = out/'audit/native-view/role'; view.parent.mkdir(parents=True); view.symlink_to((out/'capture').resolve(), target_is_directory=True)
        rows = read_events(view.parent, 'role'); validate(rows)
        starts = [r for r in rows if r['kind'] == 'source-call-enter' and r.get('callee') == protocol['source']]
        assert len(starts) == 6
        for a in starts:
            ends = [r for r in rows if r['kind'] == 'source-call-exit' and r.get('source_call_id') == a['source_call_id']]
            assert len(ends) == 1 and a['seq'] < ends[0]['seq']
            paired.append({'call_id': a['source_call_id'], 'start': a['seq'], 'end': ends[0]['seq']})
    save(out/'checks.json', {'business_requests': 6, 'business_preserved': True, 'empty_pages': 6,
        'declared_target_count': 0, 'positive_answers_added': 0, 'source_pair_count': len(paired) if mode != 'original' else None,
        'source_pairs': paired, 'not_a_positive_provenance_accuracy_sample': True, 'original_six_input_scores_unchanged': True})


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--mode', choices=('original', 'mirrortaint', 'full', 'static', 'selective'), required=True)
    run(p.parse_args().mode)
