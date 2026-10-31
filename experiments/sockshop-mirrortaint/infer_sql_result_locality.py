"""Check per-source SQL allocation proofs; this module creates no origins."""
from collections import defaultdict
from query_observation_planner import require


def validate(plan, rows):
    cfg = plan['execution_kernel'].get('sql_result_locality')
    if not cfg:
        return {}
    families, starts, finishes, sources = (defaultdict(list) for _ in range(4))
    classes = defaultdict(list)
    for row in rows:
        kind = row['kind']
        if kind.startswith('sql-locality-') and kind != 'sql-locality-class':
            families[row['ownership_id']].append(row)
        if kind == 'sql-locality-class':
            require(cfg['class_sha256'].get(row['class']) == row['class_sha256'],
                    'SQL ownership implementation differs')
            require(row['instrumented_callsites'] == cfg['instrumented_callsites'].get(row['class'],[]),
                    'SQL necessary callback/handler entry points not armed')
            classes[row['class']].append(row)
        if kind == 'collection-call-enter': starts[row['call_id']].append(row)
        if kind in ('collection-call-exit','collection-call-throw'): finishes[row['call_id']].append(row)
        if kind == 'binding-source': sources[row.get('source_call_id')].append(row)
    result = {}
    for oid, events in families.items():
        begin = [r for r in events if r['kind'] == 'sql-locality-begin']
        end = [r for r in events if r['kind'] == 'sql-locality-end']
        require(len(begin) == len(end) == 1, 'SQL ownership start/completion absent or repeated')
        begin, end = begin[0], end[0]
        require(all(r['call_id'] == begin['call_id'] and r['caller_frame'] == begin['caller_frame']
                    and r['thread'] == begin['thread'] and begin['seq'] <= r['seq'] <= end['seq']
                    for r in events), 'SQL ownership source scope differs')
        calls, exits = starts[begin['call_id']], finishes[begin['call_id']]
        require(len(calls) == len(exits) == 1, 'SQL ownership source pairing absent/ambiguous')
        call, exit = calls[0], exits[0]
        require(call['seq'] < begin['seq'] < end['seq'] < exit['seq']
                and call['frame'] == begin['caller_frame'] == exit['frame']
                and begin['callee'] == call['callee'] == end['source_callee']
                and call['callee'] in cfg['sources']
                and exit.get('sql_result_locality') == {k:v for k,v in end.items()
                    if k not in ('kind','seq','thread','frame','ownership_id','call_id','caller_frame','trace','span','parent_span','message') and not k.startswith('diagnostic_')},
                'SQL ownership invocation/completion rebound')
        if not end['valid']:
            continue
        # Authentication cannot be reduced to an arbitrary caller-supplied
        # subset of hashes. These fixed corridor implementations are necessary
        # even when their own methods are inherited or need no event payload.
        required_armed={
            'com/baomidou/mybatisplus/core/override/MybatisMapperProxy',
            'com/baomidou/mybatisplus/core/override/MybatisMapperProxy$PlainMethodInvoker',
            'com/baomidou/mybatisplus/core/override/MybatisMapperMethod',
            'org/apache/ibatis/binding/MapperMethod$MethodSignature',
            'org/apache/ibatis/binding/MapperMethod$SqlCommand',
            'org/mybatis/spring/SqlSessionTemplate',
            'org/mybatis/spring/SqlSessionTemplate$SqlSessionInterceptor',
            'org/mybatis/spring/SqlSessionUtils',
            'org/apache/ibatis/session/defaults/DefaultSqlSessionFactory',
            'org/apache/ibatis/session/defaults/DefaultSqlSession',
            'org/apache/ibatis/session/Configuration',
            'org/apache/ibatis/reflection/factory/DefaultObjectFactory',
            'org/apache/ibatis/reflection/wrapper/DefaultObjectWrapperFactory',
            'org/apache/ibatis/reflection/MetaObject',
            'org/apache/ibatis/reflection/wrapper/BeanWrapper',
            'org/apache/ibatis/reflection/DefaultReflectorFactory',
            'org/apache/ibatis/reflection/Reflector',
            'org/apache/ibatis/executor/resultset/DefaultResultSetHandler',
            'org/apache/ibatis/executor/resultset/ResultSetWrapper',
            'org/apache/ibatis/executor/BaseExecutor',
            'org/apache/ibatis/cache/impl/PerpetualCache',
            'org/apache/ibatis/type/BaseTypeHandler'}
        require(all(any(r['seq']<end['seq'] for r in classes[owner]) for owner in required_armed),
                'SQL fixed corridor instrumentation missing')
        required_used=required_armed-{
            'org/mybatis/spring/SqlSessionUtils','org/apache/ibatis/session/Configuration',
            'org/apache/ibatis/reflection/MetaObject','org/apache/ibatis/reflection/wrapper/BeanWrapper',
            'org/apache/ibatis/executor/resultset/ResultSetWrapper',
            'org/apache/ibatis/executor/BaseExecutor','org/apache/ibatis/type/BaseTypeHandler'}
        require(required_used<=set(end['used_classes'])
                and bool({'org/apache/ibatis/executor/SimpleExecutor','org/apache/ibatis/executor/ReuseExecutor'}&set(end['used_classes']))
                and bool({'org/apache/ibatis/session/Configuration','com/baomidou/mybatisplus/core/MybatisConfiguration'}&set(end['used_classes'])),
                'SQL actual implementation witness set incomplete')
        require(begin['eligible'] and not end['transactional'] and end['closed']
                and end['selects'] == end['mapper_invokers'] == 1,
                'SQL ownership runtime prerequisites absent')
        for name, count in [('select',1), ('close',1), ('transaction',1),
                            ('mapper-invoker',1), ('meta',end['meta']),
                            ('handler',end['handlers']), ('reflector',end['reflectors']),
                            ('invoker',end['invokers'])]:
            selected = [r for r in events if r['kind'] == 'sql-locality-'+name]
            require(len(selected) == count and (count > 0 or name == 'invoker')
                    and all(r.get('eligible',True) for r in selected),
                    'SQL ownership necessary '+name+' witness absent/repeated/invalid')
        select = next(r for r in events if r['kind'] == 'sql-locality-select')
        close = next(r for r in events if r['kind'] == 'sql-locality-close')
        transaction = next(r for r in events if r['kind'] == 'sql-locality-transaction')
        require(select['seq'] < transaction['seq'] < close['seq'] < end['seq']
                and select['session'] == transaction['session'] == close['session']
                and close['closed'] and not transaction['transactional'],
                'SQL session retention/close proof differs')
        for owner, digest in end['used_classes'].items():
            require(cfg['class_sha256'].get(owner) == digest
                    and any(r['seq'] < end['seq'] for r in classes[owner]),
                    'SQL runtime entry point not armed')
        graph = {node['owner']:node for node in end['objects']}
        births = [r for r in events if r['kind'] == 'sql-locality-birth']
        born = {r['object']:r for r in births}
        require(len(born) == len(births) and len(graph) == len(end['objects'])
                and end['body'] == exit['result']['object'] in graph and set(graph)<=set(born),
                'SQL result graph/birth identities differ')
        source = sources[begin['call_id']]
        require(len(source) == 1 and all(f['owner'] in graph for f in source[0]['fields']),
                'SQL result ownership omits actual source fields')
        callbacks = [r for r in events if r['kind']=='sql-locality-callback-begin']
        completed = [r for r in events if r['kind']=='sql-locality-callback-end']
        by_id = {r['callback_id']:r for r in completed}
        require(len(callbacks)==len(completed)==len(by_id)==end['callbacks'],
                'SQL preallocation callback completion missing/repeated')
        for callback in callbacks:
            owner='com/baomidou/mybatisplus/extension/plugins/MybatisPlusInterceptor'
            require(callback['site'] in cfg['instrumented_callsites'][owner]
                    and any(r['seq']<callback['seq'] for r in classes[owner])
                    and callback['callback_id'] in by_id
                    and callback['seq']<by_id[callback['callback_id']]['seq']
                    <min(born[node]['seq'] for node in graph),
                    'SQL callback not closed before final graph allocation')
        cb_starts={r['callback_id']:r for r in callbacks}
        for event in events:
            if 'preallocation_callback' not in event:continue
            cb=event['preallocation_callback']
            require(cb in cb_starts and cb_starts[cb]['seq']<event['seq']<by_id[cb]['seq'],
                    'Opaque SQL callback effect outside its actual interval')
        handlers = [r for r in events if r['kind']=='sql-locality-result-begin']
        returned = [r for r in events if r['kind']=='sql-locality-result-end']
        states = [r for r in events if r['kind']=='sql-locality-handler-state']
        require(len(handlers)==len(returned)==len(states)==end['result_handlers']>0
                and len({r['handler'] for r in handlers})==len(handlers),
                'SQL result handler coverage missing/repeated')
        require(any(r['handler']==end['result_handler'] and r['body']==end['body'] for r in returned),
                'SQL result list not returned by actual handler')
        for handler in handlers:
            exits=[r for r in returned if r['handler']==handler['handler']]
            cleared=[r for r in states if r['handler']==handler['handler']]
            require(handler['eligible'] and len(exits)==len(cleared)==1 and cleared[0]['empty']
                    and handler['seq']<exits[0]['seq']<close['seq']<cleared[0]['seq']<end['seq'],
                    'SQL retained result-handler state not excluded')
        for owner, node in graph.items():
            require(owner in born and select['seq'] < born[owner]['seq'] < close['seq']
                    and born[owner]['type'] == node['type']
                    and all(child in graph for child in node['references']),
                    'SQL allocation coverage/reference closure differs')
            require((node['type'] == 'java/util/Date' and born[owner]['birth_kind'] == 'date-handler')
                    or (born[owner]['birth_kind'] == 'factory'
                        and (node['type'] == 'java/util/ArrayList' or node['type'] in cfg['beans'])),
                    'SQL initializer/model differs')
        todo, seen = [end['body']], set()
        while todo:
            owner = todo.pop()
            if owner not in seen:
                seen.add(owner); todo.extend(graph[owner]['references'])
        require(seen == set(graph), 'SQL ownership contains disconnected graph nodes')
        result[begin['call_id']] = {'objects':graph, 'body':end['body'],
            'births':{owner:born[owner]['seq'] for owner in graph},
            'ownership_id':('sql',oid), 'seq':end['seq']}
    return result
