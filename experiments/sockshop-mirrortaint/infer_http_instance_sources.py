#!/usr/bin/env python3
"""Bounded HTTP String-property bridge, followed by readonly receiver aliases.

Match only explicit message identity. Values validate an already selected edge;
they never select a request, field, or source. No fixture/oracle inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path

from flowdist_runtime_comparison import events
from infer_boundary_sources import infer as infer_boundary
from service_model import disassemble, methods


def audit_properties(orders, shipping):
    hashes = {}
    for capture, role in ((orders, 'orders'), (shipping, 'shipping')):
        owner = 'works/weave/socks/' + role + '/entities/Shipment'
        file = capture / (owner.replace('/', '_') + '.original.class')
        text = disassemble(file)
        verbose = disassemble(file, True)
        if 'com/fasterxml/jackson/annotation/' in verbose:
            raise ValueError('Custom Jackson annotations are outside the property model')
        bodies = methods(text, owner)
        for prop in ('id', 'name'):
            suffix = prop.capitalize()
            getter = bodies['get' + suffix + '()Ljava/lang/String;']
            setter = bodies['set' + suffix + '(Ljava/lang/String;)V']
            if ([r['op'] for r in getter] != ['aload_0', 'getfield', 'areturn'] or
                getter[1]['comment'] != 'Field ' + prop + ':Ljava/lang/String;' or
                [r['op'] for r in setter] != ['aload_0', 'aload_1', 'putfield', 'return'] or
                setter[2]['comment'] != 'Field ' + prop + ':Ljava/lang/String;'):
                raise ValueError('Unsupported Shipment property accessor: ' + role + '/' + prop)
        hashes[role] = hashlib.sha256(file.read_bytes()).hexdigest()
    return {'properties': ['id', 'name'], 'class_sha256': hashes,
            'scope': 'default String DTO properties, same-message request bridge, readonly Shipping return',
            'custom_serializers_supported': False, 'upstream_customer_to_shipment_modelled': False}


def reconstruct(sender, receiver, boundary, properties):
    sends = {}
    rpc_entries = {r['rpc']: r for r in sender if r['kind'] == 'rpc-enter'}
    rpc_exits = {r['rpc']: r for r in sender if r['kind'] == 'rpc-exit'}
    for row in sender:
        if row['kind'] != 'http-send':
            continue
        message = row['rpc']
        if message in sends:
            raise ValueError('Duplicate HTTP send identity')
        if (row['uri'] != 'http://shipping/shipping' or row['method'] != 'POST' or
            message not in rpc_entries or row['request_fields'] != rpc_entries[message]['request_fields']):
            raise ValueError('Invalid HTTP send/RPC observation')
        sends[message] = row
    received = {}
    receiver_messages = set()
    for row in receiver:
        if row['kind'] != 'source' or row['boundary'] != 'http-request-body':
            continue
        message = row.get('message_id')
        if message is not None:
            if message in receiver_messages:
                raise ValueError('Duplicate HTTP receive identity')
            receiver_messages.add(message)
        if row['instance'] in received:
            raise ValueError('Duplicate receiver source instance')
        received[row['instance']] = row
    answers = []
    for answer in boundary['answers']:
        if answer['sink'] != 'return' or '.postShipping(' not in answer['method']:
            continue
        fields = []
        for field in answer['fields']:
            result = {'path': field['path'], 'status': 'unknown', 'sources': None, 'path_evidence': None}
            if field['status'] == 'resolved' and len(field['sources']) == 1:
                instance, path = field['sources'][0]
                incoming = received[instance]
                message = incoming.get('message_id')
                send = sends.get(message)
                prop = path.removeprefix('source#')
                if send is not None and prop in properties:
                    source_path = 'request#body#' + prop
                    candidates = [f for f in send['request_fields'] if f['path'] == source_path]
                    inputs = [f for f in incoming['fields'] if f['path'] == path]
                    if len(candidates) == len(inputs) == 1:
                        source, target = candidates[0], inputs[0]
                        # Identity join and property selection happened above, before this check.
                        if (source['observed'].get('value') is not None and
                            source['observed'].get('value') == target['observed'].get('value') and
                            source['observed'].get('value') == field['observed'].get('value')):
                            result.update(status='resolved', sources=[['orders', message, source_path]],
                                path_evidence=[{'service': 'orders', 'seq': send['seq'], 'owner': source['owner'],
                                                'field': source['field'], 'version': source['version']},
                                               {'service': 'shipping', 'seq': incoming['seq'], 'instance': instance,
                                                'owner': target['owner'], 'field': target['field'], 'version': target['version']},
                                               {'service': 'shipping', 'seq': answer['seq'], 'frame': answer['frame'],
                                                'owner': field['owner'], 'field': field['field'], 'version': field['version']}])
            fields.append(result)
        answers.append({'frame': answer['frame'], 'seq': answer['seq'], 'trace_id': answer['trace_id'], 'fields': fields})
    return {'engine': 'TraceFusion explicit HTTP instance/String-property model plus receiver aliases',
            'answers': answers, 'http_sends': len(sends), 'http_receives': len(received),
            'matched_messages': len(set(sends) & receiver_messages),
            'unmatched_sends': sorted(set(sends) - receiver_messages),
            'unmatched_receives': sorted(receiver_messages - set(sends)),
            'completed_client_rpcs': sum(message in rpc_exits for message in sends),
            'contracts_consumed': False, 'FlowDist_consumed': False,
            'matching_uses_values': False, 'matching_uses_trace_ids': False}


def infer(run):
    orders = run / 'tracefusion-events'
    shipping = run / 'boundary-events/shipping'
    model = audit_properties(orders, shipping)
    boundary = infer_boundary(shipping)
    result = reconstruct(events(orders / 'events.jsonl'), events(shipping / 'events.jsonl'), boundary, model['properties'])
    result['model'] = model
    result['events_sha256'] = {role: hashlib.sha256((capture / 'events.jsonl').read_bytes()).hexdigest()
                               for role, capture in (('orders', orders), ('shipping', shipping))}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(infer(args.run), indent=2) + '\n')
