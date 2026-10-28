"""Necessary metadata callback closure; never marks callback bodies read-only."""
from query_observation_planner import require

def validate(profile,proof):
 require(proof.get('listener_filters_verified'),'Save metadata-filter closure missing')
 rows=proof.get('listener_registry');require(isinstance(rows,list)and rows,'Listener registry witness missing');objects={};registries={}
 for row in rows:
  if 'class'in row:
   oid=row['object'].get('object');require(oid and oid not in objects,'Listener object missing/repeated');objects[oid]=row
   approved=profile['listener_filter_class_sha256'].get(row['class'].replace('.','/'))==row.get('class_sha256')and row['class'].replace('.','/')in profile['listener_filter_class_sha256']
   plain=row.get('identity_defaults')and not row['smart']and not row['generic'];require(row['filter_approved']and(approved or plain),'Unproved listener metadata implementation')
  elif 'multicaster'in row:
   mid=row['multicaster']['object'];require(mid not in registries,'Registry object repeated');registries[mid]=row
 required={r['delegate']['object']for r in objects.values()if r.get('delegate')}
 for row in registries.values():
  required.update(x.get('object')for x in row['direct_instances']);required.update(x['object'].get('object')for x in row['bean_instances'])
 require(required==set(objects)and None not in required,'Registered listener proof coverage differs')
 for listener in proof['listeners']:
  registry=registries.get(listener['multicaster_object']['object']);require(registry,'Dispatch from unobserved multicaster');members={x.get('object')for x in registry['direct_instances']}|{x['object'].get('object')for x in registry['bean_instances']};oid=listener['listener_object']['object'];require(oid in members and objects[oid]['class']==listener['listener'],'Dispatched listener instance not registered')
