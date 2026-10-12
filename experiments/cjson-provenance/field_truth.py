"""Source-derived field annotations for this fixed workload, separate from engines.

This is not a blinded or multi-reviewer annotation. Expected relations are based
on the pinned source rules below, not generated from either engine's tags.
"""
from cases import CASES

SEMANTICS = 'Explicit input-field content dependence after parse_string allocation; exclude control/address/identity.'
CJSON_SHA256 = '298581a04a36c0165da4b0aade235c23088cb2faa58651d720ea2f3706ed0b0d'
RULES = {
    'copy': 'parse_string copies an ordinary input character to output; only its containing value field contributes.',
    'escaped_copy': 'parse_string copies input_pointer[1] for quote, slash and backslash; ordinary characters also copy.',
    'unicode': 'parse_hex4 computes numeric values from input digits; utf16_literal_to_utf8 encodes the codepoint, retaining explicit dependence on the same value field.',
    'empty': 'The content has zero bytes. The constant NUL terminator and object identity are outside content queries.',
    'constant': 'parse_string writes literal newline/tab constants. Input selects branches but supplies no explicit content operand.',
    'replacement': 'Driver replaces this node after parsing; the new content source is replacement v1, outside the calibrated decoder.',
    'absent': 'The requested field does not exist in the parsed document.',
    'parse_failure': 'Incomplete JSON yields no parsed document and no queried target.',
}

# Explicitly enumerate expected field relations; do not derive them from observed
# output values, observed tags, or the queried path at scoring time.
ANNOTATIONS = [
    ('equal_fields','/payer','scored',['input:v0:/payer'],'copy'),
    ('equal_fields','/recipient','scored',['input:v0:/recipient'],'copy'),
    ('nested_equal','/buyer/name','scored',['input:v0:/buyer/name'],'copy'),
    ('nested_equal','/seller/name','scored',['input:v0:/seller/name'],'copy'),
    ('nested_equal','/note','scored',['input:v0:/note'],'copy'),
    ('array_equal','/items/0/sku','scored',['input:v0:/items/0/sku'],'copy'),
    ('array_equal','/items/1/sku','scored',['input:v0:/items/1/sku'],'copy'),
    ('array_equal','/items/2/sku','scored',['input:v0:/items/2/sku'],'copy'),
    ('different_lengths','/short','scored',['input:v0:/short'],'copy'),
    ('different_lengths','/long','scored',['input:v0:/long'],'copy'),
    ('overwrite_equal','/payer','out_of_scope',['replacement:v1:/payer'],'replacement'),
    ('overwrite_equal','/recipient','scored',['input:v0:/recipient'],'copy'),
    ('overwrite_different','/payer','out_of_scope',['replacement:v1:/payer'],'replacement'),
    ('overwrite_different','/recipient','scored',['input:v0:/recipient'],'copy'),
    ('empty_fields','/empty','scored',[],'empty'),
    ('empty_fields','/nonempty','scored',['input:v0:/nonempty'],'copy'),
    ('quoted_and_slash','/s','scored',['input:v0:/s'],'escaped_copy'),
    ('constant_escape','/s','scored',[],'constant'),
    ('unicode','/latin','scored',['input:v0:/latin'],'unicode'),
    ('unicode','/face','scored',['input:v0:/face'],'unicode'),
    ('missing_field','/absent','no_sink',None,'absent'),
    ('incomplete_json','/s','no_sink',None,'parse_failure'),
]


def manifest():
    expected_order = [(c['name'], p) for c in CASES for p in c['paths']]
    if [(c,p) for c,p,_,_,_ in ANNOTATIONS] != expected_order:
        raise ValueError('Annotation coverage/order differs from fixed workload')
    return dict(schema='cjson-explicit-field-truth-v1', semantics=SEMANTICS,
                cjson_sha256=CJSON_SHA256,
                annotation_review='Source-derived, non-blinded annotations; second human review pending',
                rules=RULES,
                queries=[dict(case=c, path=p, status=s, expected_sources=xs, rule=r)
                         for c,p,s,xs,r in ANNOTATIONS])
