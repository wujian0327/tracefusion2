#!/usr/bin/env python3
"""Local cost-profile checks. Converted old records are NOT new Pin execution."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import zipfile

import host_records
import perf_records
import performance as perf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='Already verified ngiflib correctness archive')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    passed = []
    with zipfile.ZipFile(args.archive) as z:
        prefix = z.namelist()[0].split('/')[0]+'/'
        read = lambda p: z.read(prefix+p)
        plan = json.loads(read('plan.json'))
        data = read('fixture/blocks/normal.gif')
        for method in ('boundary_replay', 'libdft64'):
            original = [json.loads(line) for line in read('blocks-truecolor/'+method+'/raw.jsonl').splitlines()]
            old_trace, old_external, _ = host_records.normalize(original, plan, data, method=='libdft64')
            rows = copy.deepcopy([r for r in original if r['kind'] != 'instruction'])
            for i, row in enumerate(rows, 1):
                row['record'] = i
            rows[-1].update(steps=0, ignored_shifts=0, performance_eligible=True,
                            profile='boundary-cost-v1', instruction_diagnostics=False)
            trace, external, _ = perf_records.normalize(rows, plan, data, method=='libdft64')
            assert trace == old_trace and external == old_external
            passed.append(method+'_compacted_transport_matches_416_existing_queries')
            if method == 'libdft64':
                tainted_rows = rows
            else:
                clean_rows = rows
        def reject(name, edit):
            rows = copy.deepcopy(tainted_rows)
            edit(rows)
            try:
                perf_records.normalize(rows, plan, data, True)
            except (ValueError, KeyError):
                passed.append(name)
            else:
                raise AssertionError('Accepted fault '+name)
        def first(rows, kind):
            return next(r for r in rows if r['kind'] == kind)
        reject('missing_finish', lambda r: r.pop())
        reject('missing_boundary_record', lambda r: r.pop(10))
        reject('context_change', lambda r: r[-1].update(contexts=1))
        reject('wrong_profile', lambda r: r[-1].update(profile='other'))
        reject('diagnostics_enabled', lambda r: r[-1].update(instruction_diagnostics=True))
        reject('nonzero_instruction_counter', lambda r: r[-1].update(steps=1))
        reject('unknown_call_pc', lambda r: first(r,'call_enter').update(pc=0))
        reject('bad_source_seed', lambda r: next(x for x in r if x['kind']=='read_exit' and x['source']).update(byte_labels=[]))
        reject('unknown_sink_label', lambda r: first(r,'word_exit').update(byte_labels=[[1],[]]))
        reject('incomplete_scope', lambda r: r[-1].update(active=True))
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            # Exercise fresh-process timing AND replay worker on converted records.
            perf.save(work/'plan.json', plan)
            (work/'input.gif').write_bytes(data)
            (work/'raw.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in clean_rows))
            offline = work/'offline'
            offline.mkdir()
            measurement = perf.measured([sys.executable, perf.HERE/'performance.py', '_worker', '--plan', work/'plan.json',
                '--input', work/'input.gif', '--raw', work/'raw.jsonl', '--method', 'boundary_replay', '--output', offline], offline, 60)
            result = json.loads((offline/'inference.json').read_text())
            expected = json.loads(read('blocks-truecolor/boundary_replay/inference.json'))
            assert result == expected
            phases = json.loads((offline/'phases.json').read_text())
            assert measurement['wall_seconds'] >= phases['total_wall_seconds'] > 0
            assert measurement['cpu_seconds'] > 0 and measurement['peak_rss_bytes'] > 0
            passed.append('fresh_worker_replay_and_resource_accounting')
            for name, argv, limit in [('exit_failure',[sys.executable,'-c','raise SystemExit(7)'],5),
                                      ('timeout',[sys.executable,'-c','import time; time.sleep(5)'],.05)]:
                folder = work/name
                folder.mkdir()
                try:
                    perf.measured(argv,folder,limit)
                except ValueError:
                    passed.append('reject_measured_'+name)
                else:
                    raise AssertionError('Failed child accepted')
    order = perf.schedule(2, 10, 20261010)
    assert order == perf.schedule(2, 10, 20261010) and len(order) == 96
    assert all(set(r['groups']) == set(perf.GROUPS) for r in order)
    samples = []
    for entry in perf.schedule(1,3,123):
        for group in perf.GROUPS:
            online, offline = (1,9) if group == 'boundary_replay' else (3,1)
            row = dict(entry,group=group,online_wall_seconds=online,online_cpu_seconds=online,
                offline_wall_seconds=offline,offline_cpu_seconds=offline,complete_wall_seconds=online+offline,
                complete_cpu_seconds=online+offline,online_peak_rss_bytes=100,offline_peak_rss_bytes=100,
                complete_peak_rss_bytes=100,raw_bytes=200)
            samples.append(row)
    summary = perf.summarize(samples)
    assert all(r['groups']['native']['online_wall_seconds']['n'] == 3 for r in summary)
    assert all(r['paired_replay_vs_libdft']['online_wall_reduction_percent']['median'] > 0 and
               r['paired_replay_vs_libdft']['complete_wall_reduction_percent']['median'] == -150 for r in summary)
    passed += ['reproducible_balanced_schedule','warmups_excluded_and_offline_reversal_visible']
    result = dict(checks=passed,total=len(passed),converted_prior_host_records=True,
                  new_pin_execution=False,new_libdft_execution=False,performance_result=False)
    perf.save(args.output,result)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
