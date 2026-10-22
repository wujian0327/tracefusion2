import java.util.*;

/** Immutable UUID identity plus the actual default text serializer. */
public final class UuidProjectionHooks {
    static boolean emitted;
    static Map config(){return PlannedServiceAgent.plan==null?null:(Map)PlannedServiceAgent.plan.get("uuid_projection");}
    static boolean uuid(Object value){return config()!=null&&value!=null&&value.getClass()==UUID.class;}
    static void enter()throws Exception{if(config()==null||emitted)return;Map r=PlannedServiceAgent.Recorder.row();r.put("java_runtime_version",System.getProperty("java.runtime.version"));r.put("class_sha256",JdkContractProbe.selected(new String[]{"java/util/UUID"}));PlannedServiceAgent.Recorder.emit("uuid-runtime",r);emitted=true;}
    static void serializer(Object s)throws Exception{if(!s.getClass().getName().equals("com.fasterxml.jackson.databind.ser.std.UUIDSerializer"))throw new IllegalStateException("Unsupported UUID serializer/shape");String hash=ExecutionKernelHooks.classHash(s.getClass()),key=s.getClass().getName().replace('.','/');boolean valid=hash.equals(((Map)config().get("serializer_class_sha256")).get(key));for(Object profile:(List)config().getOrDefault("serializer_class_sha256_profiles",Collections.emptyList()))valid|=hash.equals(((Map)profile).get(key));if(!valid)throw new IllegalStateException("UUID serializer hash differs");}
    static void serialization(UUID value,Object mapper)throws Exception{
        BusinessJackson.mapper(mapper);Object actual=mapper;if(BusinessJackson.call(actual,"findMixInClassFor",UUID.class)!=null||!"JSON".equals(BusinessJackson.call(BusinessJackson.call(actual,"getFactory"),"getFormatName")))throw new IllegalStateException("UUID mix-in/non-JSON format unsupported");Object s=BusinessJackson.call(BusinessJackson.call(actual,"getSerializerProviderInstance"),"findValueSerializer",UUID.class);serializer(s);Map r=ResponseBindingHooks.row();r.put("observed",PlannedServiceAgent.Recorder.value(value));r.put("serializer_class_sha256",ExecutionKernelHooks.classHash(s.getClass()));PlannedServiceAgent.Recorder.emit("uuid-wire",r);
    }
}
