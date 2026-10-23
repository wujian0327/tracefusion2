"""Check the retained closure/call certificate; never creates source edges."""
from query_observation_planner import require
from plan_service_observations import callee


def validate(plan,rows):
    c=plan.get('execution_observation_closure')
    if c is None:return {'enabled':False,'elided_writes':0}
    require(c['version']==1,'Execution closure version unsupported');cfg=plan['execution_kernel'];methods=cfg['methods'];needed=c['needed_fields'];candidates=c['candidate_write_sites']
    require(c['retained_methods']==sorted(methods)and plan['target']in needed,'Execution closure lost target or application method')
    require(c['source_calls']==plan['response_binding']['source_calls'],'Execution closure moved source boundary')
    for m in methods.values():
        for ins in m['instructions']:
            if ins['op']in(180,181):require(ins['owner']+'.'+ins['name']in needed,'Execution closure omits application field effect')
            if ins['op']in(182,183,184,185):
                for kind in ('collection_getters','collection_setters'):
                    fact=plan.get(kind,{}).get(callee(ins))
                    if fact:require(fact['field']in needed,'Execution closure omits accessor effect')
    for site,p in candidates.items():
        require(p['field']not in needed and p['constructor']not in methods and site.startswith(p['constructor']+'@'),'Execution closure elides required field/method')
        owner=p['constructor'].split('.<init>')[0];require(plan['class_sha256'][owner]==p['class_sha256'],'Execution closure constructor class differs')
        require(p['descriptor']in('Z','B','C','S','I','J','F','D','Ljava/lang/String;'),'Execution closure elides mutable reference')
    starts={r['call_id']:r for r in rows if r['kind']=='collection-call-enter'};parents={r['frame']:r.get('parent')for r in rows if r['kind']=='enter'};roots={r['frame']for r in rows if r['kind']=='enter'and r['method']==plan['entry']};full=rows[0]['mode']=='full';total=0;closed=0
    def rooted(frame):
        seen=set()
        while frame is not None and frame not in seen:
            if frame in roots:return True
            seen.add(frame);frame=parents.get(frame)
        return False
    for row in rows:
        if row['kind']not in('collection-call-exit','collection-call-throw'):continue
        start=starts.get(row.get('call_id'));fact=row.get('execution_closure')
        if start and start['callee']in c['source_calls']:
            require(isinstance(fact,dict)and fact.get('version')==1 and isinstance(fact.get('elided_writes'),dict),'Source closure completion certificate missing')
            closed+=1
            for site,count in fact['elided_writes'].items():
                require(not full and c.get('enabled',True)and site in candidates and type(count)is int and count>0,'Invalid elided-write certificate')
                require(rooted(start['frame']),'Write elision outside query root');total+=count
        elif fact is not None:raise ValueError('Closure certificate not attached to a declared source call')
    return {'enabled':True,'source_completions':closed,'elided_writes':total,'all_required_application_observations_retained':True}
