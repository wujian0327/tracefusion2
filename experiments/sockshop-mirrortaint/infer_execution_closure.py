"""Check the retained closure/call certificate; never creates source edges."""
from query_observation_planner import require
from plan_service_observations import callee


def validate_application_writes(plan,rows):
    from collections import defaultdict
    from bisect import bisect_left
    from plan_execution_closure import application_value_fields,SCALARS
    c=plan.get('execution_observation_closure',{});policy=c.get('application_write_values');observations=[r for r in rows if r['kind']=='write-version']
    if not policy:
        require(not observations,'Unplanned version-only write');return 0
    require(policy['version']==1 and policy['required_value_fields']==sorted(application_value_fields(plan)),'Application value obligations differ')
    methods=plan['execution_kernel']['methods'];invoked={callee(i)for m in methods.values()for i in m['instructions']if i['op']in (182,183,184,185)}
    for site,p in policy['sites'].items():
        require(site==p['method']+'@'+str(p['pc'])and p['field']not in policy['required_value_fields']and p['descriptor']in SCALARS,'Unsafe application write-value site')
        require(plan['class_sha256'][p['method_owner']]==p['method_sha256']and plan['class_sha256'][p['field_owner']]==p['field_class_sha256'],'Application writer class differs')
        require(plan['execution_kernel']['class_parents'][p['field_owner']]['super']=='java/lang/Object','Inherited-field write omission unsupported')
        if p['kind']=='frame':
            m=methods[p['method']];ins=m['instructions'][p['pc']];require(m['name']!='<init>'and ins['op']==181 and ins['owner']+'.'+ins['name']==p['field']and ins['desc']==p['descriptor'],'Application field site differs')
        else:
            setter=plan.get('collection_setters',{}).get(p['method']);require(p['kind']=='setter'and p['method']in invoked and p['pc']==2 and setter and setter['field']==p['field']and setter['descriptor']==p['descriptor'],'Application setter proof differs')
    enters={r['frame']:r for r in rows if r['kind']=='enter'};roots={f for f,r in enters.items()if r['method']==plan['entry']};calls=[r for r in rows if r['kind']=='collection-call-enter'];ends={r.get('call_id'):r for r in rows if r['kind']in ('collection-call-exit','collection-call-throw')}
    def root_of(frame):
        seen=set()
        while frame in enters and frame not in seen:
            if frame in roots:return frame
            seen.add(frame);frame=enters[frame].get('parent')
        return None
    version_evidence=defaultdict(list)
    for event in rows:
        if event['kind']in ('write','write-version','read'):version_evidence[(event['owner'],event['field'])].append((event['seq'],event['version']))
        elif event['kind']in ('binding-input','binding-source','binding-return','http-json'):
            for field in event.get('fields',[]):version_evidence[(field['owner'],field['field'])].append((event['seq'],field['version']))
    for values in version_evidence.values():values.sort()
    for r in observations:
        require(rows[0]['mode']=='selective'and c.get('enabled',True)and policy.get('enabled',True),'Version-only write in disabled/full policy')
        p=policy['sites'].get(r['site']);require(p and r['field']==p['field']and type(r['version'])is int and r['version']>0 and 'observed'not in r,'Invalid application version record')
        require(root_of(r['frame'])is not None,'Application write outside query root')
        if p['kind']=='frame':require(enters[r['frame']]['method']==p['method'],'Application write Frame differs')
        else:
            matches=[a for a in calls if a['frame']==r['frame']and a['callee']==p['method']and a['receiver'].get('object')==r['owner']and a['call_id']in ends and a['seq']<r['seq']<ends[a['call_id']]['seq']]
            require(len(matches)==1,'Application setter call/owner missing or ambiguous')
        root=root_of(r['frame']);versions=version_evidence[(r['owner'],r['field'])];position=bisect_left(versions,(r['seq'],-1))
        if position and versions[position-1][0]>=enters[root]['seq']:require(r['version']==versions[position-1][1]+1,'Application write counter does not follow observed version')
        returns=[a for a in rows if a['kind']=='binding-return'and a['frame']==root]
        for ret in returns:
            final=[f['version']for f in ret['fields']if f['owner']==r['owner']and f['field']==r['field']]
            if final:
                writes=[w for w in rows if w['kind']in ('write','write-version')and w['owner']==r['owner']and w['field']==r['field']and enters[root]['seq']<w['seq']<ret['seq']]
                require(writes and set(final)=={max(writes,key=lambda w:w['seq'])['version']},'Application final write version differs')
    return len(observations)


def validate(plan,rows):
    c=plan.get('execution_observation_closure')
    if c is None:
        require(not any(r['kind']=='write-version'for r in rows),'Version-only writes have no plan')
        return {'enabled':False,'elided_writes':0}
    app_count=validate_application_writes(plan,rows)
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
    return {'enabled':True,'source_completions':closed,'elided_writes':total,'application_version_only_writes':app_count,'all_required_application_observations_retained':True}
