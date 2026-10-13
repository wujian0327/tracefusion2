#!/usr/bin/env python3
"""Derive bounded scalar/stream summaries from actual original JVM bytecode, without oracle inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

APP = 'works/weave/socks/orders/'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def disassemble(file, verbose=False):
    result = subprocess.run(['javap', '-c', '-p', '-s', *(['-v'] if verbose else []), str(file)],
                            capture_output=True, text=True, timeout=15, check=True)
    return result.stdout


def methods(text, owner):
    result = {}
    name = desc = None
    for line in text.splitlines():
        if re.match(r'^  (public|private|protected|static)', line) and '(' in line:
            name = line.split('(', 1)[0].split()[-1]
            if name == owner.replace('/', '.'):
                name = '<init>'
        if name and line.strip().startswith('descriptor:'):
            desc = line.strip().split('descriptor: ', 1)[1]
            result[name + desc] = []
        match = re.match(r'^\s+(\d+):\s+(\w+)\s*(.*)', line)
        if match and name and desc:
            operand, _, comment = match[3].partition('//')
            result[name + desc].append({'offset': int(match[1]), 'op': match[2],
                                        'operand': operand.strip(), 'comment': comment.strip()})
    return result


def local(row, opcode):
    if row['op'] == opcode:
        return int(row['operand'])
    if row['op'].startswith(opcode + '_'):
        return int(row['op'].rsplit('_', 1)[1])
    return None


def reference(row):
    match = re.fullmatch(r'(?:InterfaceMethod|Method) (.*?):(.*)', row['comment'])
    require(match is not None, 'Unrecognized method reference')
    return match[1].replace('"', ''), match[2]


def scalar_expression(rows, getter_models=None, stream=False):
    stack, locals_, leaves = [], {}, []
    for row in rows:
        op = row['op']
        load = local(row, 'aload')
        if load is not None:
            stack.append({'op': 'argument', 'slot': load})
        elif local(row, 'fload') is not None:
            stack.append(locals_[local(row, 'fload')])
        elif local(row, 'fstore') is not None:
            locals_[local(row, 'fstore')] = stack.pop()
        elif op.startswith('fconst_'):
            stack.append({'op': 'constant', 'value': float(op[-1])})
        elif op in ('ldc', 'ldc_w'):
            match = re.fullmatch(r'float ([-+0-9.eE]+)f', row['comment'])
            require(match is not None, 'Only float constants supported')
            stack.append({'op': 'constant', 'value': float(match[1])})
        elif op in ('i2f', 'f2d', 'd2f'):
            stack.append({'op': op, 'arg': stack.pop()})
        elif op in ('fmul', 'fadd', 'dadd'):
            right, left = stack.pop(), stack.pop()
            stack.append({'op': op, 'left': left, 'right': right})
        elif op == 'invokevirtual' and getter_models is not None:
            method, desc = reference(row)
            getter = getter_models.get(method + desc)
            require(getter is not None, 'Unmodeled scalar callee: ' + method)
            receiver = stack.pop()
            require(receiver == {'op': 'argument', 'slot': 0}, 'Mapper receiver must be actual argument')
            leaf = {'op': 'field', 'field': getter['field'], 'descriptor': getter['descriptor']}
            leaves.append(leaf)
            stack.append(leaf)
        elif stream and op == 'invokedynamic':
            require('applyAsDouble:()Ljava/util/function/ToDoubleFunction;' in row['comment'], 'Unmodeled invokedynamic')
            stack.append({'op': 'mapper'})
        elif stream and op == 'invokeinterface':
            method, desc = reference(row)
            if method == 'java/util/List.stream' and desc == '()Ljava/util/stream/Stream;':
                require(stack.pop() == {'op': 'argument', 'slot': 1}, 'Stream collection argument changed')
                stack.append({'op': 'stream'})
            elif method == 'java/util/stream/Stream.mapToDouble' and desc == '(Ljava/util/function/ToDoubleFunction;)Ljava/util/stream/DoubleStream;':
                require(stack.pop() == {'op': 'mapper'} and stack.pop() == {'op': 'stream'}, 'Unmodeled stream pipeline')
                stack.append({'op': 'double-stream'})
            elif method == 'java/util/stream/DoubleStream.sum' and desc == '()D':
                require(stack.pop() == {'op': 'double-stream'}, 'Unmodeled reduction')
                stack.append({'op': 'sum'})
            else:
                raise ValueError('Unmodeled stream call')
        elif op in ('dreturn', 'freturn'):
            require(len(stack) == 1, 'Nonunique scalar return')
            return stack[0], leaves
        else:
            raise ValueError('Unmodeled scalar opcode: ' + op)
    raise ValueError('Missing scalar return')


def derive(capture):
    classes, texts, hashes = {}, {}, {}
    for owner in (APP + 'controllers/OrdersController', APP + 'entities/Item', APP + 'entities/CustomerOrder'):
        file = capture / (owner.replace('/', '_') + '.original.class')
        text = disassemble(file)
        classes[owner] = methods(text, owner)
        texts[owner] = text
        hashes[owner] = hashlib.sha256(file.read_bytes()).hexdigest()
    getters = {}
    for method, rows in classes[APP + 'entities/Item'].items():
        if len(rows) == 3 and [r['op'] for r in rows] in (['aload_0', 'getfield', 'ireturn'], ['aload_0', 'getfield', 'freturn']):
            match = re.fullmatch(r'Field ([^:]+):([IF])', rows[1]['comment'])
            require(match is not None, 'Accessor must read declared field')
            getters[APP + 'entities/Item.' + method] = {'field': match[1], 'descriptor': match[2]}
    controller = classes[APP + 'controllers/OrdersController']
    mapper_keys = [key for key in controller if key.startswith('lambda$calculateTotal$')]
    require(len(mapper_keys) == 1, 'Ambiguous mapper method')
    mapper = mapper_keys[0]
    mapper_expr, leaves = scalar_expression(controller[mapper], getters)
    calculate = 'calculateTotal(Ljava/util/List;)F'
    calc_expr, _ = scalar_expression(controller[calculate], stream=True)
    verbose = disassemble(capture / ((APP + 'controllers/OrdersController').replace('/', '_') + '.original.class'), True)
    require('REF_invokeStatic ' + APP + 'controllers/OrdersController.' + mapper.split('(')[0] in verbose,
            'Actual lambda bootstrap does not reference audited mapper')
    require('java/lang/invoke/LambdaMetafactory.metafactory' in verbose, 'Unmodeled lambda bootstrap')
    root = next(key for key in controller if key.startswith('newOrder('))
    rows = controller[root]
    calculations = [i for i, row in enumerate(rows) if row['op'].startswith('invoke')
                    and row['comment'] == 'Method calculateTotal:(Ljava/util/List;)F']
    require(len(calculations) == 1, 'Ambiguous scalar calculation in root')
    position = calculations[0]
    slot = local(rows[position + 1], 'fstore')
    require(slot is not None, 'Calculation result is not directly stored')
    constructors = [i for i, row in enumerate(rows) if row['op'] == 'invokespecial'
                    and ('Method ' + APP + 'entities/CustomerOrder."<init>":') in row['comment']]
    require(len(constructors) == 1 and constructors[0] > position, 'Ambiguous target constructor')
    constructor_pos = constructors[0]
    require(local(rows[constructor_pos - 1], 'fload') == slot, 'Constructor amount does not load calculation result')
    require(not any(local(row, 'fstore') == slot for row in rows[position + 2:constructor_pos]), 'Amount overwritten before constructor')
    _, ctor_desc = reference(rows[constructor_pos])
    require(ctor_desc.endswith('F)V'), 'Only final float constructor argument supported')
    ctor_key = '<init>' + ctor_desc
    ctor = classes[APP + 'entities/CustomerOrder'][ctor_key]
    writes = [i for i, row in enumerate(ctor) if row['op'] == 'putfield' and row['comment'].endswith(':F')]
    require(len(writes) == 1, 'Ambiguous float target field')
    write = writes[0]
    require(ctor[write - 2]['op'] == 'aload_0' and local(ctor[write - 1], 'fload') == 9,
            'Constructor float assignment changed')
    target_field = ctor[write]['comment'].split('Field ', 1)[1].split(':', 1)[0]
    return {'schema': 'tracefusion-service-model-v1', 'class_sha256': hashes,
            'root_method': APP + 'controllers/OrdersController.' + root,
            'calculate_method': APP + 'controllers/OrdersController.' + calculate,
            'mapper_method': APP + 'controllers/OrdersController.' + mapper,
            'mapper_expression': mapper_expr, 'mapper_reads': leaves, 'calculate_expression': calc_expr,
            'constructor_method': APP + 'entities/CustomerOrder.' + ctor_key,
            'constructor_amount_arg': 8, 'target_amount_field': target_field,
            'root_local_binding': {'slot': slot, 'call_offset': rows[position]['offset'], 'constructor_offset': rows[constructor_pos]['offset']},
            'scope': 'Read-only aliased DTO scalar fields plus audited sequential mapToDouble/sum and constructor amount binding; unknown mutations fail closed'}, texts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    model, texts = derive(args.capture)
    args.out.write_text(json.dumps(model, indent=2) + '\n')
    for owner, text in texts.items():
        (args.out.parent / (owner.rsplit('/', 1)[-1] + '.javap.txt')).write_text(text)
    print(json.dumps(model, indent=2))
