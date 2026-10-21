"""Normalize duplicate observation coordinates for one actual decoder read.

The oracle still uses raw captured messages and physical fields. This only names
an existing graph answer's source instance; it does not propagate dependencies,
select a source based on its value, or turn a snapshot into an origin.
"""
from query_observation_planner import require
import run_response_binding_revision as old


def source_coordinate(role,source,rows):
    if source.get('kind')!='http-json' or source.get('phase')!='read' or source.get('direction')!='response':return old.predicted_coord(source)
    facts=[r for r in rows if r['kind']=='http-source-fact' and r.get('message')==source['message'] and r.get('uri')==source.get('uri')]
    require(len(facts)==1,'Independent HTTP source record absent/ambiguous')
    fact=facts[0];fields=[f for f in fact['fields'] if all(f.get(k)==source.get(k) for k in ('owner','field','version','path'))]
    require(len(fields)==1 and fields[0]['observed']==source['observed'],'Independent decoder source instance differs')
    return old.source_coord(role,fact,fields[0])
