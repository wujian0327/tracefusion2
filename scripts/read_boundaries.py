"""Language-neutral pread result versions linked to executed field dependencies.

Contract: preopened immutable regular files; one thread; pread is the sole
writer of source bytes after scope entry; no reads during observed computation.
No inference from value equality and no oracle input. Unsupported histories fail.
"""
from pathlib import PurePath
import struct

from hybrid_model import require
from language_adapters import get_adapter
import loop_calls_provenance as core

INSTRUCTION, READ_ENTER, READ_EXIT, SCOPE_ENTER, SCOPE_EXIT, INVALIDATE = range(6)
MAX_READ_BYTES = 32


def bind(events, plans, config, runtime):
    try:
        require(events and len(events) <= 20000, 'Empty or oversized read history')
        rows = sorted(events, key=lambda e: e['observation_sequence'])
        require([e['observation_sequence'] for e in rows] == list(range(len(rows))), 'Missing or duplicate global observation sequence')
        require(rows[0]['kind'] == SCOPE_ENTER and rows[-1]['kind'] == SCOPE_EXIT, 'Missing workload boundary')
        require(sum(e['kind'] == SCOPE_ENTER for e in rows) == sum(e['kind'] == SCOPE_EXIT for e in rows) == 1, 'Repeated workload scope')
        require(len({e['pid_tid'] for e in rows}) == 1, 'Multiple read execution contexts unsupported')
        require(all(a['timestamp'] <= b['timestamp'] for a,b in zip(rows, rows[1:])), 'Non-monotonic observation order')
        files = runtime['read_files']; memory = {}; pending = None; operations = []; snapshots = {}; active = None
        instructions = {(fid,n['offset']): n for fid,p in enumerate(plans) for n in p['instructions']}
        compute = []
        for event in rows[1:-1]:
            kind = event['kind']
            if kind == READ_ENTER:
                require(active is None and pending is None, 'Read overlaps computation or another read')
                require(event['io_id'] == len(operations)+1, 'Missing or repeated read operation')
                require(0 < event['requested'] <= MAX_READ_BYTES and event['file_offset'] >= 0, 'Unsupported read range')
                require(event['buffer_addr'] > 0 and event['buffer_addr'] + event['requested'] < 1 << 64, 'Invalid read buffer')
                pending = event
            elif kind == READ_EXIT:
                require(pending is not None and active is None, 'Unpaired read return')
                require(all(event[k] == pending[k] for k in ('io_id','fd','file_offset','requested','buffer_addr','pid_tid')), 'Read return contradicts entry')
                returned = event['returned']
                require(-4095 <= returned <= event['requested'], 'Invalid syscall return')
                require(event['read_error'] == 0 and len(event['read_data']) == MAX_READ_BYTES, 'Read result snapshot failed')
                file = files.get(str(event['fd']))
                op = dict(io_id=event['io_id'], id='%s:pread:%s' % (event['pid_tid'],event['io_id']),
                          api='pread64', fd=event['fd'], file=file, file_offset=event['file_offset'],
                          requested=event['requested'], returned=returned, buffer_addr=event['buffer_addr'],
                          entry_sequence=pending['observation_sequence'], exit_sequence=event['observation_sequence'],
                          data=event['read_data'][:max(0,returned)])
                if returned > 0:
                    require(file is not None and file['regular'] and file['access_mode'] == 0, 'Unknown or mutable file descriptor')
                    require(event['file_offset'] + returned <= file['size'], 'Read contradicts snapshotted file size')
                    for i in range(returned):
                        memory[event['buffer_addr']+i] = (op, i, event['read_data'][i])
                operations.append(op); pending = None
            elif kind == INSTRUCTION:
                require(pending is None, 'Computation overlaps pending read')
                if active is None:
                    require(event['sequence'] == 0 and event['offset'] == 0 and event['depth'] == 1, 'Missing compute entry')
                    key = (event['pid_tid'],event['call_id'])
                    require(key not in snapshots, 'Repeated compute invocation')
                    active = key
                    snapshots[key] = (dict(memory), event, len(operations))
                require(active == (event['pid_tid'],event['call_id']), 'Interleaved compute invocations')
                compute.append(event)
                node = instructions[event['function'],event['offset']]
                if node['op'] == 'ret' and event['depth'] == 1: active = None
            else:
                raise ValueError('Unsupported descriptor lifecycle or boundary event')
        require(active is None and pending is None, 'Unclosed read or compute invocation')
        require(operations and compute, 'No reads or computations observed')
        inferred = core.infer(compute, plans, config, runtime['functions'])
        require(not inferred['issues'], 'Machine replay failed: ' + str(inferred['issues']))
        layout = get_adapter(config).layout(config,'input')
        for result in inferred['results']:
            memory, first, attempts = snapshots[result['pid_tid'],result['call_id']]
            sources = {}; graph = result['dependency_graph']; added = set()
            for read in result['contributing_reads']:
                field = layout.field(read['field'].removeprefix('input.'))
                address = first['src_addr'] + field.offset
                version = [memory.get(address+i) for i in range(field.width)]
                require(all(v is not None for v in version), 'Contributing field has no observed read origin')
                op = version[0][0]; start = version[0][1]
                require(all(v[0]['id'] == op['id'] and v[1] == start+i for i,v in enumerate(version)), 'Partial or mixed-version field unsupported')
                value = struct.unpack('<I',bytes(v[2] for v in version))[0]
                require(value == first['inputs'][field.offset//4], 'Input changed after observed read')
                file_offset = op['file_offset'] + start
                origin_id = '%s:bytes:%d:%d' % (op['id'],file_offset,field.width)
                origin = dict(id=origin_id, operation_id=op['id'], io_id=op['io_id'],
                              file_name=PurePath(op['file']['path']).name, file=op['file'],
                              file_offset=file_offset, length=field.width)
                sources[origin_id] = origin
                read['external_source_id'] = origin_id
                if op['id'] not in added:
                    graph['nodes'].append(dict(id=op['id'],kind='external-read-operation',api='pread64',
                                               io_id=op['io_id'],file=op['file'],file_offset=op['file_offset'],returned=op['returned']))
                    added.add(op['id'])
                if origin_id not in added:
                    graph['nodes'].append(dict(id=origin_id,kind='read-result-range',file_offset=file_offset,length=field.width))
                    graph['edges'].append(dict(source=op['id'],target=origin_id,kind='read-result'))
                    added.add(origin_id)
                node = next(n for n in graph['nodes'] if n.get('local_node') == read['id'])
                node['external_source_id'] = origin_id
                graph['edges'].append(dict(source=origin_id,target=node['id'],kind='read-result'))
            result['external_sources'] = sorted(sources.values(),key=lambda s:(s['io_id'],s['file_offset']))
            result['read_attempts_before_entry'] = attempts
        inferred.update(read_operations=operations, boundary_issues=[],
                        scope='Observed pread returns -> fixed field versions -> common executed dependency graph; immutable files and pread-only source writers')
        return inferred
    except (ValueError,KeyError,IndexError,TypeError,StopIteration,struct.error) as exc:
        return dict(results=[],issues=[dict(error=str(exc))],boundary_issues=[dict(error=str(exc))],
                    read_operations=[],oracle_used_for_inference=False)


def evaluate(inferred, oracle, stats, plans):
    result = core.common.evaluate(inferred,oracle,stats,plans)
    result.pop('static_source_relations')
    rows = {r['call_id']:r for r in inferred['results']}
    tp = fp = fn = 0
    def keys(items):
        return {(s['io_id'],s['file_name'],s['file_offset'],s['length']) for s in items}
    for truth,check in zip(oracle,result['checks']):
        row = rows.get(truth['sequence'],{})
        expected,observed = keys(truth['expected_external_sources']),keys(row.get('external_sources',[]))
        tp += len(expected & observed); fp += len(observed-expected); fn += len(expected-observed)
        check.update(expected_external_sources=sorted(expected),observed_external_sources=sorted(observed),
                     expected_read_attempts=truth['expected_read_attempts'],observed_read_attempts=row.get('read_attempts_before_entry'))
        check['passed'] = check['passed'] and expected == observed and check['expected_read_attempts'] == check['observed_read_attempts']
    result['passed'] = result['passed'] and not inferred.get('boundary_issues') and all(c['passed'] for c in result['checks'])
    result['external_source_relations'] = dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None)
    result['read_operations'] = len(inferred.get('read_operations',[]))
    result['expected_read_operations'] = max((t['expected_read_attempts'] for t in oracle),default=0)
    result['passed'] = result['passed'] and result['read_operations'] == result['expected_read_operations']
    result['scope'] = 'Fixture output, input-field origins and exact read-operation/file-offset sources; no general database or graph-edge accuracy claim'
    return result
