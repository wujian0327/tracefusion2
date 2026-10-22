import java.util.*;

/** Actual converter/mapper/DTO facts; never source answers or inferred labels. */
public final class ConversionContractHooks {
    static final ThreadLocal<Deque<Map>> ACTIVE=ThreadLocal.withInitial(ArrayDeque::new);
    static boolean enabled(){return ExecutionKernelHooks.enabled()&&((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("conversion_contracts")!=null;}
    static Object start(Object source,Class target,String method)throws Exception{
        if(!enabled())return SpringTransportAgent.Transport.conversionSnapshot(source);
        Map token=new LinkedHashMap();Map hashes=new TreeMap();for(Object name:((Map)((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("conversion_contracts")).get("summary_class_sha256")).keySet())hashes.put(name,ExecutionKernelHooks.classHash(Class.forName(((String)name).replace('/','.'),false,Thread.currentThread().getContextClassLoader())));token.put("summary_class_sha256",hashes);token.put("input",SpringTransportAgent.Transport.conversionSnapshot(source));token.put("source",PlannedServiceAgent.Recorder.value(source));token.put("target_class",target==null?null:target.getName());token.put("method",method);Map call=CollectionServiceHooks.CALLS.get().peek();token.put("call_id",call==null?null:call.get("call_id"));token.put("_source",source);token.put("_target",target);ACTIVE.get().push(token);return token;
    }
    public static void mapper(Object actual,Class target,boolean writing){if(!enabled()||ACTIVE.get().isEmpty())return;synchronized(PlannedServiceAgent.Recorder.class){Map token=ACTIVE.get().peek();try{
        if(writing){token.put("_write_mapper",actual);BusinessJackson.mapper(actual);Object m=actual;token.put("serialization_valid",BusinessJackson.exact(actual,"ObjectMapper")&&RequestEntityHooks.defaultFactories(m)&&BusinessJackson.call(m,"getPropertyNamingStrategy")==null&&BusinessJackson.call(BusinessJackson.call(m,"getSerializationConfig"),"getActiveView")==null&&BusinessJackson.call(BusinessJackson.call(m,"getSerializationConfig"),"getFilterProvider")==null&&RequestEntityHooks.serializationGraph(token.get("_source"),m,new IdentityHashMap<>(),0));}
        else{token.put("_read_mapper",actual);token.put("read_class_matches",target==token.get("_target"));}
    }catch(Exception unsupported){token.put("serialization_valid",false);token.put("reason",unsupported.getClass().getName()+":"+unsupported.getMessage());}}}
    static void finish(Object target,Object raw,Map row)throws Exception{
        if(!(raw instanceof Map)){row.put("input",raw);row.put("output",SpringTransportAgent.Transport.conversionSnapshot(target));return;}
        Map token=(Map)raw;if(ACTIVE.get().isEmpty()||ACTIVE.get().pop()!=token)throw new IllegalStateException("Conversion completion not paired");token.put("_closed",true);
        List before=(List)token.get("input"),after=SpringTransportAgent.Transport.conversionSnapshot(token.get("_source"));row.put("input",before);row.put("output",SpringTransportAgent.Transport.conversionSnapshot(target));
        Map proof=new LinkedHashMap();for(Object k:token.keySet())if(!((String)k).startsWith("_")&&!k.equals("input"))proof.put(k,token.get(k));
        proof.put("target",PlannedServiceAgent.Recorder.value(target));proof.put("source_after",after);proof.put("library_values",ExecutionKernelHooks.libraryValues());proof.put("class_sha256",RequestEntityHooks.hashes());
        boolean valid=Boolean.TRUE.equals(token.get("serialization_valid"))&&Boolean.TRUE.equals(token.get("read_class_matches"))&&before.equals(after)&&target!=null&&target.getClass()==token.get("_target")&&BusinessJackson.exact(token.get("_read_mapper"),"ObjectMapper");
        if(valid){try{Map decoder=new LinkedHashMap();Object mapper=token.get("_read_mapper");RequestEntityHooks.decoded(target,mapper,BusinessJackson.call(mapper,"constructType",target.getClass()),decoder);proof.put("decoder",decoder.get("resource_decoder"));valid=decoder.containsKey("resource_decoder")&&Boolean.TRUE.equals(((Map)decoder.get("resource_decoder")).get("valid"));}catch(Exception unsupported){valid=false;proof.put("reason",unsupported.getClass().getName()+":"+unsupported.getMessage());}}
        proof.put("valid",valid);row.put("conversion_contract",proof);
    }
    public static void abort(Object raw){if(raw instanceof Map&&!Boolean.TRUE.equals(((Map)raw).get("_closed"))){if(ACTIVE.get().isEmpty()||ACTIVE.get().pop()!=raw)throw new IllegalStateException("Conversion abort not paired");((Map)raw).put("_closed",true);}}
}
