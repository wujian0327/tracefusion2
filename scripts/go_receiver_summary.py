"""Relative receiver access summaries; never a whole-callee no-write proof.

Distinguishes passing the receiver address from passing values loaded through
it. The latter remain alias obligations. No business function is whitelisted.
"""
from go_object_graph import analyze, terminals


def summarize_receiver(rows, function, receiver='AX'):
    graph=analyze(rows,function,stack_policy='assume_private',allow_indirect_calls=True)
    tags={k:set() for k in graph['nodes']}
    tags['entry:'+receiver].add('receiver')
    tags['entry:SP'].add('local_frame')
    tags['entry:BP'].add('local_frame')
    changed=True
    while changed:
        changed=False
        for key,node in graph['nodes'].items():
            inferred=set()
            if node['kind'] in ('copy','value_transform','address'):
                for src in node['inputs']:
                    inferred.update(tags[src])
            elif node['kind']=='heap_load':
                address_tags=set().union(*(tags[k] for k in node['address_inputs']))
                if address_tags & {'receiver','receiver_contents'}:
                    inferred.add('receiver_contents')
                if 'local_frame' in address_tags:
                    inferred.add('unmodeled_frame_load')
            if not inferred <= tags[key]:
                tags[key].update(inferred); changed=True

    def roots_tagged(roots,tag):
        return sorted(k for k in roots if tag in tags[k])

    def load_chain(roots):
        # Relative pointer chase, not a resolved dynamic target or alias proof.
        offsets, seen = [], set()
        while True:
            ids=terminals(graph,roots)
            if len(ids)!=1 or ids[0] in seen:
                return None
            key=ids[0]; seen.add(key)
            if key=='entry:'+receiver:
                return list(reversed(offsets))
            node=graph['nodes'][key]
            if node['kind']!='heap_load' or node['memory']['index'] is not None:
                return None
            offsets.append(node['memory']['offset'])
            roots=node['base_inputs']

    reads, writes, escapes, forwards, issues = [], [], [], [], []
    for key,node in graph['nodes'].items():
        if node['kind']=='heap_load' and roots_tagged(node['address_inputs'],'receiver'):
            mem=node['memory']
            width={'MOVQ':8,'MOVL':4,'MOVUPS':16}.get(node['asm'].split()[0])
            if roots_tagged(node['index_inputs'],'receiver') or mem['index'] is not None or width is None:
                issues.append(dict(address=node['address'],reason='Indexed/unsupported receiver read'))
            else:
                reads.append(dict(address=node['address'],offset=mem['offset'],width=width,node=key))
        if node['kind'] in ('address','value_transform') and roots_tagged(node['inputs'],'receiver'):
            issues.append(dict(address=node['address'],reason='Receiver pointer arithmetic/partial transform needs a richer domain'))
    for store in graph['stores']:
        if roots_tagged(store['address_inputs'],'receiver'):
            writes.append(dict(address=store['address'],memory=store['memory']))
        if roots_tagged(store['value_inputs'],'receiver'):
            escapes.append(dict(address=store['address'],via='indirect_store'))
        if roots_tagged(store['address_inputs'],'receiver_contents'):
            forwards.append(dict(address=store['address'],via='write_through_loaded_pointer'))
        if roots_tagged(store['address_inputs'],'local_frame'):
            issues.append(dict(address=store['address'],reason='Indirect local-frame write may corrupt saved receiver'))
        if roots_tagged(store['value_inputs'],'local_frame'):
            issues.append(dict(address=store['address'],reason='Local-frame address escapes through a store'))
    for call in graph['calls']:
        if roots_tagged(call['target_inputs'],'receiver'):
            escapes.append(dict(address=call['address'],via='indirect_call_target'))
        if roots_tagged(call['target_inputs'],'local_frame'):
            issues.append(dict(address=call['address'],reason='Local-frame alias used as call target'))
        regs=call['arguments']
        stack=call['potential_stack_arguments']
        for mapping,via in ((regs,'register'),(stack,'potential_stack_argument')):
            for location,roots in mapping.items():
                if roots_tagged(roots,'receiver'):
                    escapes.append(dict(address=call['address'],callee=call['callee'],via=via,location=location))
                if roots_tagged(roots,'receiver_contents'):
                    forwards.append(dict(address=call['address'],callee=call['callee'],via=via,location=location))
                if roots_tagged(roots,'local_frame') or roots_tagged(roots,'unmodeled_frame_load'):
                    issues.append(dict(address=call['address'],reason='Local-frame alias supplied to a call'))
    for ret in graph['returns']:
        for location,roots in ret['registers'].items():
            if roots_tagged(roots,'receiver'):
                escapes.append(dict(address=ret['address'],via='return',location=location))
    direct_read_only=not writes and not escapes and not issues
    return dict(schema=1,function=function,receiver_register=receiver,
        status='conditional_receiver_access_summary' if direct_read_only else 'receiver_summary_rejected',
        direct_receiver_reads=reads,direct_receiver_writes=writes,receiver_address_escapes=escapes,
        loaded_values_forwarded=forwards,unsupported_conditions=issues,
        direct_receiver_read_only_under_conditions=direct_read_only,
        transitive_no_write_proved=False,may_preserve_caller_spills=False,
        required_conditions=[
            'Normal fixed Go ABI and compiler stack layout; private local spills are not accessed through hidden aliases.',
            'Other arguments and values loaded from the receiver must be checked for aliases back to the caller frame.',
            'No receiver argument is introduced through an unmodeled alternate entry or closure context.',
            'Unknown downstream call results/effects are not a proof of transitive memory separation.'],
        indirect_calls=[dict(address=c['address'],target_register=c['callee'],
            target_load_offsets=load_chain(c['target_inputs']),
            receiver_related_register_loads={r:load_chain(roots) for r,roots in c['arguments'].items()
                                            if roots_tagged(roots,'receiver_contents')})
            for c in graph['calls'] if c['indirect']],
        calls=len(graph['calls']),body_instructions=graph['instructions'],frame_size=graph['frame_size'])
