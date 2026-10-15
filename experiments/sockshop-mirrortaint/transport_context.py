"""Validate recorded W3C invocation identities, independent of field values."""
from collections import defaultdict
import re
from query_observation_planner import require


def identifier(value, width):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{'+str(width)+'}', value) and int(value, 16) != 0


def validate_context(row):
    require(row.get('transport_protocol') == 'w3c-trace-context', 'Missing W3C context declaration')
    require(identifier(row.get('trace_id'), 32) and identifier(row.get('request_span_id'), 16)
            and identifier(row.get('span_id'), 16), 'Invalid W3C invocation identifier')
    require(row.get('parent_span_id') is None or identifier(row['parent_span_id'], 16), 'Invalid W3C parent span')
    require(row.get('trace_flags') in ('00', '01'), 'Invalid supported W3C flags')
    require(row['message'] == row['trace_id']+'/'+row['request_span_id'], 'W3C invocation key differs from trace/span')


def validate_protocol(rows):
    """Reject mismatched client scopes; server spans must parent the wire span.

    The local `message` field is only an internal composite key. It is never
    propagated in a custom HTTP header, nor used without validating trace/span.
    """
    stacks = defaultdict(list)
    client_spans = set()
    server_spans = {}
    for row in rows:
        kind = row['kind']
        if kind not in ('http-rpc-enter', 'http-rpc-exit', 'http-rpc-abort', 'http-json'):
            continue
        validate_context(row)
        stack = stacks[row['thread']]
        if kind == 'http-rpc-enter':
            key = (row['trace_id'], row['span_id'])
            require(row['span_id'] == row['request_span_id'] and key not in client_spans, 'Reused or non-client RPC span')
            client_spans.add(key)
            stack.append(row)
        elif kind in ('http-rpc-exit', 'http-rpc-abort'):
            require(stack and stack[-1]['message'] == row['message'], 'Broken HTTP RPC context')
            stack.pop()
        else:
            client = (row['phase'], row['direction']) in (('read', 'response'), ('write', 'request'))
            if client:
                require(stack and all(stack[-1].get(k) == row.get(k) for k in
                        ('message', 'uri', 'trace_id', 'span_id', 'parent_span_id', 'request_span_id', 'trace_flags', 'tracestate')),
                        'JSON context does not belong to active actual RPC')
            else:
                require(row['parent_span_id'] == row['request_span_id'] or
                        (row['parent_span_id'] is None and row['span_id'] == row['request_span_id']), 'Server span has wrong wire parent')
                prior = server_spans.setdefault(row['message'], row['span_id'])
                require(prior == row['span_id'], 'Multiple server spans for one HTTP invocation')
    require(not any(stacks.values()), 'Unclosed HTTP RPC')
    return True
