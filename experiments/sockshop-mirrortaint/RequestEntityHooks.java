import java.util.*;
import java.lang.reflect.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.deser.BeanDeserializer;
import com.fasterxml.jackson.databind.deser.SettableBeanProperty;

/** Exact Spring request/decoded graph facts. No source sets or business formulas. */
public final class RequestEntityHooks {
    static Map config(){return ExecutionKernelHooks.enabled()?(Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("request_entity_contracts"):null;}
    static Map jdk()throws Exception{if(JDK_CACHE==null)JDK_CACHE=JdkContractProbe.selected(new String[]{"java/util/AbstractCollection","java/util/Formatter","java/util/TimeZone","java/util/concurrent/TimeUnit","java/net/URI","java/util/regex/Pattern","java/util/regex/Matcher"});return JDK_CACHE;}
    static Object get(Object o,String name)throws Exception{return FrameworkCallHooks.invoke(o,name);}
    static final Map<ClassLoader,Map> HASH_CACHE=new WeakHashMap<ClassLoader,Map>();
    static Map JDK_CACHE;
    static Map hashes()throws Exception{
        ClassLoader loader=Thread.currentThread().getContextClassLoader();synchronized(HASH_CACHE){Map existing=HASH_CACHE.get(loader);if(existing!=null)return existing;}Map result=new TreeMap();
        // Loading classes can enter transformer/recorder code. Never hold the
        // cache monitor across resolution, byte reads or other agent locks.
        for(Object key:((Map)config().get("class_sha256")).keySet()){String n=(String)key;result.put(n,ExecutionKernelHooks.classHash(Class.forName(n.replace('/','.'),false,loader)));}Map frozen=Collections.unmodifiableMap(result);
        synchronized(HASH_CACHE){Map existing=HASH_CACHE.get(loader);if(existing!=null){if(!existing.equals(frozen))throw new IllegalStateException("Contract class resources changed");return existing;}HASH_CACHE.put(loader,frozen);}return frozen;
    }
    static boolean exact(Object o,String name){return o!=null&&o.getClass().getName().equals(name);}
    static Map fact(String kind)throws Exception{Map f=new LinkedHashMap();f.put("kind",kind);f.put("class_sha256",hashes());f.put("jdk_sha256",jdk());return f;}
    static Map request(Object o)throws Exception{
        Map f=new LinkedHashMap();f.put("method",String.valueOf(get(o,"getMethod")));f.put("uri",String.valueOf(get(o,"getUrl")));f.put("body",PlannedServiceAgent.Recorder.value(get(o,"getBody")));f.put("headers",new TreeMap((Map)get(o,"getHeaders")));return f;
    }
    static void begin(Map row){
        if(config()==null)return;Object[] args=(Object[])row.get("_args_ref");String call=(String)row.get("callee");
        if(call.equals("java/lang/StringBuilder.append(Ljava/lang/Object;)Ljava/lang/StringBuilder;")&&args.length==1&&args[0] instanceof List&&ReadEffectHooks.list(args[0]))row.put("_render_list_refs",((List)args[0]).toArray());
    }
    static void end(Map start,Object result,Map row)throws Exception{
        if(config()==null)return;String call=(String)start.get("callee");Object recv=start.get("_receiver_ref");Object[] args=(Object[])start.get("_args_ref");Map f=null;
        if(call.equals("org/springframework/http/RequestEntity.get(Ljava/net/URI;)Lorg/springframework/http/RequestEntity$HeadersBuilder;")||call.equals("org/springframework/http/RequestEntity.post(Ljava/net/URI;)Lorg/springframework/http/RequestEntity$BodyBuilder;")){
            f=fact("request-builder");f.put("valid",exact(result,"org.springframework.http.RequestEntity$DefaultBodyBuilder")&&exact(args[0],"java.net.URI"));f.put("uri",String.valueOf(args[0]));f.put("method",call.contains(".get(")?"GET":"POST");
        }else if(call.startsWith("org/springframework/http/RequestEntity$")&&(call.contains(".accept(")||call.contains(".contentType("))){
            f=fact("request-header");f.put("valid",exact(recv,"org.springframework.http.RequestEntity$DefaultBodyBuilder")&&result==recv);List values=new ArrayList();if(args[0] instanceof Object[])for(Object x:(Object[])args[0]){if(!exact(x,"org.springframework.http.MediaType"))f.put("valid",false);values.add(PlannedServiceAgent.Recorder.value(x));}else{if(!exact(args[0],"org.springframework.http.MediaType"))f.put("valid",false);values.add(PlannedServiceAgent.Recorder.value(args[0]));}f.put("values",values);
        }else if(call.startsWith("org/springframework/http/RequestEntity$")&&(call.contains(".build(")||call.contains(".body("))){
            f=fact("request-built");f.put("valid",exact(recv,"org.springframework.http.RequestEntity$DefaultBodyBuilder")&&exact(result,"org.springframework.http.RequestEntity"));if(Boolean.TRUE.equals(f.get("valid")))f.putAll(request(result));
        }else if(call.equals("org/springframework/web/client/RestTemplate.exchange(Lorg/springframework/http/RequestEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;")){
            f=fact("request-exchange");boolean valid=exact(recv,"org.springframework.web.client.RestTemplate")&&exact(args[0],"org.springframework.http.RequestEntity")&&exact(result,"org.springframework.http.ResponseEntity")&&args[1]!=null&&Arrays.asList("org.springframework.core.ParameterizedTypeReference","org.springframework.hateoas.mvc.TypeReferences$ResourceType","org.springframework.hateoas.mvc.TypeReferences$ResourcesType").contains(args[1].getClass().getMethod("getType").getDeclaringClass().getName());
            f.put("network_effects","opaque; only URI/headers/encoded bytes and response stream cross this API, not a read-only network summary");
            if(exact(recv,"org.springframework.web.client.RestTemplate")){List interceptors=new ArrayList();for(Object interceptor:(List)get(recv,"getInterceptors"))interceptors.add(interceptor.getClass().getName());f.put("interceptors",interceptors);Object factory=get(recv,"getRequestFactory");f.put("request_factory",factory.getClass().getName());f.put("error_handler",get(recv,"getErrorHandler").getClass().getName());
                boolean transport=exact(factory,"org.springframework.http.client.SimpleClientHttpRequestFactory")||exact(factory,"org.springframework.http.client.InterceptingClientHttpRequestFactory")&&exact(ResponseBindingHooks.member(factory,"requestFactory"),"org.springframework.http.client.SimpleClientHttpRequestFactory");for(Object type:interceptors)transport=transport&&"org.springframework.cloud.sleuth.instrument.web.client.TraceRestTemplateInterceptor".equals(type);valid=valid&&transport&&exact(get(recv,"getErrorHandler"),"org.springframework.web.client.DefaultResponseErrorHandler");}
            List converters=new ArrayList();if(exact(recv,"org.springframework.web.client.RestTemplate"))for(Object c:(List)get(recv,"getMessageConverters"))converters.add(c.getClass().getName().replace('.','/'));valid=valid&&!converters.isEmpty()&&((List)config().get("converter_classes")).containsAll(converters);
            f.put("valid",valid);f.put("converters",converters);if(valid){f.putAll(request(args[0]));Object b=get(result,"getBody");f.put("response_body",PlannedServiceAgent.Recorder.value(b));f.put("response_type",b==null?null:b.getClass().getName());f.put("type_reference",String.valueOf(get(args[1],"getType")));}
        }else if(call.equals("org/springframework/http/ResponseEntity.getBody()Ljava/lang/Object;")||call.equals("org/springframework/http/HttpEntity.getBody()Ljava/lang/Object;")){
            f=fact("entity-body");f.put("valid",exact(recv,"org.springframework.http.ResponseEntity")&&get(recv,"getBody")==result);f.put("body",PlannedServiceAgent.Recorder.value(result));
        }else if(call.equals("org/springframework/hateoas/Resource.getContent()Ljava/lang/Object;")){
            f=fact("resource-content");f.put("valid",exact(recv,"org.springframework.hateoas.Resource")&&get(recv,"getContent")==result);f.put("content",PlannedServiceAgent.Recorder.value(result));
        }
        if(call.equals("org/springframework/hateoas/Resource.getId()Lorg/springframework/hateoas/Link;")){
            f=fact("resource-link");boolean valid=exact(recv,"org.springframework.hateoas.Resource");if(valid){for(Object link:(List)get(recv,"getLinks"))valid=valid&&exact(link,"org.springframework.hateoas.Link");valid=valid&&get(recv,"getId")==result;}f.put("valid",valid);f.put("link",PlannedServiceAgent.Recorder.value(result));
        }
        if(call.equals("org/springframework/hateoas/Link.getHref()Ljava/lang/String;")){
            f=fact("link-href");f.put("valid",exact(recv,"org.springframework.hateoas.Link")&&get(recv,"getHref")==result);f.put("href",PlannedServiceAgent.Recorder.value(result));
        }
        if(call.equals("org/springframework/http/RequestEntity.toString()Ljava/lang/String;")&&exact(recv,"org.springframework.http.RequestEntity")){
            Object b=get(recv,"getBody");Map render=fact("request-render");render.put("content",PlannedServiceAgent.Recorder.value(b));render.put("content_type",b==null?null:b.getClass().getName());render.put("valid",true);row.put("request_render",render);
            if(b==null){f=fact("request-empty-render");f.put("valid",true);f.put("request",request(recv));}
        }
        if(call.equals("org/springframework/hateoas/Resource.toString()Ljava/lang/String;")&&exact(recv,"org.springframework.hateoas.Resource")){
            Object content=get(recv,"getContent");Map render=fact("resource-render");render.put("content",PlannedServiceAgent.Recorder.value(content));render.put("content_type",content==null?null:content.getClass().getName());
            boolean plain=content==null||content.getClass().getMethod("toString").getDeclaringClass()==Object.class&&content.getClass().getMethod("hashCode").getDeclaringClass()==Object.class;
            boolean links=true;for(Object link:(List)get(recv,"getLinks"))if(!exact(link,"org.springframework.hateoas.Link"))links=false;render.put("plain_object",plain);render.put("valid",links&&!(content instanceof java.util.Formattable));row.put("request_render",render);
        }
        if(start.get("_render_list_refs")!=null){
            Object[] before=(Object[])start.get("_render_list_refs");List list=(List)args[0];boolean valid=list.size()==before.length;List values=new ArrayList();for(int i=0;i<before.length;i++){valid=valid&&i<list.size()&&before[i]==list.get(i);Map v=new LinkedHashMap();v.put("observed",PlannedServiceAgent.Recorder.value(before[i]));v.put("type",before[i]==null?null:before[i].getClass().getName());values.add(v);}
            Map render=fact("list-render");render.put("valid",valid);render.put("object",PlannedServiceAgent.Recorder.value(args[0]));render.put("class",args[0].getClass().getName().replace('.','/'));render.put("list_class_sha256",ExecutionKernelHooks.classHash(args[0].getClass()));render.put("elements",values);row.put("request_render",render);
        }
        if(f!=null)row.put("request_entity_contract",f);
    }
    static boolean defaultFactories(ObjectMapper mapper)throws Exception{
        if(!mapper.getSerializationConfig().getAnnotationIntrospector().getClass().getName().equals("com.fasterxml.jackson.databind.introspect.JacksonAnnotationIntrospector")||!mapper.getDeserializationConfig().getAnnotationIntrospector().getClass().getName().equals("com.fasterxml.jackson.databind.introspect.JacksonAnnotationIntrospector"))return false;
        Object serializer=mapper.getSerializerFactory();Object deserializer=ResponseBindingHooks.member(mapper.getDeserializationContext(),"_factory");
        if(!serializer.getClass().getName().equals("com.fasterxml.jackson.databind.ser.BeanSerializerFactory")||!deserializer.getClass().getName().equals("com.fasterxml.jackson.databind.deser.BeanDeserializerFactory"))return false;
        Object sc=ResponseBindingHooks.member(serializer,"_factoryConfig"),dc=ResponseBindingHooks.member(deserializer,"_factoryConfig");
        for(String name:new String[]{"_additionalSerializers","_additionalKeySerializers","_modifiers"})if(java.lang.reflect.Array.getLength(ResponseBindingHooks.member(sc,name))!=0)return false;
        for(String name:new String[]{"_additionalDeserializers","_modifiers","_abstractTypeResolvers","_valueInstantiators"})if(java.lang.reflect.Array.getLength(ResponseBindingHooks.member(dc,name))!=0)return false;return true;
    }
    static boolean serializationGraph(Object object,ObjectMapper mapper,IdentityHashMap<Object,Boolean> seen,int depth)throws Exception{
        if(object==null)return true;if(depth>12||seen.size()>10000)return false;
        String name=object.getClass().getName();
        com.fasterxml.jackson.databind.JsonSerializer serializer=mapper.getSerializerProviderInstance().findValueSerializer(object.getClass());ResponseBindingHooks.serializer(serializer,object);
        if(object instanceof String||object instanceof Boolean||TemporalDateHooks.date(object))return true;
        if(object instanceof Number)return Arrays.asList("java.lang.Byte","java.lang.Short","java.lang.Integer","java.lang.Long","java.lang.Float","java.lang.Double").contains(name);
        if(seen.put(object,true)!=null)return false;
        if(object instanceof Map&&ConversionContractHooks.enabled()){
            if(object.getClass()!=HashMap.class&&object.getClass()!=LinkedHashMap.class||!serializer.getClass().getName().equals("com.fasterxml.jackson.databind.ser.std.MapSerializer")||mapper.findMixInClassFor(object.getClass())!=null)return false;
            for(Object key:((Map)object).keySet())if(!(key instanceof String)||!serializationGraph(((Map)object).get(key),mapper,seen,depth+1))return false;return true;
        }
        if(object instanceof List){if(!ReadEffectHooks.list(object))return false;for(Object value:(List)object)if(!serializationGraph(value,mapper,seen,depth+1))return false;return true;}
        if(mapper.findMixInClassFor(object.getClass())!=null||serializer.getClass()!=com.fasterxml.jackson.databind.ser.BeanSerializer.class||ResponseBindingHooks.member(serializer,"_anyGetterWriter")!=null||ResponseBindingHooks.member(serializer,"_propertyFilterId")!=null)return false;
        List<Map> props=(List)SpringTransportAgent.Transport.schema.get(name.replace('.','/'));if(props==null)return false;
        Iterator<com.fasterxml.jackson.databind.ser.PropertyWriter> writers=serializer.properties();while(writers.hasNext()){
            com.fasterxml.jackson.databind.ser.PropertyWriter w=writers.next();if(w.getClass()!=com.fasterxml.jackson.databind.ser.BeanPropertyWriter.class)return false;com.fasterxml.jackson.databind.ser.BeanPropertyWriter writer=(com.fasterxml.jackson.databind.ser.BeanPropertyWriter)w;Map prop=null;for(Map v:props)if(v.get("property").equals(writer.getName()))prop=v;
            if(prop==null||writer.getTypeSerializer()!=null)return false;java.lang.reflect.Member member=writer.getMember().getMember();
            if(member instanceof Method){String getter=(String)prop.get("getter");if(getter==null||!getter.equals(member.getDeclaringClass().getName().replace('.','/')+"."+member.getName()+org.objectweb.asm.Type.getMethodDescriptor((Method)member)))return false;}
            else if(!(member instanceof Field)||!member.getName().equals(((String)prop.get("field")).substring(((String)prop.get("field")).lastIndexOf('.')+1)))return false;
            Object value=ResponseBindingHooks.member(object,((String)prop.get("field")).substring(((String)prop.get("field")).lastIndexOf('.')+1));if(!serializationGraph(value,mapper,seen,depth+1))return false;
        }return true;
    }
    static Map serialization(Object body,Object mapper)throws Exception{
        if(config()==null)return null;Map f=fact("default-serialization-read-effects");ObjectMapper m=(ObjectMapper)mapper;
        boolean valid=mapper.getClass()==ObjectMapper.class&&defaultFactories(m)&&m.getPropertyNamingStrategy()==null&&m.getSerializationConfig().getActiveView()==null&&m.getSerializationConfig().getFilterProvider()==null;
        try{valid=valid&&serializationGraph(body,m,new IdentityHashMap<Object,Boolean>(),0);}catch(Exception unsupported){valid=false;f.put("reason",unsupported.getClass().getName()+":"+unsupported.getMessage());}f.put("valid",valid);return f;
    }
    static boolean propertyDecoder(SettableBeanProperty property,Map prop,Object owner)throws Exception{
        if(prop==null)return false;Object d=property.getValueDeserializer();String type=d.getClass().getName();String desc=(String)prop.get("descriptor");
        if(desc.equals("Ljava/lang/String;"))return type.equals("com.fasterxml.jackson.databind.deser.std.StringDeserializer");
        Map<String,String> scalar=new HashMap<String,String>();scalar.put("Z","Boolean");scalar.put("B","Byte");scalar.put("S","Short");scalar.put("C","Character");scalar.put("I","Integer");scalar.put("J","Long");scalar.put("F","Float");scalar.put("D","Double");
        if(scalar.containsKey(desc))return type.equals("com.fasterxml.jackson.databind.deser.std.NumberDeserializers$"+scalar.get(desc)+"Deserializer");
        if(desc.equals("Ljava/util/List;")||desc.equals("Ljava/util/Collection;")){
            if(!type.equals("com.fasterxml.jackson.databind.deser.std.CollectionDeserializer")||ResponseBindingHooks.member(d,"_delegateDeserializer")!=null)return false;
            Object vi=ResponseBindingHooks.member(d,"_valueInstantiator");if(!vi.getClass().getName().equals("com.fasterxml.jackson.databind.deser.std.StdValueInstantiator"))return false;
            com.fasterxml.jackson.databind.deser.ValueInstantiator value=(com.fasterxml.jackson.databind.deser.ValueInstantiator)vi;
            if(value.getDefaultCreator()==null||value.getDefaultCreator().getDeclaringClass()!=ArrayList.class||value.getDefaultCreator().getParameterCount()!=0)return false;
            String field=(String)prop.get("field");Object actual=ResponseBindingHooks.member(owner,field.substring(field.lastIndexOf('.')+1));return actual==null||actual.getClass()==ArrayList.class&&((List)actual).isEmpty();
        }return false;
    }
    static void decoded(Object body,Object mapper,Object actualType,Map row)throws Exception{
        if(config()==null||body==null||!exact(body,"org.springframework.hateoas.Resource")&&!SpringTransportAgent.Transport.schema.containsKey(body.getClass().getName().replace('.','/')))return;
        Map f=fact("resource-decoded");boolean resource=exact(body,"org.springframework.hateoas.Resource");Object content=resource?get(body,"getContent"):body;ObjectMapper m=(ObjectMapper)mapper;
        boolean valid=mapper.getClass()==ObjectMapper.class&&defaultFactories(m)&&content!=null&&((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("decoder_birth_sites")).containsKey(content.getClass().getName().replace('.','/')+".<init>()V")&&m.findMixInClassFor(content.getClass())==null&&m.getPropertyNamingStrategy()==null&&m.getDeserializationConfig().getProblemHandlers()==null&&m.getInjectableValues()==null;
        // Resolve the actual decoder, without executing a constructor/setter or
        // re-reading input. Only default bean properties with frozen setters.
        if(!valid){f.put("valid",false);f.put("reason","Unsupported default decoder/configuration or constructor");f.put("wrapper_kind",resource?"resource":"plain-bean");f.put("wrapper",PlannedServiceAgent.Recorder.value(body));f.put("content",PlannedServiceAgent.Recorder.value(content));f.put("content_type",content==null?null:content.getClass().getName());f.put("properties",Collections.emptyList());f.put("ignored",Collections.emptyList());f.put("fields",SpringTransportAgent.Transport.snapshot(content));row.put("resource_decoder",f);return;}
        com.fasterxml.jackson.databind.deser.DefaultDeserializationContext ctxt=(com.fasterxml.jackson.databind.deser.DefaultDeserializationContext)m.getDeserializationContext();
        ctxt=ctxt.createInstance(m.getDeserializationConfig(),null,m.getInjectableValues());
        JsonDeserializer root=ctxt.findRootValueDeserializer((JavaType)actualType);
        Set ignored=new HashSet();
        if(root.getClass()==BeanDeserializer.class){Object names=ResponseBindingHooks.member(root,"_ignorableProps");if(names instanceof Set)ignored.addAll((Set)names);}else valid=false;
        JsonDeserializer d=content==null?null:ctxt.findRootValueDeserializer(m.constructType(content.getClass()));
        valid=valid&&((JavaType)actualType).getRawClass()==body.getClass()&&(!resource||((JavaType)actualType).containedType(0)!=null&&((JavaType)actualType).containedType(0).getRawClass()==content.getClass())&&m.findMixInClassFor(body.getClass())==null;
        List names=new ArrayList();if(d!=null&&d.getClass()==BeanDeserializer.class){
            com.fasterxml.jackson.databind.deser.ValueInstantiator vi=((BeanDeserializer)d).getValueInstantiator();
            valid=valid&&vi.getClass().getName().equals("com.fasterxml.jackson.databind.deser.std.StdValueInstantiator")&&vi.getDefaultCreator()!=null&&vi.getDefaultCreator().getDeclaringClass()==content.getClass()&&vi.getDefaultCreator().getMember() instanceof Constructor&&vi.getDefaultCreator().getParameterCount()==0&&((BeanDeserializer)d).getObjectIdReader()==null&&ResponseBindingHooks.member(d,"_injectables")==null&&ResponseBindingHooks.member(d,"_anySetter")==null;Iterator<SettableBeanProperty> ps=((BeanDeserializer)d).properties();while(ps.hasNext()){SettableBeanProperty p=ps.next();java.lang.reflect.Member member=p.getMember()==null?null:p.getMember().getMember();
            String name=p.getName();if(ignored.contains(name))continue;Map prop=null;List<Map> props=(List)SpringTransportAgent.Transport.schema.get(content.getClass().getName().replace('.','/'));if(props!=null)for(Map x:props)if(name.equals(x.get("property")))prop=x;
            if(!propertyDecoder(p,prop,content)||p.getInjectableValueId()!=null||p.hasValueTypeDeserializer()||prop==null||!(member instanceof Method)||prop.get("getter")==null||!p.getClass().getName().equals("com.fasterxml.jackson.databind.deser.impl.MethodProperty"))valid=false;
            // The exact setter is verified by the bytecode-derived planner.
            if(member instanceof Method){String key=member.getDeclaringClass().getName().replace('.','/')+"."+member.getName()+org.objectweb.asm.Type.getMethodDescriptor((Method)member);Map setters=(Map)PlannedServiceAgent.plan.get("collection_setters");Map setter=(Map)setters.get(key);if(setter==null||prop==null||!Objects.equals(setter.get("field"),prop.get("field")))valid=false;names.add(name);}
        }}else valid=false;
        List fields=SpringTransportAgent.Transport.snapshot(content),sources=new ArrayList(),defaults=new ArrayList();Map site=(Map)((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("decoder_birth_sites")).get(content.getClass().getName().replace('.','/')+".<init>()V");Map counts=(Map)site.get("field_write_counts");
        for(Object raw:fields){Map observed=(Map)raw;String path=(String)observed.get("path");String name=path.substring(1);int base=counts.containsKey(observed.get("field"))?((Number)counts.get(observed.get("field"))).intValue():0;int version=((Number)observed.get("version")).intValue();
            if(ignored.contains(name)){if(version!=base)valid=false;defaults.add(name);}
            else if(names.contains(name)){if(version==base+1)sources.add(name);else if(version==base)defaults.add(name);else valid=false;}
        }
        f.put("valid",valid);f.put("wrapper_kind",resource?"resource":"plain-bean");f.put("wrapper",PlannedServiceAgent.Recorder.value(body));f.put("content",PlannedServiceAgent.Recorder.value(content));f.put("content_type",content.getClass().getName());f.put("properties",names);f.put("ignored",ignored);f.put("source_properties",sources);f.put("default_properties",defaults);f.put("fields",fields);row.put("resource_decoder",f);
    }
}
