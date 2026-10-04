"""Bounded immutable-value lineage. Receives normalized evidence, not Go registers.

Source return values and concat/JSON operations are explicitly summarized.
No oracle, fixture names or source-value uniqueness is used to assign origins.
"""
import hashlib
import json
from lineage_graph import backward_nodes


def require(ok, message):
    if not ok: raise ValueError(message)


def raw(value):
    return bytes.fromhex(value['hex'])


def byte_origins(nodes, mappings, sink, length):
    """Back-propagate half-open byte intervals through declared value mappings.

    Each mapping is (parent, output_start, output_end, parent_start).
    The sink is the decoded JSON string, not its escaped wire representation.
    """
    pending=[(sink,0,length)];seen=set();origins={}
    while pending:
        node,start,end=pending.pop()
        if (node,start,end) in seen:continue
        seen.add((node,start,end))
        if nodes[node]['kind']=='source':
            require(0<=start<end<=nodes[node]['length'], 'Source byte range outside definition')
            origins.setdefault(node,[]).append([start,end]);continue
        covered=0
        for parent,out_start,out_end,parent_start in mappings.get(node,[]):
            lo,hi=max(start,out_start),min(end,out_end)
            if lo<hi:
                covered+=hi-lo
                pending.append((parent,parent_start+lo-out_start,parent_start+hi-out_start))
        require(covered==end-start, 'Incomplete byte mapping')
    result=[]
    for source,ranges in sorted(origins.items()):
        merged=[]
        for lo,hi in sorted(ranges):
            if merged and lo<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],hi)
            else:merged.append([lo,hi])
        result.append({'source':source,'ranges':merged})
    return result


def infer(document, plan):
    try:
        require(not document.get('capture_errors') and document.get('returncode') == 0, 'Capture failed')
        require(document['binary_sha256'] == plan['binary_sha256'], 'Binary hash mismatch')
        events = sorted(document['events'], key=lambda e: (e['timestamp'], e['sequence']))
        require(events, 'No events')
        stats = document['stats']
        require(stats['submitted'] == len(events) and not any(stats[k] for k in ('submit_errors','read_errors','lost')), 'Incomplete transport')
        require(len({e['sequence'] for e in events}) == len(events), 'Duplicate sequence')
        require(len({(e['pid'],e['g']) for e in events}) == 1 and all(e['g'] for e in events), 'Requires one execution goroutine')
        sites = {s['id']:s for s in plan['sites']}
        # Declared traces with optional copy/trim. No selector or
        # oracle is supplied to inference. Other event omissions are rejected.
        expected = plan.get('allowed_event_orders', [plan['event_order']])
        require([e['site'] for e in events] in expected, 'Missing, extra or reordered operation')
        nodes, edges, stack, values = {}, [], [], {}
        counts = {'source':0,'copy':0,'trim':0,'concat':0,'json':0}
        mappings={};sink_length=0
        sink = None
        def add_value(key, node, data):
            require(key not in values, 'Aliased/reused value identity unsupported')
            values[key] = (node, data)
        def lookup(value):
            require(value['key'] in values, 'Operand has no observed definition')
            node, data = values[value['key']]
            require(data == raw(value), 'Value changed after its observed definition')
            return node
        for event in events:
            spec = sites[event['site']]
            require(event['op'] == spec['op'] and event['phase'] == spec['phase'], 'Site contract mismatch')
            if event['phase'] == 'pre':
                stack.append(event)
                continue
            require(stack and sites[stack[-1]['site']]['pair'] == spec['pair'], 'Unpaired operation')
            before = stack.pop()
            op = event['op']
            if op == 'scope': continue
            counts[op] += 1
            nid = op+':'+str(counts[op])
            node = {'id':nid, 'kind':op, 'entry_sequence':before['sequence'], 'exit_sequence':event['sequence']}
            if op == 'source':
                value = event['values']['value']
                data = raw(value)
                require(1 < len(data) <= 128, 'Source strings must contain 2..128 bytes')
                node.update(path=raw(before['values']['path']).decode(), length=len(data), sha256=hashlib.sha256(data).hexdigest())
                add_value(value['key'], nid, data)
            elif op == 'copy':
                source = before['values']['value']
                parent = lookup(source)
                value = event['values']['value']
                require(raw(value) == raw(source), 'Copy result contradicts summary')
                # A supported nonempty Clone must define distinct storage.
                add_value(value['key'], nid, raw(value))
                node.update(operation='string-clone', input_identity=source['key'],
                            output_identity=value['key'], output_length=len(raw(value)))
                edges.append({'source':parent,'target':nid,'kind':'data','role':'input'})
                mappings[nid]=[(parent,0,len(raw(value)),0)]
            elif op == 'trim':
                source=before['values']['value'];prefix=raw(before['values']['prefix'])
                parent=lookup(source);data=raw(source);value=event['values']['value']
                require(prefix==b'SA', 'Only the configured constant prefix SA is supported')
                require(data.startswith(prefix) and len(data)>len(prefix), 'Trim requires a matching prefix and nonempty result')
                offset=len(prefix)
                require(raw(value)==data[offset:], 'Trim result contradicts summary')
                # Selected Go implementation returns a view into the input.
                pointer,length=source['key'].split(':')
                require(int(length)==len(data), 'Trim input identity length mismatch')
                expected_key=f'{int(pointer,16)+offset:x}:{len(data)-offset}'
                require(value['key']==expected_key, 'Trim result is not the expected input subrange')
                add_value(value['key'],nid,raw(value))
                node.update(operation='trim-prefix',input_identity=source['key'],output_identity=value['key'],
                            input_byte_range=[offset,len(data)],output_length=len(raw(value)),prefix_hex=prefix.hex())
                edges.append({'source':parent,'target':nid,'kind':'data','role':'input'})
                mappings[nid]=[(parent,0,len(raw(value)),offset)]
            elif op == 'concat':
                left, right = before['values']['left'], before['values']['right']
                parents = (lookup(left), lookup(right))
                value = event['values']['value']
                require(raw(value) == raw(left)+raw(right), 'Concat result contradicts summary')
                node['operation'] = 'concat'
                node['output_length'] = len(raw(value))
                add_value(value['key'], nid, raw(value))
                for role,parent in zip(('left','right'),parents):
                    edges.append({'source':parent,'target':nid,'kind':'data','role':role})
                split=len(raw(left))
                mappings[nid]=[(parents[0],0,split,0),(parents[1],split,len(raw(value)),0)]
            elif op == 'json':
                value = before['values']['value']
                parent = lookup(value)
                output = json.loads(raw(event['values']['json']))
                require(isinstance(output,dict) and set(output) == {'result'}, 'JSON schema outside summary')
                require(isinstance(output['result'], str) and output['result'].encode() == raw(value), 'JSON result contradicts input')
                node['operation'] = 'json-string-field'
                edges.append({'source':parent,'target':nid,'kind':'data','role':'value'})
                sink = 'output:result'
                nodes[sink] = {'id':sink,'kind':'output-field','field':'result','value':output['result']}
                edges.append({'source':nid,'target':sink,'kind':'data','role':'result'})
                sink_length=len(raw(value))
                mappings[nid]=[(parent,0,sink_length,0)]
                mappings[sink]=[(nid,0,sink_length,0)]
            nodes[nid] = node
        require(not stack and counts['source']==3 and counts['concat']==1 and counts['json']==1
                and counts['copy'] in (0,1) and counts['trim'] in (0,1) and sink, 'Incomplete workload')
        keep = backward_nodes(edges, [sink], {'data'})
        origins = sorted(n for n in keep if nodes[n]['kind'] == 'source')
        result = {'status':'resolved_under_configured_summaries','sources':origins,
                'contributing_reads':[nodes[n] for n in origins],
                'noncontributing_reads':[n for n in nodes if nodes[n]['kind']=='source' and n not in keep],
                'graph':{'nodes':[nodes[n] for n in sorted(keep)],'edges':[e for e in edges if e['source'] in keep and e['target'] in keep]},
                'observed_graph':{'nodes':list(nodes.values()),'edges':edges},
                'scope':('Explicit data dependencies; source API returns, immutable strings, configured concat and JSON summaries; not arbitrary Go instruction replay'
                         if not counts['copy'] else 'Explicit data dependencies; source API returns, immutable strings, configured copy, concat and JSON summaries; not arbitrary Go instruction replay')}
        if counts['trim']:
            result['source_byte_ranges']=byte_origins(nodes,mappings,sink,sink_length)
            result['byte_range_scope']='Half-open UTF-8 byte ranges in source returns contributing to the decoded result string; excludes control/selection dependencies'
            result['scope']='Explicit data dependencies under configured source, copy, trim, concat and JSON summaries; not arbitrary Go instruction replay'
        return result
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        return {'status':'unknown','reason':str(exc)}
