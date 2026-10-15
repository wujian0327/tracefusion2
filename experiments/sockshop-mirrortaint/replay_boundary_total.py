#!/usr/bin/env python3
"""Conditional strong-boundary replay of the frozen, bytecode-derived expression.

Explicit extra ownership/flow contracts are assumed, not established by these
boundary events. This is an adequacy check, not unconditional runtime proof or
an alternative measured cost result. Predictions do not read expected sources.
"""
import argparse
import json
import math
from pathlib import Path
from infer_planned_service import evaluate,f32
from run_planned_service import load,save,sha
from evaluate_distributed_paths import fields,summary,scored
from transport_context import validate_protocol
from plan_service_observations import plan_service
from plan_distributed_fields import augment

ASSUMPTIONS=[
    'The complete source HTTP array is exactly the ordered collection consumed by the modeled reduction; no replacement, subset or additional hidden input.',
    'All decoded member fields remain immutable and exclusively owned through calculation; reflection/native/concurrent mutations excluded.',
    'The frozen pure mapper and sequential sum run exactly once on all members; no unobserved exceptional or alternate calculation path.',
    'The modeled constructor receives that result and its target field remains unchanged through actual response serialization.',
]


def predict(trial,build,assume_contracts):
    p=load(build/'orders/plan.json');m=load(build/'orders/model.json')
    regenerated=augment(m,plan_service(m,p['entry'],p['target']))
    if regenerated!=p:raise ValueError('Plan is not derived from actual original bytecode')
    rows={role:[json.loads(l) for l in (trial/'sockshop'/role/'events.jsonl').read_text().splitlines()] for role in ('orders','carts')}
    for rs in rows.values():validate_protocol(rs)
    sends={r['message']:r for r in rows['carts'] if r['kind']=='http-json' and r['phase']=='write' and r['direction']=='response'}
    receives=[r for r in rows['orders'] if r['kind']=='http-json' and r['phase']=='read' and r['direction']=='response' and r.get('method')=='GET' and r['message'] in sends]
    answers={}
    for target in rows['orders']:
        if target['kind']!='http-json' or target['phase']!='write' or target['direction']!='response':continue
        targets=[f for f in target['fields'] if f['field']==p['target']]
        if not targets:continue
        if len(targets)!=1:raise ValueError('Ambiguous target field')
        inputs=[r for r in receives if r['parent_message']==target['message']]
        answer={'known':False,'sources':[],'source_keys':[],'target':targets[0],
                'conditional_on_external_contracts':True}
        if len(inputs)!=1 or not assume_contracts:answers[target['message']]=answer;continue
        receive=inputs[0];send=sends[receive['message']];sf=fields(send);rf=fields(receive)
        if set(sf)!=set(rf):raise ValueError('Incomplete boundary snapshot')
        members={};origins=[];nodes=[]
        for path,field in rf.items():
            if field['field'] not in p['mapper_fields']:continue
            source=sf[path]
            if source['observed']!=field['observed']:
                # JVM object identity differs; only selected primitive value validates the wire edge.
                if source['observed'].get('value')!=field['observed'].get('value'):raise ValueError('Wire value differs')
            member=path.rsplit('/',1)[0];members.setdefault(member,{})[field['field']]=field
            origins.append(['carts',send['seq'],path,source['owner'],source['field'],source['version']])
            nodes.append(dict(source,service='carts',seq=send['seq'],kind='http-json',message=send['message']))
        if any(set(v)!=set(p['mapper_fields']) for v in members.values()):raise ValueError('Missing required mapper field')
        values=[evaluate(p['reduction']['mapper_expression'],v) for _,v in sorted(members.items())]
        value=evaluate(p['expression'],{},math.fsum(values))
        if not math.isfinite(value) or value!=f32(targets[0]['observed']['value']):raise ValueError('Conditional bytecode replay contradicts output')
        answer.update(known=True,sources=nodes,source_keys=origins,replayed_value=value)
        answers[target['message']]=answer
    return answers


def run(root,build,out):
    out.mkdir(parents=True,exist_ok=False);results={}
    for trial in sorted(root.glob('round-*-boundary')):
        answers=predict(trial,build,True);unknown=predict(trial,build,False)
        actual=load(trial/'sockshop/field-results.json');runs={r['case']:r['message'] for r in load(trial/'sockshop/run.json')['cases']}
        scored_rows=[]
        for q in actual['queries']:
            a=answers[runs[q['case']]]
            scored_rows.append(scored(q['case'],q['path'],a,[tuple(k) for k in q['expected_source_keys']],q['expected_sources']))
        if any(a['known'] for a in unknown.values()):raise ValueError('Missing assumptions did not fail closed')
        results[trial.name]=summary(scored_rows)
        save(out/(trial.name+'.json'),{'summary':summary(scored_rows),'queries':scored_rows})
    save(out/'comparison.json',{'scope':'Conditional feasibility, not an unconditional same-contract baseline','assumptions_not_established_by_capture':ASSUMPTIONS,
        'results':results,'without_assumptions_all_unknown':True,'build_sha256':sha(build/'build.json'),'original_data_modified':False})
    lines=['# 强边界重放：条件充分性检查','',
       '结论必须收紧为：已有boundary策略在现有还原器下返回unknown。不能据此断言所有边界方法均无法回答。',
       '本次仅使用真实boundary HTTP/JSON字段和从原版字节码重新生成的表达式，在额外契约成立的条件下重放；不使用内部帧/读取/归约/写入事件，推断不读预期来源。','',
       '额外前提（本采集没有独立证明）：','',*['- '+v for v in ASSUMPTIONS],'',
       '| 捕获 | 条件下exact | TP/FP/FN |','| --- | --- | --- |']
    for name,s in results.items():lines.append(f"| {name} | {s['exact']}/{s['queries']} | {s['tp']}/{s['fp']}/{s['fn']} |")
    lines+=['','移除额外契约时全部保持unknown。此检查说明这条确定性路径有进一步少采的空间；它没有提供与原方法同等运行时保证，也没有新测强边界方案的性能，不用来替换已有成本表。','']
    (out/'results.md').write_text('\n'.join(lines));print(json.dumps(results,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','build','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.root.resolve(),a.build.resolve(),a.out.resolve())
