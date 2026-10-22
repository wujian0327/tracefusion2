import java.util.*;
import com.fasterxml.jackson.databind.*;

/** Immutable UUID identity plus the actual default text serializer. */
public final class UuidProjectionHooks {
    static boolean emitted;
    static Map config(){return PlannedServiceAgent.plan==null?null:(Map)PlannedServiceAgent.plan.get("uuid_projection");}
    static boolean uuid(Object value){return config()!=null&&value!=null&&value.getClass()==UUID.class;}
    static void enter()throws Exception{if(config()==null||emitted)return;Map r=PlannedServiceAgent.Recorder.row();r.put("java_runtime_version",System.getProperty("java.runtime.version"));r.put("class_sha256",JdkContractProbe.selected(new String[]{"java/util/UUID"}));PlannedServiceAgent.Recorder.emit("uuid-runtime",r);emitted=true;}
    static void serializer(JsonSerializer s)throws Exception{if(!s.getClass().getName().equals("com.fasterxml.jackson.databind.ser.std.UUIDSerializer"))throw new IllegalStateException("Unsupported UUID serializer/shape");if(!ExecutionKernelHooks.classHash(s.getClass()).equals(((Map)config().get("serializer_class_sha256")).get(s.getClass().getName().replace('.','/'))))throw new IllegalStateException("UUID serializer hash differs");}
    static void serialization(UUID value,Object mapper)throws Exception{
        ObjectMapper actual=(ObjectMapper)mapper;if(actual.findMixInClassFor(UUID.class)!=null||!"JSON".equals(actual.getFactory().getFormatName()))throw new IllegalStateException("UUID mix-in/non-JSON format unsupported");JsonSerializer s=actual.getSerializerProviderInstance().findValueSerializer(UUID.class);serializer(s);Map r=ResponseBindingHooks.row();r.put("observed",PlannedServiceAgent.Recorder.value(value));r.put("serializer_class_sha256",ExecutionKernelHooks.classHash(s.getClass()));PlannedServiceAgent.Recorder.emit("uuid-wire",r);
    }
}
