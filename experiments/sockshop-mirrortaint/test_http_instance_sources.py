import copy
import unittest

from infer_http_instance_sources import reconstruct


def field(path, owner, name, value='same'):
    return {'path': path, 'owner': owner, 'field': name, 'version': 1,
            'observed': {'object': owner + '-value', 'value': value}, 'primitive': False}


def observations():
    sender, receiver, answers = [], [], []
    for i, message in enumerate(('one', 'two')):
        fields = [field('request#body#name', 'client-' + message, 'name')]
        sender.extend([{'kind': 'rpc-enter', 'rpc': message, 'request_fields': fields},
                       {'kind': 'http-send', 'rpc': message, 'uri': 'http://shipping/shipping',
                        'method': 'POST', 'seq': i + 1, 'trace_id': 'same-trace', 'request_fields': fields}])
        receiver.append({'kind': 'source', 'boundary': 'http-request-body', 'message_id': message,
                         'instance': 'source-' + message, 'seq': i + 10,
                         'fields': [field('source#name', 'server-' + message, 'name')]})
        target = field('result#name', 'server-' + message, 'name')
        target.update(status='resolved', sources=[['source-' + message, 'source#name']])
        answers.append({'sink': 'return', 'method': 'ShippingController.postShipping()', 'trace_id': 'same-trace',
                        'frame': i + 1, 'seq': i + 20, 'fields': [target]})
    return sender, receiver, {'answers': answers}


class InstanceReconstructionTest(unittest.TestCase):
    def test_equal_values_and_trace_shuffled_receives_keep_message_sources(self):
        sender, receiver, boundary = observations()
        result = reconstruct(sender, list(reversed(receiver)), boundary, ['name'])
        sources = [a['fields'][0]['sources'][0][1] for a in result['answers']]
        self.assertEqual(sources, ['one', 'two'])

    def test_missing_message_stays_unknown_despite_equal_value_and_trace(self):
        sender, receiver, boundary = observations()
        receiver[0]['message_id'] = None
        result = reconstruct(sender, receiver, boundary, ['name'])
        self.assertEqual(result['answers'][0]['fields'][0]['status'], 'unknown')

    def test_duplicate_sends_rejected(self):
        sender, receiver, boundary = observations()
        sender.append(copy.deepcopy(sender[1]))
        with self.assertRaisesRegex(ValueError, 'Duplicate HTTP send'):
            reconstruct(sender, receiver, boundary, ['name'])

    def test_duplicate_receives_rejected(self):
        sender, receiver, boundary = observations()
        receiver[1]['message_id'] = receiver[0]['message_id']
        with self.assertRaisesRegex(ValueError, 'Duplicate HTTP receive'):
            reconstruct(sender, receiver, boundary, ['name'])

    def test_changed_payload_invalidates_edge(self):
        sender, receiver, boundary = observations()
        receiver[0]['fields'][0]['observed']['value'] = 'changed'
        result = reconstruct(sender, receiver, boundary, ['name'])
        self.assertEqual(result['answers'][0]['fields'][0]['status'], 'unknown')

    def test_receiver_write_without_provenance_stays_unknown(self):
        sender, receiver, boundary = observations()
        boundary['answers'][0]['fields'][0].update(status='unknown', sources=None)
        result = reconstruct(sender, receiver, boundary, ['name'])
        self.assertEqual(result['answers'][0]['fields'][0]['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
