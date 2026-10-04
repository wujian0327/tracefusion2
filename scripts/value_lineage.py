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
        # This pilot's root has a fixed operation sequence; reject missing or
        # extra calls, including a completely absent unused source call.
        expected = plan['event_order']
        require([e['site'] for e in events] == expected, 'Missing, extra or reordered operation')
        nodes, edges, stack, values = {}, [], [], {}
        counts = {'source':0,'concat':0,'json':0}
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
            nodes[nid] = node
        require(not stack and counts == {'source':3,'concat':1,'json':1} and sink, 'Incomplete workload')
        keep = backward_nodes(edges, [sink], {'data'})
        origins = sorted(n for n in keep if nodes[n]['kind'] == 'source')
        return {'status':'resolved_under_configured_summaries','sources':origins,
                'contributing_reads':[nodes[n] for n in origins],
                'noncontributing_reads':[n for n in nodes if nodes[n]['kind']=='source' and n not in keep],
                'graph':{'nodes':[nodes[n] for n in sorted(keep)],'edges':[e for e in edges if e['source'] in keep and e['target'] in keep]},
                'observed_graph':{'nodes':list(nodes.values()),'edges':edges},
                'scope':'Explicit data dependencies; source API returns, immutable strings, configured concat and JSON summaries; not arbitrary Go instruction replay'}
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        return {'status':'unknown','reason':str(exc)}
