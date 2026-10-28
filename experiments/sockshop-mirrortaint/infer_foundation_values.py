"""Validate generic value/default facts; never contains application field rules."""
from query_observation_planner import require
from infer_execution_kernel import same_value,coordinate

def runtime(cfg,rows):
    contract=cfg.get('foundation_values')
    if not contract:return False
    facts=[r for r in rows if r['kind']=='foundation-runtime'];require(len(facts)==1,'Foundation runtime absent/duplicated')
    fact=facts[0];supported=any(all(fact[k]==p[k]for k in ('java_runtime_version','class_sha256'))for p in contract['jdk_profiles'])
    require(fact['approved']==supported,'Foundation runtime approval contradicts pins');return supported

def call_fact(cfg,row,kind,supported):
    f=row.get('foundation_value');require(f and f['kind']==kind,'Required foundation call witness absent/different')
    require(f['jdk_approved']==supported,'Foundation call/runtime approval differs')
    if kind=='assert-is-null-string':
        library=any(f['class_sha256']==p['class_sha256']['org/springframework/util/Assert']for p in cfg['foundation_values']['assert_profiles'])
        require(not f['valid']or library,'Assert exact library differs')
    require(not f['valid']or supported and f['default_environment'],'Foundation call precondition contradicted')
    return f

def default_facts(cfg,rows,starts):
    result={};owners=set()
    for fact in rows:
        if fact['kind']!='execution-defaults':continue
        spec=cfg.get('default_initializers',{}).get(fact['constructor']);require(spec and spec['class_sha256']==fact['class_sha256'],'Default initializer/hash differs')
        candidates=[r for r in starts if r['constructor_id']==fact['constructor_id']]
        require(len(candidates)==1,'Default constructor start absent/ambiguous');start=candidates[0]
        require(start['callee']==fact['constructor'] and start['frame']==fact['caller_frame'] and start['pc']==fact['pc'] and start['seq']<fact['seq'],'Default constructor occurrence/caller differs')
        require(fact['constructor_id']not in result and fact['object']not in owners,'Default allocation occurrence/object repeated');owners.add(fact['object'])
        fields=fact['fields'];require([(f['field'],f['descriptor'])for f in fields]==[(f['field'],f['descriptor'])for f in spec['fields']],'Default field coverage differs')
        for f in fields:
            require(f['owner']==fact['object'] and f['version']==0,'Default owner/version differs');v=f['observed'];desc=f['descriptor'];value=v.get('value','@missing')
            if desc.startswith(('L','[')):require(value is None and v.get('object')is None,'Reference default is not null')
            elif desc=='Z':require(value is False and v.get('object')is None,'Boolean default differs')
            else:require(type(value)in(int,float) and value==0 and v.get('object')is None,'Primitive default differs')
        result[fact['constructor_id']]=fact
    return result
