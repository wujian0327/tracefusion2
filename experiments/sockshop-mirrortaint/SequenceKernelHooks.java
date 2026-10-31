import java.util.*;
/** Exact sequential pipeline facts. Never executes an application callback. */
public final class SequenceKernelHooks {
 static final ThreadLocal<IdentityHashMap<Object,Map>> PIPES=ThreadLocal.withInitial(IdentityHashMap::new);
 static final ThreadLocal<IdentityHashMap<Object,Map>> COLLECTORS=ThreadLocal.withInitial(IdentityHashMap::new);
 static Map config(){if(!ExecutionKernelHooks.enabled())return null;Map cfg=(Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("sequence_values");if(cfg==null)return null;for(Object row:(List)cfg.get("profiles"))if(System.getProperty("java.runtime.version").equals(((Map)row).get("java_runtime_version")))return cfg;return null;}
 static Map pins()throws Exception{Map p=new TreeMap();if(config()!=null){List profiles=(List)config().get("profiles");if(!profiles.isEmpty())for(Object k:((Map)((Map)profiles.get(0)).get("class_sha256")).keySet())if(((String)k).startsWith("java/"))p.put(k,JdkContractProbe.hash((String)k));}return p;}
 static Map fact(String kind)throws Exception{Map f=new LinkedHashMap();f.put("kind",kind);f.put("valid",true);f.put("java_runtime_version",System.getProperty("java.runtime.version"));f.put("class_sha256",pins());return f;}
 static Map collectorState(Object collector)throws Exception{Map state=new LinkedHashMap();for(String name:new String[]{"supplier","accumulator","combiner","finisher","characteristics"}){java.lang.reflect.Field field=collector.getClass().getDeclaredField(name);field.setAccessible(true);state.put(name,PlannedServiceAgent.Recorder.id(field.get(collector)));}return state;}
 static Map copyPipe(Map p){Map copy=new LinkedHashMap(p);copy.put("stages",new ArrayList((List)p.get("stages")));return copy;}
 static void begin(Map start)throws Exception{
  if(config()==null)return;String key=(String)start.get("callee");Object recv=start.get("_receiver_ref");Object[] args=(Object[])start.get("_args_ref");
  if(key.equals("java/util/List.forEach(Ljava/util/function/Consumer;)V")&&recv!=null&&recv.getClass()==ArrayList.class){
   Map f=fact("for-each");f.put("source",PlannedServiceAgent.Recorder.id(recv));f.put("elements",CollectionServiceHooks.contents(recv));f.put("epoch",CollectionServiceHooks.epoch(recv));f.put("callback",PlannedServiceAgent.Recorder.id(args[0]));start.put("sequence_start",f);
  }else if(key.equals("java/util/stream/Stream.collect(Ljava/util/stream/Collector;)Ljava/lang/Object;")&&PIPES.get().containsKey(recv)&&COLLECTORS.get().containsKey(args[0])){
   Map f=fact("collect-to-list");f.putAll(copyPipe(PIPES.get().get(recv)));f.put("collector",PlannedServiceAgent.Recorder.id(args[0]));Map actual=collectorState(args[0]);f.put("collector_configuration",actual);boolean sequential=Arrays.asList("java.util.stream.ReferencePipeline$Head","java.util.stream.ReferencePipeline$2","java.util.stream.ReferencePipeline$3").contains(recv.getClass().getName())&&!((java.util.stream.Stream)recv).isParallel();f.put("valid",sequential&&actual.equals(COLLECTORS.get().get(args[0])));start.put("sequence_start",f);
  }
 }
 static void complete(Map start,Object result,Throwable error,Map row)throws Exception{
  if(config()==null)return;String key=(String)start.get("callee");Object recv=start.get("_receiver_ref");Object[] args=(Object[])start.get("_args_ref");
  if(error!=null){if(start.get("sequence_start")!=null){Map f=new LinkedHashMap((Map)start.get("sequence_start"));f.put("exception",PlannedServiceAgent.Recorder.id(error));row.put("sequence_contract",f);}return;}
  if(key.equals("java/util/Collection.stream()Ljava/util/stream/Stream;")||key.equals("java/util/List.stream()Ljava/util/stream/Stream;")){
   if(recv==null||recv.getClass()!=ArrayList.class||result==null||!result.getClass().getName().equals("java.util.stream.ReferencePipeline$Head"))return;
   Map pipe=new LinkedHashMap();pipe.put("source",PlannedServiceAgent.Recorder.id(recv));pipe.put("elements",CollectionServiceHooks.contents(recv));pipe.put("epoch",CollectionServiceHooks.epoch(recv));pipe.put("stages",new ArrayList());PIPES.get().put(result,pipe);
  }else if((key.equals("java/util/stream/Stream.map(Ljava/util/function/Function;)Ljava/util/stream/Stream;")||key.equals("java/util/stream/Stream.filter(Ljava/util/function/Predicate;)Ljava/util/stream/Stream;"))&&PIPES.get().containsKey(recv)){
   String operation=key.contains(".map(")?"map":"filter",type=operation.equals("map")?"java.util.stream.ReferencePipeline$3":"java.util.stream.ReferencePipeline$2";
   if(result==null||!result.getClass().getName().equals(type))return;Map pipe=copyPipe(PIPES.get().remove(recv));Map stage=new LinkedHashMap();stage.put("operation",operation);stage.put("callback",PlannedServiceAgent.Recorder.id(args[0]));((List)pipe.get("stages")).add(stage);PIPES.get().put(result,pipe);Map f=fact("pipeline-stage");f.putAll(copyPipe(pipe));row.put("sequence_contract",f);
  }else if(key.equals("java/util/stream/Collectors.toList()Ljava/util/stream/Collector;")){
   if(result==null||!result.getClass().getName().equals("java.util.stream.Collectors$CollectorImpl"))return;Map actual=collectorState(result);COLLECTORS.get().put(result,actual);Map f=fact("to-list-collector");f.put("collector_configuration",actual);f.put("collector",PlannedServiceAgent.Recorder.id(result));row.put("sequence_contract",f);
  }else if(start.get("sequence_start")!=null){
   Map f=new LinkedHashMap((Map)start.get("sequence_start"));if(f.get("kind").equals("collect-to-list")){if(result==null||result.getClass()!=ArrayList.class)throw new IllegalStateException("toList returned unsupported list");f.put("result",PlannedServiceAgent.Recorder.id(result));f.put("result_elements",CollectionServiceHooks.contents(result));PIPES.get().remove(recv);}
   else{f.put("after",CollectionServiceHooks.contents(recv));f.put("after_epoch",CollectionServiceHooks.epoch(recv));}row.put("sequence_contract",f);
  }
 }
}
