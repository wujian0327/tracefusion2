"""Validate ownership certificates without adding/changing provenance origins."""
from query_observation_planner import require

def validate(plan,rows):
 cfg=plan['execution_kernel'].get('source_locality')
 if not cfg:return {}
 pins=cfg['class_sha256'];framework={}
 for r in rows:
  if r['kind']=='locality-framework':
   require(pins.get(r['class'])==r['class_sha256'],'Ownership runtime class differs');framework[r['class']]=r
 begins={};ends={};result={}
 for r in rows:
  if r['kind']=='locality-begin':
   require(r['ownership_id']not in begins,'Ownership occurrence repeated');begins[r['ownership_id']]=r
  elif r['kind']=='locality-end':
   require(r['ownership_id']in begins and r['ownership_id']not in ends,'Ownership completion absent/repeated');ends[r['ownership_id']]=r
 require(set(begins)==set(ends),'Ownership capture did not close')
 for oid,start in begins.items():
  end=ends[oid];family=[r for r in rows if r.get('ownership_id')==oid];require(start['seq']<end['seq']and all(r['call_id']==start['call_id']and r['caller_frame']==start['caller_frame']and r['thread']==start['thread']for r in family),'Ownership caller/call binding differs')
  calls=[r for r in rows if r['kind']=='collection-call-enter'and r['call_id']==start['call_id']];finishes=[r for r in rows if r['kind']in ('collection-call-exit','collection-call-throw')and r['call_id']==start['call_id']]
  require(len(calls)==len(finishes)==1 and calls[0]['seq']<start['seq']<end['seq']<finishes[0]['seq']and calls[0]['frame']==start['caller_frame']and calls[0]['callee']==start['callee'],'Ownership source call interval differs')
  require(start['callee']in plan['response_binding']['source_calls']and end['source_callee']==start['callee'],'Ownership is not a declared source')
  if not end['valid']:continue
  readers=[r for r in family if r['kind']=='locality-reader'];decoded=[r for r in family if r['kind']=='locality-decoded'];returns=[r for r in family if r['kind']=='locality-client-return'];births=[r for r in family if r['kind']=='locality-birth']
  require(len(readers)==len(decoded)==len(returns)==end['readers']==end['returns']==1 and readers[0]['eligible']and decoded[0]['valid'],'Ownership necessary decoder/return witness absent')
  read,dec,ret=readers[0],decoded[0],returns[0];require(read['seq']<dec['seq']<ret['seq']<end['seq']and dec['body']==ret['body']==end['body']==finishes[0]['result']['object'],'Ownership returned object differs')
  require(all(dec.get(k)==end.get(k)for k in ('objects','corridor','reader_configuration','properties','object_token','caller_bottom','proxy_type','cache_scope','cache_operations_empty')),'Ownership graph/configuration/corridor rebound')
  born={r['object']:r for r in births};require(len(born)==len(births),'Ownership object birth repeated')
  graph={o['owner']:o for o in dec['objects']};require(len(graph)==len(dec['objects'])and end['body']in graph,'Ownership graph missing/repeated root')
  sources=[r for r in rows if r['kind']=='binding-source'and r.get('source_call_id')==start['call_id']]
  require(len(sources)==1 and all(f['owner']in graph for f in sources[0]['fields']),'Ownership omits actual source-field owners')
  for owner,obj in graph.items():
   require(owner in born and read['seq']<born[owner]['seq']<dec['seq']and born[owner]['type']==obj['type'],'Ownership graph allocation coverage differs')
   require(all(child in graph for child in obj['references']),'Ownership graph has external mutable reference')
  require(born[end['body']]['birth_kind']=='default-bean'and graph[end['body']]['type']==read['bean']in cfg['beans'],'Ownership root initializer differs')
  todo=[end['body']];seen=set()
  while todo:
   owner=todo.pop()
   if owner not in seen:seen.add(owner);todo.extend(graph[owner]['references'])
  require(seen==set(graph),'Ownership graph contains disconnected objects')
  for method in dec['corridor']:
   owner,name=method.rsplit('.',1);require(name in cfg['return_methods'].get(owner,[])and owner in framework and framework[owner]['seq']<read['seq'],'Ownership corridor class/method instrumentation absent')
  require(isinstance(dec.get('caller_bottom'),int)and dec['caller_bottom']==start['caller_bottom']>0,'Ownership actual caller depth absent')
  conf=dec.get('reader_configuration');require(conf and conf['bean']==read['bean']and conf['eligible'],'Ownership configuration witness absent')
  require(all(conf.get(k,'missing')is None for k in ('update','injection','schema','filter','problem_handlers','default_typer','active_view')),'Ownership decoder configuration allows publication callbacks')
  require(dec.get('object_token')is True,'Ownership actual object token absent')
  require(all(read.get(k)==v for k,v in conf.items()),'Ownership reader configuration rebound')
  factories=[r for r in family if r['kind']=='locality-factory-config']
  fc=conf.get('factory_configuration')
  require(len(factories)==1 and fc and all(factories[0].get(k)==v for k,v in fc.items())and factories[0]['seq']<read['seq'],'Ownership factory configuration absent/rebound')
  used={'boolean','int','long','double','float','java/lang/Object','java/lang/String','java/lang/Long','java/lang/Integer','java/lang/Boolean','java/lang/Double','java/lang/Float','java/util/Map','java/util/List','java/util/LinkedHashMap','java/util/ArrayList',read['bean']}
  require(set(fc['used_types'])==used and fc['_modifiers']==fc['_abstractTypeResolvers']==[],'Ownership factory scope/callback differs')
  allowed={
   '_additionalDeserializers':{'com/fasterxml/jackson/databind/module/SimpleDeserializers':'exact-map-no-used-type','com/fasterxml/jackson/datatype/jdk8/Jdk8Deserializers':'no-reference-type'},
   '_additionalKeyDeserializers':{'com/fasterxml/jackson/databind/module/SimpleKeyDeserializers':'exact-map-no-used-type','com/fasterxml/jackson/databind/deser/std/StdKeyDeserializers':'standard-key-resolver'},
   '_valueInstantiators':{'com/fasterxml/jackson/datatype/jsr310/JavaTimeModule$1':'non-zoneid-identity'}}
  for field,rules in allowed.items():
   for callback in fc[field]:
    cls=callback['class'];require(cls in rules and callback['rule']==rules[cls]and callback['class_sha256']==pins.get(cls)and cls in framework,'Ownership factory callback not proved')
    if callback['rule']=='exact-map-no-used-type':require(not set(callback['mapped_types'])&used,'Ownership custom decoder matches used type')
  introspectors=conf.get('introspectors',[])
  require(introspectors and all(c in ('com/fasterxml/jackson/databind/introspect/JacksonAnnotationIntrospector','com/fasterxml/jackson/databind/introspect/AnnotationIntrospectorPair','com/fasterxml/jackson/module/paramnames/ParameterNamesAnnotationIntrospector')and c in framework for c in introspectors),'Ownership annotation callback not proved')
  fields={f['field']:f['descriptor']for f in cfg['beans'][read['bean']]['fields']};properties=dec.get('properties',[])
  require(len(properties)==len(fields)and {p['field']:p['descriptor']for p in properties}==fields,'Ownership physical setter coverage differs')
  for p in properties:
   suffix={'J':'NumberDeserializers$LongDeserializer','I':'NumberDeserializers$IntegerDeserializer','Z':'NumberDeserializers$BooleanDeserializer','Ljava/lang/String;':'StringDeserializer','Ljava/lang/Object;':'UntypedObjectDeserializer$Vanilla'}[p['descriptor']]
   require(p['decoder']=='com/fasterxml/jackson/databind/deser/std/'+suffix and p['decoder']in framework and p['null_provider']in(p['decoder'],'com/fasterxml/jackson/databind/deser/impl/NullsConstantProvider'),'Ownership property decoder/null callback differs')
   require(plan['collection_setters'].get(p['setter'],{}).get('field')==p['field']and p['type_handler']is None and p['injectable']is None,'Ownership property callback/assignment proof differs')
  for owner in (conf['reader_class'],conf['context_class'],conf['factory_class'],'com/fasterxml/jackson/databind/deser/BeanDeserializer','com/fasterxml/jackson/databind/deser/std/UntypedObjectDeserializer$Vanilla'):
   require(owner in framework,'Ownership actual decoder instrumentation absent')
  require(dec['cache_scope']==any(x.startswith('org/springframework/cache/interceptor/CacheAspectSupport.')for x in dec['corridor']),'Ownership cache scope rebound')
  if dec['cache_scope']:
   cache=[r for r in family if r['kind']=='locality-cache'];require(len(cache)==1 and cache[0]['empty']and cache[0]['seq']<read['seq'],'Ownership cache publication not excluded')
   witness=cache[0];require(witness['class']is None and witness['class_sha256']is None or witness['class']=='java/util/Collections$EmptyList'and any(p['class_sha256'].get(witness['class'])==witness['class_sha256']for p in plan['execution_kernel']['runtime_profiles']),'Ownership cache emptiness implementation unproved')
  result[start['call_id']]={'objects':graph,'body':end['body'],'seq':end['seq'],'births':{k:born[k]['seq']for k in graph},'ownership_id':oid}
 return result
