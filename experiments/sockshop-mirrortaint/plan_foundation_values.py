"""Closed bytecode proofs for local defaults and javac8 plain enum constants."""
import json
from pathlib import Path
from plan_service_observations import callee
from query_observation_planner import require

CONTRACT=Path(__file__).with_name('foundation-value-contracts-20261028.json')

def iconst(value):
    return {'op':value+3} if -1<=value<=5 else {'op':16 if value<=127 else 17,'operand':value}

def shape(code):return [{k:v for k,v in i.items()if k!='index'}for i in code]

def plain_enum(model,owner):
    c=model['classes'][owner];require(c['super']=='java/lang/Enum' and c['access']&16384,'Not enum')
    fields=c['fields'];constants=[f['name']for f in fields if f['access']&16384]
    require(0<len(constants)<=128 and all(f['access']&8 for f in fields),'Enum has instance state/too many constants')
    array=[f for f in fields if not f['access']&16384];require(len(array)==1 and array[0]['desc']=='[L'+owner+';' and array[0]['access']&4096,'Enum synthetic values field differs')
    ctor=model['methods'][owner+'.<init>(Ljava/lang/String;I)V'];require(not ctor['exception_handlers'],'Enum constructor has handler')
    expected=[{'op':25,'var':0},{'op':25,'var':1},{'op':21,'var':2},{'op':183,'owner':'java/lang/Enum','name':'<init>','desc':'(Ljava/lang/String;I)V'},{'op':177}]
    require(shape(ctor['instructions'])==expected,'Enum constructor has additional effects')
    initial=model['methods'][owner+'.<clinit>()V'];require(not initial['exception_handlers'],'Enum initializer handler unsupported');expected=[]
    for ordinal,name in enumerate(constants):
        expected += [{'op':187,'type':owner},{'op':89},{'op':18,'constant':name,'constant_type':'String'},iconst(ordinal),{'op':183,'owner':owner,'name':'<init>','desc':'(Ljava/lang/String;I)V'},{'op':179,'owner':owner,'name':name,'desc':'L'+owner+';'}]
    expected += [iconst(len(constants)),{'op':189,'type':owner}]
    for ordinal,name in enumerate(constants):expected += [{'op':89},iconst(ordinal),{'op':178,'owner':owner,'name':name,'desc':'L'+owner+';'},{'op':83}]
    expected += [{'op':179,'owner':owner,'name':array[0]['name'],'desc':'[L'+owner+';'},{'op':177}]
    require(shape(initial['instructions'])==expected,'Enum initializer has unproved effects')
    return {'class_sha256':c['sha256'],'constants':constants,'proof':'Closed javac8 constructor and constant/values-array initializer; no additional instance state, calls, writes or handlers.'}

def enum_proofs(model):
    valid={};rejected={}
    for owner,c in model['classes'].items():
        if c.get('super')!='java/lang/Enum':continue
        try:valid[owner]=plain_enum(model,owner)
        except (ValueError,KeyError)as error:rejected[owner]=str(error)
    return valid,rejected

def attach(plan,model,enums,rejected):
    cfg=plan['execution_kernel'];contract=json.loads(CONTRACT.read_text());cfg['foundation_values']=contract
    cfg['plain_enum_classes']=enums;cfg['unproved_enum_classes']=rejected
    defaults={}
    for key,effect in cfg['constructors'].items():
        if effect.get('kind')not in ('assignments','frame'):continue
        m=model['methods'].get(key);c=m['instructions']if m else []
        if len(c)<2 or c[0]!={'index':0,'op':25,'var':0}or c[1].get('op')!=183 or callee(c[1])!='java/lang/Object.<init>()V':continue
        owner=m['owner'];cl=model['classes'][owner]
        if cl['super']!='java/lang/Object':continue
        defaults[key]={'pc':1,'class_sha256':cl['sha256'],'fields':[{'field':owner+'.'+f['name'],'descriptor':f['desc']}for f in cl['fields']if not f['access']&8]}
    cfg['default_initializers']=defaults
    plan['snapshot_fields']=sorted(set(plan['snapshot_fields'])|{f['field']for v in defaults.values()for f in v['fields']})
    from plan_scalar_projection import attach as scalar_projection
    return scalar_projection(plan,model)
