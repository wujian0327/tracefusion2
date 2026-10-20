"""Exact Date evidence checks; field sources and environment facts stay distinct."""
from query_observation_planner import require

def validate_date_runtime(plan,rows):
    cfg=plan.get('date_projection')
    if not cfg:return
    evidence=[r for r in rows if r['kind']=='date-runtime'];require(len(evidence)==1,'Date runtime proof absent/duplicated')
    require(any(all(evidence[0][k]==p[k] for k in ('java_runtime_version','class_sha256')) for p in cfg['runtime_profiles']),'Unmodeled Date runtime')

def validate_date_serialization(plan,rows):
    if not plan.get('date_projection'):return
    from infer_response_binding import matches
    validate_date_runtime(plan,rows)
    for row in rows:
        if row['kind']!='http-json' or row.get('phase')!='write' or row.get('direction')!='response':continue
        for field in row['fields']:
            observed=field['observed']
            if 'date_epoch_ms' not in observed or not matches(plan['response_binding']['path'],field['path']):continue
            proofs=[r for r in rows if r['kind']=='date-serialization' and r.get('message')==row['message'] and r['seq']<row['seq'] and r['date']==observed]
            require(len(proofs)==1,'Date serialization identity proof absent/ambiguous');p=proofs[0]
            require(any(p['class_sha256']==profile['class_sha256'] for profile in plan['date_projection']['jackson_profiles']),'Unmodeled Date serializer library')
            require(field.get('wire_value')==p['wire_value'],'Date wire projection differs')
            if p['timestamp']:require(p['wire_value']==observed['date_epoch_ms'],'Date timestamp differs')
            else:
                from datetime import datetime,timezone
                value=p['wire_value'];require(isinstance(value,str),'Date ISO value absent')
                instant=datetime.strptime(value,'%Y-%m-%dT%H:%M:%S.%f%z');require(instant.tzinfo is not None and ((instant.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)).days*86400000+(instant.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)).seconds*1000+instant.microsecond//1000)==observed['date_epoch_ms'],'Date ISO instant differs')
