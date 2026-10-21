"""Validate concrete Spring task/Future facts; this phase does not infer origins."""
from collections import defaultdict
from query_observation_planner import require, descriptors
from infer_execution_kernel import same_value
from analysis_status import AnalysisLimit


def validate_async_protocol(plan, rows):
    config = plan.get('async_protocol')
    if not config:
        return {'enabled': False}
    require(config.get('version') == 1 and config.get('observation_only') is True,
            'Unsupported async protocol')
    runtime = [r for r in rows if r['kind'] == 'async-runtime']
    # A plan may execute a branch with no submission at all.
    if not runtime:
        require(not any(r['kind'].startswith('async-') and r['kind'] != 'async-framework'
                        for r in rows), 'Missing async runtime evidence')
        return {'enabled': True, 'observation_only': True, 'tasks': []}
    require(len(runtime) == 1 and any(all(runtime[0].get(k) == p[k]
            for k in ('java_runtime_version', 'class_sha256'))
            for p in config['runtime_profiles']), 'Async runtime hash differs')
    pins = {r['class']: r['sha256'] for r in rows if r['kind'] == 'async-framework'}
    necessary = {'org/springframework/aop/interceptor/AsyncExecutionAspectSupport',
                 'org/springframework/aop/interceptor/AsyncExecutionInterceptor',
                 'org/springframework/aop/interceptor/AsyncExecutionInterceptor$1'}
    if any(r['kind'] == 'async-worker-inner' and r.get('inner_class') ==
           'org.springframework.scheduling.annotation.AsyncResult' for r in rows):
        necessary.add('org/springframework/scheduling/annotation/AsyncResult')
    require(necessary <= pins.keys() and all(config['class_sha256'].get(k) == v
            for k, v in pins.items()), 'Async Spring framework hashes missing/differ')
    grouped = defaultdict(list)
    for r in rows:
        if r['kind'].startswith('async-') and 'task_id' in r:
            grouped[r['task_id']].append(r)
    starts = {r['call_id']: r for r in rows if r['kind'] == 'collection-call-enter'}
    completions = {r['call_id']: r for r in rows
                   if r['kind'] in ('collection-call-exit', 'collection-call-throw')}
    futures, reports = {}, []
    for task, events in grouped.items():
        def one(kind, optional=False):
            found = [r for r in events if r['kind'] == kind]
            require(len(found) <= 1 if optional else len(found) == 1,
                    'Async task lifecycle missing/duplicate: ' + kind)
            return found[0] if found else None
        submit = one('async-submit-begin')
        require(isinstance(task, int) and task > 0, 'Async task ID invalid')
        complete, rejected = one('async-submit-end', True), one('async-submit-throw', True)
        require(bool(complete) != bool(rejected), 'Async submit completion absent/ambiguous')
        finish = complete or rejected
        require(submit['seq'] < finish['seq'] and submit['thread'] == finish['thread']
                and submit['caller_frame'] == finish.get('frame'), 'Async submit caller/order differs')
        parent = starts.get(submit['parent_call_id'])
        require(parent and parent['frame'] == submit['caller_frame']
                and parent['seq'] < submit['seq'], 'Async parent call absent/different')
        parent_end = completions.get(submit['parent_call_id'])
        require(parent_end and finish['seq'] < parent_end['seq'], 'Async parent call completion absent')
        begin, end, failed = (one(k, True) for k in
                             ('async-worker-start', 'async-worker-end', 'async-worker-throw'))
        frames = [r for r in rows if r['kind'] == 'enter' and r.get('async_task_id') == task]
        report = {'task_id': task, 'caller_frame': submit['caller_frame'],
                  'parent_call_id': submit['parent_call_id'], 'worker_frames': len(frames),
                  'method': submit.get('method'), 'gets': [], 'known_origins_created': 0}
        if rejected:
            require(not (begin or end or failed or frames), 'Rejected task has worker execution')
            require(parent_end['kind'] == 'collection-call-throw'
                    and parent_end['exception'] == rejected['exception'], 'Submission exception differs')
            report['status'] = 'submission_rejected'
            reports.append(report)
            continue
        obj = complete['future']['object']
        require(obj and obj not in futures, 'Outer future absent or reused')
        if complete['future_class'] != 'java.util.concurrent.FutureTask':
            raise AnalysisLimit('async-future-type', 'Only the pinned outer FutureTask protocol is supported')
        futures[obj] = (task, end, failed)
        require(parent_end['kind'] == 'collection-call-exit'
                and parent_end['result'] == complete['future'], 'Returned outer future differs')
        if begin:
            require(bool(end) != bool(failed), 'Started async worker lacks unique completion')
            terminal = end or failed
            require(submit['seq'] < begin['seq'] < terminal['seq']
                    and begin['thread'] == terminal['thread'], 'Async worker order/thread differs')
            require(all(begin['seq'] < f['seq'] < terminal['seq']
                        and f['thread'] == begin['thread'] for f in frames), 'Async worker frame escapes task')
            if not submit.get('supported') or not submit.get('future_return'):
                raise AnalysisLimit('async-callable', 'Unsupported async callable or declared return type')
            if submit['method'] not in plan['execution_kernel']['methods']:
                raise AnalysisLimit('async-worker-method', 'Async application method has no executable bytecode plan')
            roots = [f for f in frames if f['method'] == submit['method'] and f.get('parent') is None]
            require(len(roots) == 1, 'Async application worker frame missing/ambiguous')
            root = roots[0]
            require(root['receiver'] == submit['receiver']['object']
                    and len(root['args']) == len(submit['args'])
                    and len(parent['args']) == len(submit['args']),
                    'Async worker receiver/arguments differ')
            types = descriptors(submit['method'][submit['method'].index('('):])
            for descriptor, expected, actual, caller in zip(types, submit['args'], root['args'], parent['args']):
                if descriptor.startswith(('L', '[')):
                    require(expected == actual == caller, 'Async reference argument identity differs')
                else:
                    same_value(expected, actual); same_value(expected, caller)
            root_ends = [r for r in rows if r['kind'] in ('exit', 'abort') and r.get('frame') == root['frame']]
            require(len(root_ends) == 1, 'Async worker frame completion missing')
            report['worker_frame'] = root['frame']
            if end:
                inner, unwrapped = one('async-worker-inner'), one('async-worker-unwrapped')
                require(root_ends[0]['kind'] == 'exit' and root_ends[0]['result'] == inner['inner']
                        and inner['inner_class'] == 'org.springframework.scheduling.annotation.AsyncResult'
                        and root_ends[0]['seq'] < inner['seq'] < unwrapped['seq'] < end['seq']
                        and unwrapped['result'] == end['result'], 'Async inner future/result identity differs')
            report['status'] = 'worker_completed' if end else 'worker_exceptional'
            report['rpc_messages'] = [r.get('message') for r in rows
                if r['kind'] == 'http-rpc-enter' and r['thread'] == begin['thread']
                and begin['seq'] < r['seq'] < terminal['seq']]
        else:
            require(not (end or failed or frames), 'Async worker completion without start')
            report['status'] = 'not_started'
        reports.append(report)
    by_task = {r['task_id']: r for r in reports}
    require(all(r.get('async_task_id') in by_task for r in rows
                if r['kind'] == 'enter' and 'async_task_id' in r),
            'Worker frame refers to absent task')
    for call, completion in completions.items():
        parent = starts.get(call)
        if parent and parent.get('receiver', {}).get('object') in futures:
            if '.get(' in parent['callee'] or '.cancel(' in parent['callee']:
                require('async_future' in completion, 'Necessary Future observation missing')
    for row in rows:
        a = row.get('async_future')
        if not a:
            continue
        parent = starts.get(row.get('call_id'))
        require(parent and parent['receiver'] == a['future']
                and parent['seq'] < row['seq'], 'Future observation caller/receiver differs')
        require(a['completion'] == ('normal' if row['kind'] == 'collection-call-exit' else 'exceptional')
                and ('.get(' if a['operation'] == 'get' else '.cancel(') in parent['callee'],
                'Future operation/completion differs')
        if a['completion'] == 'exceptional':
            require(a['exception'] == row['exception'] and a['exception_type'] == row['exception_type'],
                    'Future exception observation differs')
        obj = a['future']['object']
        if obj not in futures:
            require(a['task_id'] is None, 'Future linked to unknown task')
            continue
        task, end, failed = futures[obj]
        require(task == a['task_id'], 'Future task binding differs')
        if a['operation'] == 'get':
            if a['completion'] == 'normal':
                require(end and end['seq'] < row['seq'] and end['result'] == row['result'] == a['result'],
                        'Future result/completed task identity differs')
            elif a['exception_type'] == 'java.util.concurrent.ExecutionException':
                require(failed and failed['seq'] < row['seq'] and failed['exception'] == a['cause'],
                        'Future failure cause differs')
            else:
                require(a['exception_type'] in ('java.util.concurrent.TimeoutException',
                        'java.util.concurrent.CancellationException', 'java.lang.InterruptedException'),
                        'Unsupported Future exception')
        else:
            require(a['operation'] == 'cancel', 'Unknown Future operation')
        by_task[task]['gets'].append({'call_id': row['call_id'], 'operation': a['operation'],
                                     'completion': a['completion']})
    return {'enabled': True, 'observation_only': True, 'tasks': reports}
