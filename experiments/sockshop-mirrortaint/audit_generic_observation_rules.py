"""Same-execution compatibility and literal raw-fact checks; no new timing."""
import argparse
import copy
import json
import subprocess
import types
import shutil
from pathlib import Path
from run_planned_service import load, save, sha, ROOT
from run_generic_observation_rules import verify, COMMIT
from infer_execution_kernel import infer_execution


def run(home, out):
    out.mkdir(parents=True, exist_ok=False); freeze = verify()
    import infer_execution_closure as closure
    old = types.ModuleType('frozen_closure_reference')
    original = subprocess.check_output(['git', 'show', COMMIT+':experiments/sockshop-mirrortaint/infer_execution_closure.py'], cwd=ROOT, text=True)
    exec(compile(original, '<frozen-closure-reference>', 'exec'), old.__dict__)
    current = closure.validate_application_writes; compatibility = []; online_signatures = []
    base=home/'controls-03' if (home/'controls-03').exists() else home
    members=home/'member-slots-02' if (home/'member-slots-02').exists() else home/'member-slots'
    cases = [('remove-if', base/'remove-if', 'plan.json', 'events.jsonl'),
             ('json-copy', base/'json-copy', 'plan.json', 'events.jsonl'),
             ('json-copy-cold', base/'json-copy-cold', 'plan.json', 'events.jsonl'),
             ('write-values', base/'write-values', 'build/fixture/plan.json', 'fixture/events.jsonl'),
             ('write-guard-off', home/'write-guard-off', 'build/fixture/plan.json', 'fixture/events.jsonl'),
             ('member-slots', members, 'plan.json', 'events.jsonl')]
    for label, dest, plan_path, capture in cases:
        p = load(dest/plan_path)
        signatures = {}
        for mode in ('full', 'selective'):
            path = dest/mode/capture; rows = [json.loads(s) for s in path.read_text().splitlines()]
            try:
                closure.validate_application_writes = old.validate_application_writes
                before = infer_execution(p, rows)
            finally:
                closure.validate_application_writes = current
            after = infer_execution(p, rows)
            assert before == after, (label, mode)
            compatibility.append({'control': label, 'mode': mode, 'capture_sha256': sha(path),
                                  'answers': len(after['answers']), 'entire_result_equal': True})
            by_seq = {r['seq']: r for r in rows}
            occurrences = {}; counts = {}
            for row in rows:
                if row['kind'] in ('binding-source','binding-input'):
                    key=(row['kind'],row.get('callee'),row.get('argument'))
                    occurrences[row['seq']]=counts.get(key,0); counts[key]=counts.get(key,0)+1
            def token(t):
                if t[0]=='field':
                    r=by_seq[t[1]]; f=r['fields'][t[2]]
                    return (r['kind'], occurrences.get(r['seq']), r.get('argument'), r.get('callee'), f.get('path'), f['field'], f['version'])
                return tuple(t)
            signatures[mode] = [(a['path'],a['field'],a['version'],a['known'],sorted(map(token,a['origins']),key=repr),sorted(map(token,a['selectors']),key=repr)) for a in after['answers']]
        assert signatures['full']==signatures['selective'], label
        online_signatures.append({'control':label,'target_status_version_source_occurrences_selectors_equal':True,'physical_ids_compared_across_jvms':False})
    root = base/'write-values'; p = load(root/'build/fixture/plan.json')
    selective = [json.loads(s) for s in (root/'selective/fixture/events.jsonl').read_text().splitlines()]
    full = [json.loads(s) for s in (root/'full/fixture/events.jsonl').read_text().splitlines()]
    writes = [r for r in selective if r['kind']=='write-version']
    target_writes = [r for r in selective if r['kind']=='write' and r['field']==p['target']]
    assert writes and target_writes and all('observed' in r for r in target_writes)
    same_value_overwrites = []
    for r in target_writes:
        if '.setText(' not in r['site']: continue
        earlier = [f for e in selective if e['seq']<r['seq'] and e['kind']=='binding-input' for f in e.get('fields',[]) if f['owner']==r['owner'] and f['field']==r['field']]
        assert earlier and r['observed']['value']==earlier[-1]['observed']['value']=='SAME'
        assert r['version']==earlier[-1]['version']+1
        same_value_overwrites.append({'seq':r['seq'],'previous_version':earlier[-1]['version'],'new_version':r['version'],'value_retained':True})
    assert same_value_overwrites
    for r in writes:
        assert r['field'] != p['target'] and 'observed' not in r
        assert any(e['kind']=='exit' and e['seq']>r['seq'] and any(f['owner']==r['owner'] and f['field']==r['field'] and f['version']==r['version'] for f in e.get('fields', [])) for e in selective)
    corrupted = copy.deepcopy(selective)
    next(r for r in corrupted if r['kind']=='write-version')['version'] += 1
    closure.validate_application_writes = old.validate_application_writes
    try:
        infer_execution(p, corrupted); old_accepted = True
    finally:
        closure.validate_application_writes = current
    try:
        infer_execution(p, corrupted)
    except ValueError as e:
        refusal = str(e)
    else:
        raise AssertionError('Corrupted write version accepted')
    # A full-mode capture is not a license to backfill selective eligibility.
    bad = copy.deepcopy(full)
    candidate = next(r for r in bad if r['kind']=='write' and r['site'] in p['execution_observation_closure']['application_write_values']['sites'])
    candidate['kind'] = 'write-version'; candidate.pop('observed')
    try:
        infer_execution(p, bad)
    except ValueError as e:
        projection_refusal = str(e)
    else:
        raise AssertionError('Unlicensed full-mode projection accepted')
    from infer_distributed_fields import Reconstruction
    sticky = []
    for mode in ('full','selective'):
        # Protection copy only: remove the problem's meaning, keep sequence and
        # the original sticky footer; do not carry the failure sidecar across.
        original_rows=[json.loads(s) for s in (base/'remove-if'/(mode+'-unsupported')/'events.jsonl').read_text().splitlines()]
        assert any(r['kind']=='problem' for r in original_rows)
        derived=copy.deepcopy(original_rows)
        for row in derived:
            if row['kind']=='problem': row['kind']='counterexample-marker'
        dest=out/'sticky-protections'/mode; (dest/'build/fixture').mkdir(parents=True); (dest/'capture/fixture').mkdir(parents=True)
        shutil.copyfile(base/'remove-if/plan.json',dest/'build/fixture/plan.json')
        (dest/'capture/fixture/events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in derived))
        try: Reconstruction(dest/'build',dest/'capture',['fixture'])
        except ValueError as e:
            assert str(e)=='Collector problem'; sticky.append({'mode':mode,'no_problem_events':True,'no_sidecar':True,'footer_refused':True})
        else: raise AssertionError('Sticky-invalid batch accepted')
    save(out/'results.json', {'freeze': freeze, 'same_execution_compatibility': compatibility,'new_full_selective_logical_signatures':online_signatures,
         'online_raw_checks': {'version_only_writes': len(writes), 'target_writes_with_payload': len(target_writes), 'same_value_target_overwrites':same_value_overwrites,'omitted_writes_match_actual_exit_versions': True},
         'new_counterexample': {'original_accepted': old_accepted, 'candidate_refusal': refusal},
         'sticky_footer_protections':sticky,
         'derived_omission_projection': {'status': 'not_testable_as_a_positive_preservation_claim', 'reason': 'Full capture header forbids omission; no pre-omission selective guard license is emitted. Runtime-disable capture also does not prove a successful guard. Never rewrite mode or manufacture a later completion license.', 'unlicensed_projection_refused': projection_refusal},
         'scope': 'Unchanged complete captures old/new offline validation, not a new Agent deployment or performance result.'})
    print('Compatibility:', len(compatibility), 'complete captures; wrong-version:', refusal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--home', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); run(a.home.resolve(), a.out.resolve())
