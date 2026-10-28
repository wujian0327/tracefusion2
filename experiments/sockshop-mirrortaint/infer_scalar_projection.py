"""Wire identity/projection validation. No data-source edges are inferred here."""
from query_observation_planner import require
from infer_response_binding import matches
from decimal import Decimal
from math import isfinite

def validate(plan,rows):
 contract=plan.get('scalar_projection')
 if not contract:return
 for row in rows:
  if row['kind']!='http-json'or row.get('phase')!='write'or row.get('direction')!='response':continue
  for f in row['fields']:
   v=f['observed']
   if not matches(plan['response_binding']['path'],f['path'])or not(v.get('enum_type')or f.get('descriptor')=='Ljava/math/BigDecimal;'and v.get('value')is not None):continue
   from infer_foundation_values import runtime
   require(runtime(plan['execution_kernel'],rows),'Unapproved scalar bootstrap runtime')
   proofs=[r for r in rows if r['kind']=='scalar-serialization'and r.get('message')==row['message']and r['seq']<row['seq']and r['observed']==v]
   require(len(proofs)==1,'Scalar wire projection witness absent/ambiguous');p=proofs[0];require(p['class_sha256']==contract['class_sha256'],'Scalar serialization class hashes differ');require(p['generator_features']==contract['default_generator_features']and p['factory_class']in('com.fasterxml.jackson.core.JsonFactory','com.fasterxml.jackson.databind.MappingJsonFactory'),'Scalar generator configuration differs')
   if v.get('enum_type'):
    spec=plan['execution_kernel']['plain_enum_classes'].get(v['enum_type'].replace('.','/'));require(spec and p['enum_class_sha256']==spec['class_sha256']and p['projection']=='enum-name','Enum static proof/library differs');require(spec['constants'][v['enum_ordinal']]==v['value']==p['wire_value'],'Enum name/ordinal/wire projection differs')
   else:require(p['projection']=='decimal-int'and type(p['wire_value'])in(int,float)and isfinite(p['wire_value'])and Decimal(str(p['wire_value']))==Decimal(str(v['value'])),'Decimal wire projection differs')
