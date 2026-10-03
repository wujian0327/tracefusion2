#!/usr/bin/env python3
"""Shared executed-call engine: CFG loops plus nonrecursive direct calls."""
from collections import Counter
from functools import partial
import struct

import hybrid_provenance as common
import interproc_provenance as collector
import interproc_model as model
import loop_provenance as loop
from hybrid_model import BRANCHES, branch_taken, require, validate_config
from language_adapters import get_adapter

MAX_EXECUTED_STEPS = 4096


def plan_program(assembly, symbols, config, decoder=model.decode):
    validate_config(config)
    require(not get_adapter(config).leaf_only, 'Looped calls require a calls-capable adapter')
    functions,active = {},set()
    addresses = {}
    for name,(address,size) in symbols.items():addresses.setdefault(address,[]).append(name)

    def discover(name):
        require(name not in active, 'Recursion is unsupported')
        if name in functions:return
        require(name in symbols and len(functions)+len(active)<32, 'Unknown function or function budget exceeded')
        active.add(name);p=decoder(name,assembly,symbols)
        for n in p['instructions']:
            if n['op'] in BRANCHES | {'jmp'}:
                require(n['target'] != 0, 'A loop must not re-enter a function entry probe')
            if n['op']=='call':
                names=addresses.get(n['target_address'],[])
                require(len(names)==1, 'Call must target one known function entry')
                n['callee']=names[0]
                require(n['callee'] not in config['functions'], 'Calls into roots unsupported')
                discover(n['callee'])
        functions[name]=p;active.remove(name)

    for root in config['functions']:discover(root)
    depths={}
    def depth(name):
        if name not in depths:
            depths[name]=1+max((depth(n['callee']) for n in functions[name]['instructions'] if n['op']=='call'),default=0)
        return depths[name]
    require(all(depth(root)<=model.MAX_DEPTH for root in config['functions']), 'Call depth exceeds bound')
    plans=[functions[n] for n in config['functions']]+[functions[n] for n in sorted(set(functions)-set(config['functions']))]
    for p in plans:
        p.update(is_root=p['function'] in config['functions'],paths=[],static_sources=[],
                 probe_offsets=[n['offset'] for n in p['instructions']],
                 probe_counts=dict(selected=len(p['instructions']),all_instructions=len(p['instructions'])),
                 planning='cyclic CFG and acyclic direct-call graph; observe all scoped instructions; no path enumeration')
    return plans


def infer(events, plans, config, runtime_bases):
    require(runtime_bases is not None, 'Executable mapping required')
    adapter=get_adapter(config)
    try:adapter.context.validate(events,model.REGS)
    except (ValueError,KeyError,IndexError) as exc:
        return dict(results=[],issues=[dict(error=str(exc))],oracle_used_for_inference=False)
    functions={p['function']:p for p in plans}
    ids={p['function']:i for i,p in enumerate(plans)}
    maps={i:{n['offset']:n for n in p['instructions']} for i,p in enumerate(plans)}
    results,issues=[],[]
    for (tid,call),rows in sorted(adapter.context.group(events).items()):
        try:
            require(len(rows)<=MAX_EXECUTED_STEPS, 'Executed instruction budget exceeded; no partial result')
            rows.sort(key=lambda r:r['sequence'])
            require([r['sequence'] for r in rows]==list(range(len(rows))), 'Missing or duplicate sequence')
            first=rows[0];rid=first['root']
            require(0<=rid<len(plans) and plans[rid]['is_root'], 'Unknown root')
            name=plans[rid]['function']
            require(first['function']==rid and first['offset']==0 and first['depth']==1, 'Missing root entry')
            require(all(r['root']==rid and 0<=r['function']<len(plans) for r in rows), 'Mixed roots or unknown functions')
            require(all(rows[i]['timestamp']<=rows[i+1]['timestamp'] for i in range(len(rows)-1)), 'Non-monotonic sequence')
            require(all(len(r['regs'])==16 and len(r['inputs'])==len(config['input_fields']) and len(r['outputs'])==len(config['output_fields']) and len(r['stack'])==model.STACK_WORDS+adapter.stack_above//8 for r in rows), 'Observation shape mismatch')
            machine=model.Machine(first,config)
            calls=[dict(id='root',function=name,context=[name],depth=1,parent_id=None,callsite=None,entry_sequence=0)]
            frames=[dict(fid=rid,offset=0,instance=0)]
            path=[];visits=Counter();backedges=0;step_calls={}
            for i,event in enumerate(rows):
                require(frames, 'Event after root return')
                frame=frames[-1];fid=frame['fid'];off=frame['offset'];fn=plans[fid]['function']
                require((event['function'],event['offset'],event['depth'])==(fid,off,len(frames)), 'Event contradicts dynamic call stack or CFG edge')
                require(off in maps[fid], 'Unknown instruction offset')
                n=maps[fid][off];instance=calls[frame['instance']]
                require(n['op']!='unsupported_runtime', 'Runtime stack-growth/preemption path observed; invocation unsupported')
                visits[(fn,off)]+=1
                step=dict(function=fn,offset=off,context=instance['context'],depth=len(frames),
                          id='/'.join(instance['context'])+'|%s:%x@exec%d'%(fn,off,i),occurrence=visits[(fn,off)])
                machine.check(event,step,runtime_bases)
                if n['op'] in model.CMOVS:step['condition_taken']=branch_taken(model.CMOVS[n['op']],machine.flags)
                nxt=machine.step(n,runtime_bases)
                path.append(step);step_calls[step['id']]=instance['id']
                if n['op']=='call':
                    require(len(frames)<model.MAX_DEPTH, 'Call depth exceeds bound')
                    child=ids[n['callee']];serial=len(calls)
                    require(not plans[child]['is_root'] and all(f['fid']!=child for f in frames), 'Recursion or root reentry unsupported')
                    frame['offset']=n['next']
                    calls.append(dict(id='call%d'%serial,function=n['callee'],
                        context=instance['context']+['%s:%x@call%d'%(fn,off,serial)],
                        depth=len(frames)+1,parent_id=instance['id'],callsite=step['id'],entry_sequence=i+1))
                    frames.append(dict(fid=child,offset=0,instance=serial))
                elif n['op']=='ret':
                    instance['exit_sequence']=i;frames.pop()
                else:
                    require(nxt is not None, 'Unexpected termination')
                    frame['offset']=nxt-runtime_bases[fn]
                    require(frame['offset'] in maps[fid], 'CFG edge leaves function')
                    if n['op'] in BRANCHES | {'jmp'} and frame['offset']<=off:backedges+=1
                expected=None if not frames else runtime_bases[plans[frames[-1]['fid']]['function']]+frames[-1]['offset']
                require(nxt==expected, 'Machine call/return disagrees with logical stack')
                require((i+1==len(rows)) == (not frames), 'Incomplete root execution or extra events')
            require(not frames and not machine.returns, 'Unclosed call stack')
            analyzed,reads,contributing,graph=loop.reconstruct(path,functions,config,tid,call,argument_sources=('arg.select',))
            for read in analyzed['source_reads']:
                read['call_instance']=step_calls[read['instruction']]
            for node in graph['nodes']:
                if node.get('kind')=='source-read':node['call_instance']=step_calls[node['instruction']]
            graph['identity_scope']='root invocation + dynamic call instance + executed instruction ordinal'
            results.append(dict(pid_tid=tid,call_id=call,function=name,status='resolved',
                sources=sorted({r['field'] for r in contributing}),static_sources=[],
                argument_sources=sorted(s for s in analyzed['sources'] if s=='arg.select'),
                value=rows[-1]['outputs'][config['output_fields'].index(config['sink_field'])],sink='output.'+config['sink_field'],
                source_reads=analyzed['source_reads'],contributing_reads=contributing,call_instances=calls,
                summary=dict(executed_instructions=len(rows),backward_edges=backedges,helper_calls=len(calls)-1,
                             maximum_depth=max(c['depth'] for c in calls),total_source_reads=len(reads),
                             contributing_source_reads=len(contributing),
                             instruction_visits={'%s:%x'%k:v for k,v in sorted(visits.items())}),dependency_graph=graph))
        except (ValueError,KeyError,IndexError,TypeError,struct.error) as exc:
            issues.append(dict(pid_tid=tid,call_id=call,error=str(exc)))
    return dict(results=results,issues=issues,oracle_used_for_inference=False,
                scope='single execution identity; CFG loops and nonrecursive direct calls; observed stack/return checks; explicit executed read dependencies')


def evaluate(inferred, oracle, stats, plans):
    result=common.evaluate(inferred,oracle,stats,plans);result.pop('static_source_relations')
    rows={r['call_id']:r for r in inferred['results']}
    for truth,check in zip(oracle,result['checks']):
        summary=rows.get(truth['sequence'],{}).get('summary',{})
        check.update(expected_helper_calls=truth['expected_helper_calls'],observed_helper_calls=summary.get('helper_calls'),
                     count=truth['count'],observed_backward_edges=summary.get('backward_edges',0))
        check['passed']=check['passed'] and check['expected_helper_calls']==check['observed_helper_calls'] and (truth['count']<2 or check['observed_backward_edges']>0)
    result['passed']=result['passed'] and all(c['passed'] for c in result['checks'])
    result['scope']='fixture field/value accuracy, dynamic helper-call count and repeated execution; no compiler-independent load ordinal scoring'
    return result


build=partial(common.build,planner=plan_program,source_generator=collector.bpf_source,
              extra_flags=('-fno-optimize-sibling-calls','-fno-ipa-ra'))

if __name__=='__main__':
    raise SystemExit(common.main(default_scenario=common.ROOT/'scenarios/loop-calls-provenance',
        prefix='loop-calls-provenance',build_fn=build,record_fn=collector.record,infer_fn=infer,evaluate_fn=evaluate))
