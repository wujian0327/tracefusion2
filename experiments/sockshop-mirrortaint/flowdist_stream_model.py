#!/usr/bin/env python3
"""Bounded sequential List.stream().mapToDouble(lambda).sum() summary.

Derive callback-result -> terminal-result library edges from pipeline structure,
never from selected fields, experiment queries, expected labels or runtime values.
Other stream shapes receive no summary.
"""
import argparse
import json
from pathlib import Path
import re


def derive(rows):
    groups={}
    for index,row in enumerate(rows):
        method,body=row.split(' - ',1);groups.setdefault(method,[]).append((index,body))
    edges=[]
    for method,statements in groups.items():
        if any('parallel' in body for _,body in statements):continue
        lists={};factories={};pipelines={};definitions={}
        for index,body in statements:
            defined=re.match(r'(\S+) = ',body)
            if defined:definitions[defined[1]]=definitions.get(defined[1],0)+1
            stream=re.fullmatch(r'(\S+) = interfaceinvoke \S+\.<java.util.List: java.util.stream.Stream stream\(\)>\(\)',body)
            if stream:lists[stream[1]]=index;continue
            factory=re.match(r'(\S+) = dynamicinvoke "applyAsDouble" ',body)
            target=re.search(r'handle: (<[^>]+>)',body)
            if factory and target and 'java.lang.invoke.LambdaMetafactory:' in body:
                factories[factory[1]]=(index,target[1]);continue
            mapped=re.fullmatch(r'(\S+) = interfaceinvoke (\S+)\.<java.util.stream.Stream: java.util.stream.DoubleStream mapToDouble\(java.util.function.ToDoubleFunction\)>\((\S+)\)',body)
            if mapped and mapped[2] in lists and mapped[3] in factories:
                pipelines[mapped[1]]=(index,mapped[2],mapped[3],factories[mapped[3]][1]);continue
            summed=re.fullmatch(r'(\S+) = interfaceinvoke (\S+)\.<java.util.stream.DoubleStream: double sum\(\)>\(\)',body)
            if not summed or summed[2] not in pipelines:continue
            _,stream,callback,target=pipelines[summed[2]]
            if any(definitions.get(v)!=1 for v in (stream,callback,summed[2],summed[1])):continue
            returns=[(i,b.split(' ',1)[1]) for i,b in groups.get(target,[]) if re.fullmatch(r'return \S+',b)]
            if not returns:continue
            for source,variable in returns:
                edges.append({'source_statement':source,'target_statement':index,'source_variable':variable,
                    'target_variable':summed[1],'source_method':target,'target_method':method,
                    'rule':'Sequential List.stream -> mapToDouble(lambda) -> DoubleStream.sum; mapped scalar result contributes to reduction',
                    'edge_type':'VTE_RET'})
    return edges


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--statements',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    if a.out.exists():raise ValueError('Fresh model directory required')
    a.out.mkdir(parents=True);edges=derive(a.statements.read_text().splitlines())
    (a.out/'model.json').write_text(json.dumps({'edges':edges,'labels_consumed':False,'algorithm_modified':False,
        'library_model_extended':True,'scope':'Direct sequential List/mapToDouble/sum, no stateful/custom serialization or parallel model'},indent=2)+'\n')
    (a.out/'model.tsv').write_text(''.join('\t'.join(str(e[k]) for k in ('source_statement','target_statement','source_variable','target_variable','source_method','target_method'))+'\n' for e in edges))
