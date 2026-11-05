import java.util.*;
import java.lang.reflect.Field;
/** Observes original calls only; never invokes a predicate. */
public final class RemoveIfHooks {
 static Map config(){return ExecutionKernelHooks.enabled()?(Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("remove_if"):null;}
 static boolean call(Map start){String k=(String)start.get("callee");return k.equals("java/util/List.removeIf(Ljava/util/function/Predicate;)Z")||k.equals("java/util/ArrayList.removeIf(Ljava/util/function/Predicate;)Z");}
 static int mod(Object list)throws Exception{Field f=AbstractList.class.getDeclaredField("modCount");f.setAccessible(true);return f.getInt(list);}
 static Map state(Object list)throws Exception{Map r=new LinkedHashMap();r.put("elements",CollectionServiceHooks.contents(list));r.put("epoch",CollectionServiceHooks.epoch(list));r.put("mod_count",mod(list));return r;}
 static void begin(Map start)throws Exception{
  Object list=start.get("_receiver_ref");if(config()==null||!call(start)||list==null||list.getClass()!=ArrayList.class)return;
  Map runtime=new LinkedHashMap();runtime.put("java_runtime_version",System.getProperty("java.runtime.version"));runtime.put("class_sha256",JdkContractProbe.selected(new String[]{"java/util/ArrayList","java/util/BitSet","java/util/Objects"}));
  if(!((List)config().get("profiles")).contains(runtime))return;
  Map r=new LinkedHashMap();r.put("version",1);r.put("runtime",runtime);r.put("receiver",PlannedServiceAgent.Recorder.id(list));r.put("predicate",PlannedServiceAgent.Recorder.value(((Object[])start.get("_args_ref"))[0]));r.put("before",state(list));start.put("remove_if_start",r);
 }
 static void complete(Map start,Object result,Throwable error,Map row)throws Exception{
  if(start.get("remove_if_start")==null)return;Map r=new LinkedHashMap((Map)start.get("remove_if_start"));r.put("after",state(start.get("_receiver_ref")));r.put("exception",PlannedServiceAgent.Recorder.value(error));r.put("exception_type",error==null?null:error.getClass().getName());r.put("result",PlannedServiceAgent.Recorder.value(result));row.put("remove_if",r);
 }
}
