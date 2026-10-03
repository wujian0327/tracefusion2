"""Read/compute -> explicit JSON summary -> accepted stdout bytes.

No oracle or stdout reads during inference. Address/order/version matching is
required, with byte/value checks as consistency evidence, never as identity.
Contract: one execution context, observed roots are the only output-field
writers; format_json is the only JSON-buffer writer; no concurrent mutation,
aliased source/output buffers, or mutation during immutable handoffs. This is
not a general memory-lifetime tracker or an analysis of libc internals.
"""
import copy

import read_boundaries as read
from hybrid_model import require
from language_adapters import get_adapter

FORMAT_ENTER,FORMAT_EXIT,WRITE_ENTER,WRITE_EXIT=range(6,10)


def encode_u32(value):
    require(isinstance(value,int) and 0<=value<=0xffffffff,'Not an unsigned 32-bit value')
    return ('{"value":%d}\n'%value).encode('ascii')


def bind(events,plans,config,runtime):
    try:
        require(config['json_output']['model']=='json-u32-value-v1' and config['json_output']['capacity']==32 and config['json_output']['fd']==1,'Unsupported JSON summary')
        require(events and len(events)<=20000,'Empty or oversized output history')
        rows=sorted(events,key=lambda e:e['observation_sequence'])
        require([e['observation_sequence'] for e in rows]==list(range(len(rows))),'Missing or duplicate output sequence')
        require(rows[0]['kind']==read.SCOPE_ENTER and rows[-1]['kind']==read.SCOPE_EXIT,'Missing output scope')
        require(len({e['pid_tid'] for e in rows})==1,'Multiple output execution contexts')
        get_adapter(config).context.validate(rows,read.core.model.REGS)
        require(all(a['timestamp']<=b['timestamp'] for a,b in zip(rows,rows[1:])),'Non-monotonic output history')
        require(all(e['kind'] in range(10) for e in rows),'Unknown output event')
        projected=[dict(e,observation_sequence=i) for i,e in enumerate(e for e in rows if e['kind']<6)]
        inferred=read.bind(projected,plans,config,runtime)
        require(not inferred['issues'],'Read/compute binding failed: '+str(inferred['issues']))
        # Restore external-read sequence positions to the full capture stream.
        positions=[e['observation_sequence'] for e in rows if e['kind']<6]
        for op in inferred['read_operations']:
            op['entry_sequence']=positions[op['entry_sequence']];op['exit_sequence']=positions[op['exit_sequence']]
        results={(r['pid_tid'],r['call_id']):r for r in inferred['results']}
        instructions={(fid,n['offset']):n for fid,p in enumerate(plans) for n in p['instructions']}
        field=get_adapter(config).layout(config,'output').field(config['sink_field'])
        active=None;latest=None;formatting=None;writing=None;current_format=None
        formats=[];writes=[];sinks=[];read_pending=False
        for e in rows[1:-1]:
            kind=e['kind']
            if kind==read.READ_ENTER:
                require(formatting is None and writing is None,'Read overlaps output operation');read_pending=True
            elif kind==read.READ_EXIT:
                read_pending=False
                if e['returned']>0:
                    start,end=e['buffer_addr'],e['buffer_addr']+e['returned']
                    require(latest is None or end<=latest['address'] or start>=latest['address']+4,'Read aliases computed output')
                    require(current_format is None or end<=current_format['buffer_addr'] or start>=current_format['buffer_addr']+32,'Read aliases JSON buffer')
            elif kind==read.INSTRUCTION:
                require(formatting is None and writing is None,'Computation overlaps output operation')
                if active is None:
                    active=(e['pid_tid'],e['call_id']);latest=None
                    require(current_format is None or e['dst_addr']+get_adapter(config).layout(config,'output').size<=current_format['buffer_addr'] or e['dst_addr']>=current_format['buffer_addr']+32,'Compute aliases JSON buffer')
                if instructions[e['function'],e['offset']]['op']=='ret' and e['depth']==1:
                    r=results[active]
                    latest=dict(result=r,address=e['dst_addr']+field.offset,value=r['value'],sequence=e['observation_sequence'])
                    active=None
            elif kind==FORMAT_ENTER:
                require(active is None and not read_pending and formatting is None and writing is None,'Overlapping serializer invocation')
                require(e['io_id']==len(formats)+1 and e['requested']==32,'Missing or unsupported serializer invocation')
                require(latest is not None and e['src_addr']==latest['address'],'Serializer input has no current observed compute version')
                require(e['source_error']==0 and e['outputs'][0]==latest['value'],'Serializer input snapshot failed or output changed')
                require(0<e['buffer_addr']<2**64-32,'Invalid JSON buffer')
                require(e['buffer_addr']+32<=e['src_addr'] or e['buffer_addr']>=e['src_addr']+4,'JSON buffer aliases serializer input')
                formatting=(e,latest);current_format=None
            elif kind==FORMAT_EXIT:
                require(formatting is not None,'Unpaired serializer return')
                entry,origin=formatting
                require(all(e[k]==entry[k] for k in ('io_id','src_addr','buffer_addr','requested','pid_tid')),'Serializer return contradicts entry')
                require(e['source_error']==e['read_error']==0 and e['outputs'][0]==origin['value'],'Serializer snapshot failure')
                payload=encode_u32(origin['value'])
                require(e['returned']==len(payload) and len(e['read_data'])==32 and bytes(e['read_data'][:len(payload)+1])==payload+b'\0','JSON bytes contradict explicit serializer model')
                r=origin['result'];fid='%s:json:%s'%(e['pid_tid'],e['io_id'])
                graph=copy.deepcopy(r['dependency_graph'])
                previous=[n['id'] for n in graph['nodes'] if n.get('kind')=='sink']
                require(len(previous)==1,'Unknown compute sink graph')
                number_start=len(b'{"value":');number_length=len(str(origin['value']))
                graph['nodes'].append(dict(id=fid,kind='json-number-range',field='$.value',offset=number_start,length=number_length,model='json-u32-value-v1'))
                graph['edges'].append(dict(source=previous[0],target=fid,kind='serialization-summary',evidence='explicit model plus entry/exit observations'))
                current_format=dict(id=fid,format_id=e['io_id'],call_id=r['call_id'],buffer_addr=e['buffer_addr'],value=origin['value'],data=list(payload),
                    entry_sequence=entry['observation_sequence'],exit_sequence=e['observation_sequence'],number_range=dict(offset=number_start,length=number_length),
                    external_sources=copy.deepcopy(r['external_sources']),dependency_graph=graph)
                formats.append(current_format);formatting=None
            elif kind==WRITE_ENTER:
                require(active is None and not read_pending and formatting is None and writing is None,'Overlapping write')
                require(e['io_id']==len(writes)+1,'Missing or repeated write attempt')
                require(current_format is not None and e['buffer_addr']==current_format['buffer_addr'],'Write buffer has no observed JSON version')
                require(e['requested']==len(current_format['data']) and e['read_error']==0 and len(e['read_data'])==32,'Write snapshot failed or unsupported output range')
                require(e['read_data'][:e['requested']]==current_format['data'],'JSON buffer changed after serialization')
                require(e['fd'] in (1,-1),'Unsupported output descriptor')
                writing=(e,current_format)
            elif kind==WRITE_EXIT:
                require(writing is not None,'Unpaired write return')
                entry,version=writing
                require(all(e[k]==entry[k] for k in ('io_id','fd','buffer_addr','requested','pid_tid')),'Write return contradicts entry')
                require(-4095<=e['returned']<=e['requested'],'Invalid write return')
                require(e['returned']<=0 or e['returned']==e['requested'],'Partial write unsupported; no complete JSON field claim')
                require(e['fd']==1 or e['returned']<0,'Invalid descriptor reported output success')
                accepted=e['returned']>0
                op=dict(write_id=e['io_id'],format_id=version['format_id'],call_id=version['call_id'],fd=e['fd'],returned=e['returned'],requested=e['requested'],
                        data=version['data'] if accepted else [],status='accepted' if accepted else 'not-written',entry_sequence=entry['observation_sequence'],exit_sequence=e['observation_sequence'])
                writes.append(op)
                if accepted:
                    graph=copy.deepcopy(version['dependency_graph']);wid='%s:write:%s'%(e['pid_tid'],e['io_id'])
                    graph['nodes'].append(dict(id=wid,kind='stdout-json-field',fd=e['fd'],field='$.value',write_id=e['io_id'],**version['number_range']))
                    graph['edges'].append(dict(source=version['id'],target=wid,kind='accepted-write',evidence='observed buffer identity, bytes and successful return'))
                    sinks.append(dict(**op,field='$.value',value=version['value'],external_sources=version['external_sources'],dependency_graph=graph))
                writing=None
            else:
                raise ValueError('Unexpected scope or descriptor lifecycle event')
        require(active is None and not read_pending and formatting is None and writing is None,'Incomplete output history')
        require(formats and writes,'No JSON output operations observed')
        inferred.update(formats=formats,write_operations=writes,output_fields=sinks,output_issues=[],
            stdout_bytes=[byte for op in writes for byte in op['data']],
            scope='Observed pread + executed fixed fields + explicit JSON u32 summary + successful stdout write; no generic serializer or network delivery claim')
        return inferred
    except (ValueError,KeyError,IndexError,TypeError,StopIteration) as exc:
        return dict(results=[],read_operations=[],issues=[dict(error=str(exc))],boundary_issues=[],output_issues=[dict(error=str(exc))],formats=[],write_operations=[],output_fields=[],stdout_bytes=[],oracle_used_for_inference=False)


def evaluate(inferred,oracle,stats,plans):
    score=read.evaluate(inferred,oracle['computations'],stats,plans)
    computations={r['sequence']:r for r in oracle['computations']}
    outputs={r['write_id']:r for r in inferred['output_fields']}
    writes={r['write_id']:r for r in inferred['write_operations']}
    checks=[];tp=fp=fn=0;expected_stdout=[]
    def sources(items):return {(s['io_id'],s['file_name'],s['file_offset'],s['length']) for s in items}
    for truth in oracle['writes']:
        r=computations[truth['call_id']];payload=encode_u32(r['expected_value']);success=truth['fd']==1
        if success:expected_stdout.extend(payload)
        expected=sources(r['expected_external_sources']) if success else set()
        output=outputs.get(truth['write_id'],{});observed=sources(output.get('external_sources',[]))
        tp+=len(expected&observed);fp+=len(observed-expected);fn+=len(expected-observed)
        op=writes.get(truth['write_id'],{})
        passed=all(op.get(k)==truth[k] for k in ('write_id','format_id','call_id','fd')) and op.get('returned')==(len(payload) if success else -9)
        passed=passed and bool(output)==success and expected==observed
        if success:passed=passed and output.get('value')==r['expected_value'] and output.get('data')==list(payload)
        checks.append(dict(write_id=truth['write_id'],passed=passed,expected_emitted=success,expected_sources=sorted(expected),observed_sources=sorted(observed)))
    expected_ids={r['write_id'] for r in oracle['writes']}
    extras=[r for r in inferred['output_fields'] if r['write_id'] not in expected_ids]
    fp+=sum(len(r['external_sources']) for r in extras)
    stdout_match=inferred['stdout_bytes']==oracle['stdout_bytes']==expected_stdout
    score.update(output_checks=checks,output_source_relations=dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None),
        formats=len(inferred['formats']),expected_formats=oracle['format_count'],writes=len(writes),expected_writes=len(oracle['writes']),
        emitted_json_fields=len(outputs),stdout_bytes_match=stdout_match,
        scope='Fixture read/compute sources and emitted JSON $.value origins, with explicit serializer summary; not generic JSON or full graph-edge accuracy')
    score['passed']=score['passed'] and bool(checks) and all(c['passed'] for c in checks) and not extras and len(writes)==len(oracle['writes']) and len(inferred['formats'])==oracle['format_count'] and stdout_match and not inferred['output_issues']
    return score
