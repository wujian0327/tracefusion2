"""Fixed normal-input workload. Expected values are evaluated outside the C driver."""
import json
import re

CASES = [
    dict(name='equal_fields', text='{"payer":"alice","recipient":"alice"}', paths=['/payer','/recipient']),
    dict(name='nested_equal', text='{"buyer":{"name":"same"},"seller":{"name":"same"},"note":"other"}',
         paths=['/buyer/name','/seller/name','/note']),
    dict(name='array_equal', text='{"items":[{"sku":"A"},{"sku":"A"},{"sku":"B"}]}',
         paths=['/items/0/sku','/items/1/sku','/items/2/sku']),
    dict(name='different_lengths', text='{"short":"x","long":"abcdefghijk"}', paths=['/short','/long']),
    dict(name='overwrite_equal', text='{"payer":"alice","recipient":"alice"}',
         replace_key='payer', replacement='alice', paths=['/payer','/recipient']),
    dict(name='overwrite_different', text='{"payer":"old","recipient":"keep"}',
         replace_key='payer', replacement='new', paths=['/payer','/recipient']),
    dict(name='empty_fields', text='{"empty":"","nonempty":"x"}', paths=['/empty','/nonempty']),
    dict(name='quoted_and_slash', text=r'{"s":"a\"b\\c\/d"}', paths=['/s'], semantics='escape_diagnostic'),
    dict(name='constant_escape', text=r'{"s":"\n\t"}', paths=['/s'], semantics='control_diagnostic'),
    dict(name='unicode', text=r'{"latin":"\u0041","face":"\uD83D\uDE00"}',
         paths=['/latin','/face'], semantics='unicode_diagnostic'),
    dict(name='missing_field', text='{"present":"x"}', paths=['/absent']),
    dict(name='incomplete_json', text='{"s":', paths=['/s'], valid=False),
]


def tokens(text):
    """Independent syntax walk; maps string value tokens by path, never by equal value."""
    lex = list(re.finditer(r'"(?:[^"\\]|\\.)*"|[{}\[\]:,]', text))
    pos, spans = 0, {}
    def take(expected=None):
        nonlocal pos
        t=lex[pos]; pos+=1
        if expected is not None and t.group()!=expected: raise ValueError('unexpected JSON token')
        return t
    def value(path):
        t=take(); s=t.group()
        if s=='{':
            if lex[pos].group()=='}': take('}'); return
            while True:
                key=json.loads(take().group()); take(':')
                value(path+'/'+key.replace('~','~0').replace('/','~1'))
                if lex[pos].group()=='}': take('}'); break
                take(',')
        elif s=='[':
            index=0
            if lex[pos].group()==']': take(']'); return
            while True:
                value(path+'/'+str(index)); index+=1
                if lex[pos].group()==']': take(']'); break
                take(',')
        elif s.startswith('"'):
            # Workload lexical inputs are ASCII, including escaped Unicode.
            spans[path]=dict(begin=t.start()+1,end=t.end()-1,decoded=json.loads(s))
        else: raise ValueError('outside fixed string/object/array workload')
    value('')
    if pos!=len(lex): raise ValueError('unused tokens')
    return spans


def lookup(obj, path):
    try:
        for token in path.split('/')[1:]:
            token=token.replace('~1','/').replace('~0','~')
            obj=obj[int(token)] if isinstance(obj,list) else obj[token]
        return obj
    except (KeyError,IndexError,TypeError): return None


def oracle(case):
    try: obj=json.loads(case['text'])
    except json.JSONDecodeError:
        if case.get('valid',True): raise
        return dict(parsed=False,queries=[dict(path=p,status='no_sink') for p in case['paths']],document=None)
    if not case.get('valid',True): raise ValueError('expected rejection')
    spans=tokens(case['text'])
    for path,span in spans.items():
        if lookup(obj,path)!=span['decoded']: raise ValueError('syntax/Python parser disagreement')
    if 'replace_key' in case: obj[case['replace_key']]=case['replacement']
    queries=[]
    for path in case['paths']:
        val=lookup(obj,path)
        if val is None:
            queries.append(dict(path=path,status='no_sink')); continue
        origin='replacement' if 'replace_key' in case and path=='/'+case['replace_key'] else 'input:'+path
        queries.append(dict(path=path,status='string',value_hex=val.encode().hex(),
                            format_field_origin=origin,
                            explicit_data_origin_status='not_scored',
                            empty_content=(val=='')))
    return dict(parsed=True,queries=queries,document=obj,input_string_spans=spans)
