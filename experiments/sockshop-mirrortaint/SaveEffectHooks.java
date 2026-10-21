import java.util.*;
import java.lang.reflect.*;

/** Finite default Mongo save effect witness, never a same-value purity test. */
public final class SaveEffectHooks {
    static Map config(){return ExecutionKernelHooks.enabled()?(Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("save_effect_contracts"):null;}
    static final ThreadLocal<Deque<Map>> ACTIVE=new ThreadLocal<Deque<Map>>(){protected Deque<Map> initialValue(){return new ArrayDeque<Map>();}};
    static Object field(Object o,String name)throws Exception{return ResponseBindingHooks.member(o,name);}
    static Object call(Object o,String name,Object...args)throws Exception{
        for(Method m:o.getClass().getMethods())if(m.getName().equals(name)&&m.getParameterTypes().length==args.length){boolean ok=true;for(int i=0;i<args.length;i++)if(args[i]!=null&&!m.getParameterTypes()[i].isInstance(args[i]))ok=false;if(ok){m.setAccessible(true);try{return m.invoke(o,args);}catch(InvocationTargetException e){throw new IllegalStateException(e.getCause());}}}throw new NoSuchMethodException(name);
    }
    static boolean exact(Object o,String n){return o!=null&&o.getClass().getName().equals(n);}
    static Map hashes()throws Exception{Map r=new TreeMap();ClassLoader l=Thread.currentThread().getContextClassLoader();for(Object k:((Map)config().get("class_sha256")).keySet()){String n=(String)k;r.put(n,ExecutionKernelHooks.classHash(Class.forName(n.replace('/','.'),false,l)));}return r;}
    static List converters(Object c)throws Exception{List r=new ArrayList();for(Object x:(List)field(c,"converters"))r.add(x.getClass().getName());return r;}
    static String converterName(Object converter)throws Exception{
        String n=converter.getClass().getName();if(n.endsWith("$ConverterAdapter"))n+="["+field(converter,"converter").getClass().getName()+"]";else if(n.endsWith("$ConverterFactoryAdapter"))n+="["+field(converter,"converterFactory").getClass().getName()+"]";return n;
    }
    static Map registry(Object service)throws Exception{
        Object cs=field(service,"converters");Map result=new TreeMap();if(!((Set)field(cs,"globalConverters")).isEmpty())throw new IllegalStateException("Global custom conversion callback");
        for(Object raw:((Map)field(cs,"converters")).entrySet()){Map.Entry entry=(Map.Entry)raw;List names=new ArrayList();for(Object c:(List)field(entry.getValue(),"converters"))names.add(converterName(c));Object key=entry.getKey();result.put(((Class)call(key,"getSourceType")).getName()+"->"+((Class)call(key,"getTargetType")).getName(),names);}return result;
    }
    static final Map<ClassLoader,Map> DEFAULT_REGISTRY=new WeakHashMap<ClassLoader,Map>();
    static Map defaultRegistry()throws Exception{
        final ClassLoader loader=Thread.currentThread().getContextClassLoader();if(DEFAULT_REGISTRY.containsKey(loader))return DEFAULT_REGISTRY.get(loader);
        Class resolver=Class.forName("org.springframework.data.mongodb.core.convert.DbRefResolver",false,loader);Object unavailable=Proxy.newProxyInstance(loader,new Class[]{resolver},new InvocationHandler(){public Object invoke(Object p,Method m,Object[] a){throw new IllegalStateException("No database access allowed in default configuration probe");}});
        Object context=Class.forName("org.springframework.data.mongodb.core.mapping.MongoMappingContext",true,loader).newInstance();Class mapping=Class.forName("org.springframework.data.mapping.context.MappingContext",false,loader);Object converter=Class.forName("org.springframework.data.mongodb.core.convert.MappingMongoConverter",false,loader).getConstructor(resolver,mapping).newInstance(unavailable,context);call(converter,"afterPropertiesSet");Map r=registry(call(converter,"getConversionService"));DEFAULT_REGISTRY.put(loader,r);return r;
    }
    static boolean publisher(Object context)throws Exception{
        Set<Object> seen=Collections.newSetFromMap(new IdentityHashMap<Object,Boolean>());while(context!=null){if(!seen.add(context)||seen.size()>8)return false;String type=context.getClass().getName();if(!Arrays.asList("org.springframework.boot.context.embedded.AnnotationConfigEmbeddedWebApplicationContext","org.springframework.context.annotation.AnnotationConfigApplicationContext").contains(type)||field(context,"earlyApplicationEvents")!=null||!exact(field(context,"applicationEventMulticaster"),"org.springframework.context.event.SimpleApplicationEventMulticaster"))return false;context=call(context,"getParent");}return true;
    }
    static boolean graph(Object o,Object context,IdentityHashMap<Object,Boolean> seen,List details)throws Exception{
        if(o==null||o instanceof String||o instanceof Boolean||o.getClass()==Integer.class||o.getClass()==Long.class||o.getClass()==Double.class||o.getClass()==Float.class||TemporalDateHooks.date(o))return true;
        if(seen.put(o,true)!=null)return true;if(seen.size()>10000)return false;
        if(o instanceof List){if(!ReadEffectHooks.list(o))return false;for(Object x:(List)o)if(!graph(x,context,seen,details))return false;return true;}
        String cls=o.getClass().getName().replace('.','/');List<Map> props=(List)SpringTransportAgent.Transport.schema.get(cls);if(props==null)return false;
        if(!Boolean.TRUE.equals(call(context,"hasPersistentEntityFor",o.getClass())))return false;Object entity=call(context,"getPersistentEntity",o.getClass());if(!exact(entity,"org.springframework.data.mongodb.core.mapping.BasicMongoPersistentEntity")||(Boolean)call(entity,"hasVersionProperty"))return false;
        String fn="org.springframework.data.mapping.model.BeanWrapper";if(!entity.getClass().getMethod("getPropertyAccessor",Object.class).getDeclaringClass().getName().equals("org.springframework.data.mapping.model.BasicPersistentEntity"))return false;details.add(Collections.singletonMap("accessor",fn));
        if(!fn.equals("org.springframework.data.mapping.model.BeanWrapper"))return false;
        for(Object p:(List)field(entity,"properties")){
            if(!exact(p,"org.springframework.data.mongodb.core.mapping.CachingMongoPersistentProperty")&&!exact(p,"org.springframework.data.mongodb.core.mapping.BasicMongoPersistentProperty"))return false;
            if((Boolean)call(p,"usePropertyAccess"))return false;
            Field f=(Field)call(p,"getField");if(f==null||!f.getDeclaringClass().getName().replace('.','/').equals(cls))return false;
            boolean found=false;for(Map prop:props)if(prop.get("field").equals(cls+"."+f.getName()))found=true;if(!found)return false;
            f.setAccessible(true);Object value=f.get(o);
            if((Boolean)call(p,"isDbReference")){if(value==null)continue;if(value instanceof List&&ReadEffectHooks.list(value)&&((List)value).isEmpty())continue;details.add(Collections.singletonMap("unsupported_dbref",f.getName()));return false;}
            if(!graph(value,context,seen,details))return false;
        }return true;
    }
    public static Object begin(Object repository,Object entity){
        if(config()==null)return null;synchronized(PlannedServiceAgent.Recorder.class){Map r=PlannedServiceAgent.Recorder.row();r.put("entity",PlannedServiceAgent.Recorder.value(entity));r.put("listeners",new ArrayList());r.put("events",0);r.put("callback_invocations",0);r.put("listeners_verified",true);r.put("valid",false);r.put("_entity_ref",entity);Map caller=CollectionServiceHooks.CALLS.get().peek();if(caller!=null)r.put("call_id",caller.get("call_id"));
        try{
            r.put("class_sha256",hashes());Object ops=field(repository,"mongoOperations"),converter=call(ops,"getConverter");r.put("operations",ops.getClass().getName());r.put("converter",converter.getClass().getName());r.put("publisher",field(ops,"eventPublisher").getClass().getName());
            boolean valid=exact(repository,"org.springframework.data.mongodb.repository.support.SimpleMongoRepository")&&exact(ops,"org.springframework.data.mongodb.core.MongoTemplate")&&exact(converter,"org.springframework.data.mongodb.core.convert.MappingMongoConverter")&&publisher(field(ops,"eventPublisher"))&&exact(call(converter,"getTypeMapper"),"org.springframework.data.mongodb.core.convert.DefaultMongoTypeMapper");
            Object conversions=field(converter,"conversions");Object defaults=conversions.getClass().getConstructor(List.class).newInstance(Collections.emptyList());r.put("registry",registry(call(converter,"getConversionService")));r.put("default_registry",defaultRegistry());valid=valid&&r.get("registry").equals(r.get("default_registry"));r.put("converters",converters(conversions));r.put("default_converters",converters(defaults));valid=valid&&converters(conversions).equals(converters(defaults));
            List details=new ArrayList();valid=valid&&graph(entity,call(converter,"getMappingContext"),new IdentityHashMap<Object,Boolean>(),details);r.put("mapping",details);
            Object info=field(repository,"entityInformation");Object persistent=field(info,"entityMetadata");Object id=call(persistent,"getIdProperty");Field idField=id==null?null:(Field)call(id,"getField");
            if(idField==null||idField.getType()!=String.class)valid=false;else{r.put("id_field",idField.getDeclaringClass().getName().replace('.','/')+"."+idField.getName());idField.setAccessible(true);r.put("id_before",PlannedServiceAgent.Recorder.value(idField.get(entity)));r.put("_id_field_ref",idField);}
            r.put("before",SpringTransportAgent.Transport.snapshot(entity));r.put("preconditions",valid);r.put("valid",valid);
        }catch(Throwable unsupported){r.put("reason",unsupported.getClass().getName()+":"+unsupported.getMessage());}
        ACTIVE.get().push(r);return r;}
    }
    public static void listeners(Object listeners,Object multicaster,Object event){
        if(config()==null||ACTIVE.get().isEmpty())return;synchronized(PlannedServiceAgent.Recorder.class){Map r=ACTIVE.get().peek();List names=(List)r.get("listeners");boolean verified=Boolean.TRUE.equals(r.get("listeners_verified"));
        try{
            verified=verified&&exact(multicaster,"org.springframework.context.event.SimpleApplicationEventMulticaster")&&field(multicaster,"taskExecutor")==null&&field(multicaster,"errorHandler")==null;
            String eventType=event.getClass().getName();verified=verified&&Arrays.asList("org.springframework.data.mongodb.core.mapping.event.BeforeConvertEvent","org.springframework.data.mongodb.core.mapping.event.BeforeSaveEvent","org.springframework.data.mongodb.core.mapping.event.AfterSaveEvent").contains(eventType);
            for(Object listener:(Collection)listeners){String n=listener.getClass().getName();Map detail=new LinkedHashMap();detail.put("listener",n);detail.put("event",eventType);
                if(n.equals("org.springframework.context.event.ApplicationListenerMethodAdapter")){
                    Method method=(Method)field(listener,"method");detail.put("target",method.getDeclaringClass().getName()+"."+method.getName()+org.objectweb.asm.Type.getMethodDescriptor(method));Object condition=field(listener,"condition");verified=verified&&(condition==null||"".equals(condition));
                }else if(n.equals("org.springframework.boot.context.config.DelegatingApplicationListener")){
                    Object delegate=field(listener,"multicaster");verified=verified&&(delegate==null||exact(delegate,"org.springframework.context.event.SimpleApplicationEventMulticaster"));
                }else if(!n.equals("org.springframework.boot.context.config.ConfigFileApplicationListener"))verified=false;
                names.add(detail);
            }
        }catch(Exception unsupported){verified=false;r.put("listener_reason",unsupported.getClass().getName()+":"+unsupported.getMessage());}
        r.put("listeners_verified",verified);r.put("events",((Number)r.get("events")).intValue()+1);}
    }
    public static void handler(){if(config()==null||ACTIVE.get().isEmpty())return;synchronized(PlannedServiceAgent.Recorder.class){Map r=ACTIVE.get().peek();r.put("callback_invocations",((Number)r.get("callback_invocations")).intValue()+1);}}
    public static void exceptional(String call,Throwable error){
        if(config()==null||ACTIVE.get().isEmpty()||!call.endsWith(".save(Ljava/lang/Object;)Ljava/lang/Object;"))return;
        synchronized(PlannedServiceAgent.Recorder.class){Map r=ACTIVE.get().peek();Map caller=CollectionServiceHooks.CALLS.get().peek();if(caller==null||!Objects.equals(r.get("call_id"),caller.get("call_id")))return;ACTIVE.get().pop();r.remove("_entity_ref");r.remove("_id_field_ref");r.put("completion","exceptional");r.put("valid",false);r.put("error",PlannedServiceAgent.Recorder.value(error));PlannedServiceAgent.Recorder.emit("mongo-save-effect",r);}
    }
    public static void end(Object token,Object result){if(token==null)return;synchronized(PlannedServiceAgent.Recorder.class){Map r=(Map)token;try{
        if(ACTIVE.get().isEmpty()||ACTIVE.get().pop()!=r)throw new IllegalStateException("Save witness completion not paired");Object entity=r.remove("_entity_ref");Field id=(Field)r.remove("_id_field_ref");r.put("completion","normal");r.put("result",PlannedServiceAgent.Recorder.value(result));r.put("after",SpringTransportAgent.Transport.snapshot(entity));r.put("valid",Boolean.TRUE.equals(r.get("valid"))&&entity==result&&Boolean.TRUE.equals(r.get("listeners_verified"))&&((Number)r.get("callback_invocations")).intValue()==0&&((Number)r.get("events")).intValue()>=3);
        if(id!=null){r.put("id_after",PlannedServiceAgent.Recorder.value(id.get(entity)));
            if(Boolean.TRUE.equals(r.get("valid"))&&!Objects.equals(r.get("id_before"),r.get("id_after"))){
                String name=(String)r.get("id_field");PlannedServiceAgent.Recorder.field(entity,name,id.get(entity),"@mongo-save:"+r.get("call_id"),true,true);
                Map write=new LinkedHashMap();write.put("owner",PlannedServiceAgent.Recorder.id(entity));write.put("field",name);write.put("version",PlannedServiceAgent.Recorder.VERSIONS.get(PlannedServiceAgent.Recorder.id(entity)+":"+name));write.put("observed",PlannedServiceAgent.Recorder.value(id.get(entity)));write.put("seq",PlannedServiceAgent.Recorder.seq);r.put("id_write",write);r.put("after",SpringTransportAgent.Transport.snapshot(entity));
            }
        }PlannedServiceAgent.Recorder.emit("mongo-save-effect",r);
    }catch(Throwable e){PlannedServiceAgent.Recorder.problem("save-effect:"+e);}}}
}
