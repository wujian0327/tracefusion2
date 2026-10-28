import java.util.*;
import java.lang.reflect.*;
import java.math.BigDecimal;
/** Finite JVM value/effect facts. Never computes sources. */
public final class FoundationValueHooks {
 static boolean emitted,approved;
 static Map config(){return ExecutionKernelHooks.enabled()?(Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("foundation_values"):null;}
 static void runtime()throws Exception{
  Map cfg=config();if(cfg==null||emitted)return;Map actual=new TreeMap();Map profile=(Map)((List)cfg.get("jdk_profiles")).get(0);
  for(Object name:((Map)profile.get("class_sha256")).keySet())actual.put(name,JdkContractProbe.hash((String)name));
  String version=System.getProperty("java.runtime.version");approved=false;for(Object raw:(List)cfg.get("jdk_profiles")){Map p=(Map)raw;if(version.equals(p.get("java_runtime_version"))&&actual.equals(p.get("class_sha256")))approved=true;}
  Map row=PlannedServiceAgent.Recorder.row();row.put("java_runtime_version",version);row.put("class_sha256",actual);row.put("approved",approved);PlannedServiceAgent.Recorder.emit("foundation-runtime",row);emitted=true;
 }
 static boolean environment(){return System.getSecurityManager()==null&&System.getProperties().getClass()==Properties.class;}
 static Map fact(String kind)throws Exception{runtime();Map f=new LinkedHashMap();f.put("kind",kind);f.put("jdk_approved",approved);f.put("default_environment",environment());return f;}
 static void complete(Map start,Object result,Throwable error,Map row)throws Exception{
  if(config()==null)return;String key=(String)start.get("callee");Object[] args=(Object[])start.get("_args_ref");
  if(key.equals("java/lang/Boolean.valueOf(Z)Ljava/lang/Boolean;")){
   Map f=fact("boolean-box");f.put("valid",error==null&&approved&&environment()&&args.length==1&&args[0]instanceof Boolean&&result==Boolean.valueOf((Boolean)args[0]));row.put("foundation_value",f);
  }else if(key.equals("org/springframework/util/Assert.isNull(Ljava/lang/Object;Ljava/lang/String;)V")){
   Map f=fact("assert-is-null-string");Class<?> c=Class.forName("org.springframework.util.Assert",false,Thread.currentThread().getContextClassLoader());String hash=ExecutionKernelHooks.classHash(c);boolean library=false;
   for(Object raw:(List)config().get("assert_profiles"))if(hash.equals(((Map)((Map)raw).get("class_sha256")).get("org/springframework/util/Assert")))library=true;
   boolean input=args.length==2&&(args[1]==null||args[1].getClass()==String.class);f.put("class_sha256",hash);f.put("null_input",input&&args[0]==null);f.put("completion",error==null?"normal":"exceptional");
   f.put("valid",approved&&environment()&&library&&input&&(error==null?args[0]==null:args[0]!=null&&error.getClass()==IllegalArgumentException.class));row.put("foundation_value",f);
  }
 }
 static void constructed(Object receiver,Object[] args,Map row)throws Exception{
  if(config()==null||receiver.getClass()!=BigDecimal.class||args.length!=1||args[0]==null||args[0].getClass()!=Integer.class)return;
  // Only the declared int overload, not another numerically equal constructor.
  Map start=(Map)row.get("_foundation_ctor");if(start==null||!"java/math/BigDecimal.<init>(I)V".equals(start.get("callee")))return;
  Map f=fact("decimal-int");BigDecimal value=(BigDecimal)receiver;f.put("int_value",(Integer)args[0]);f.put("scale",value.scale());f.put("valid",approved&&environment()&&value.scale()==0&&value.intValueExact()==((Integer)args[0]).intValue());row.put("foundation_value",f);
 }
 public static void defaults(Object object,String ctor){synchronized(PlannedServiceAgent.Recorder.class){try{
  Map cfg=(Map)PlannedServiceAgent.plan.get("execution_kernel"),spec=(Map)((Map)cfg.getOrDefault("default_initializers",Collections.emptyMap())).get(ctor);
  if(spec==null||ExecutionKernelHooks.CONSTRUCTORS.get().isEmpty())return;Map pending=ExecutionKernelHooks.CONSTRUCTORS.get().peek();if(!ctor.equals(pending.get("callee")))return;
  Deque<PlannedServiceAgent.Recorder.Frame> frames=PlannedServiceAgent.Recorder.STACK.get();Iterator<PlannedServiceAgent.Recorder.Frame> it=frames.iterator();if(!it.hasNext())return;PlannedServiceAgent.Recorder.Frame top=it.next();
  if(ExecutionKernelHooks.method(ctor)){if(!top.method.equals(ctor)||!it.hasNext()||!it.next().id.equals(pending.get("frame")))return;}else if(!top.id.equals(pending.get("frame")))return;
  String owner=ctor.substring(0,ctor.indexOf('.'));if(!object.getClass().getName().replace('.','/').equals(owner))throw new IllegalStateException("Default initialization runtime class differs");
  Map r=PlannedServiceAgent.Recorder.row();r.put("constructor",ctor);r.put("class_sha256",ExecutionKernelHooks.classHash(object.getClass()));r.put("object",PlannedServiceAgent.Recorder.id(object));r.put("constructor_id",pending.get("constructor_id"));r.put("caller_frame",pending.get("frame"));r.put("pc",pending.get("pc"));List fields=new ArrayList();
  for(Object raw:(List)spec.get("fields")){Map p=(Map)raw;String name=(String)p.get("field"),desc=(String)p.get("descriptor");Field field=object.getClass().getDeclaredField(name.substring(name.lastIndexOf('.')+1));field.setAccessible(true);if(!org.objectweb.asm.Type.getDescriptor(field.getType()).equals(desc))throw new IllegalStateException("Default field descriptor differs");Object value=field.get(object);int version=PlannedServiceAgent.Recorder.VERSIONS.getOrDefault(r.get("object")+":"+name,0);boolean zero=value==null;
   if(field.getType().isPrimitive())zero=value instanceof Boolean?!((Boolean)value):value instanceof Character?((Character)value).charValue()==0:value instanceof Float?Float.floatToRawIntBits((Float)value)==0:value instanceof Double?Double.doubleToRawLongBits((Double)value)==0:((Number)value).longValue()==0;
   if(version!=0||!zero)throw new IllegalStateException("Allocation does not have JVM defaults at Object return");Map f=new LinkedHashMap(p);f.put("owner",r.get("object"));f.put("version",version);Map observed=PlannedServiceAgent.Recorder.value(value);if(field.getType().isPrimitive())observed.put("object",null);f.put("observed",observed);fields.add(f);
  }r.put("fields",fields);PlannedServiceAgent.Recorder.emit("execution-defaults",r);
 }catch(Throwable failure){throw new IllegalStateException(failure);}}}
 static void enumRead(Object value,String owner,String field,Map row)throws Exception{
  Map proof=(Map)((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).getOrDefault("plain_enum_classes",Collections.emptyMap())).get(owner);if(proof==null)return;Map f=fact("plain-enum-constant");Class<?> c=Class.forName(owner.replace('/','.'),false,Thread.currentThread().getContextClassLoader());int ordinal=((List)proof.get("constants")).indexOf(field);boolean valid=approved&&environment()&&ordinal>=0&&value!=null&&value.getClass()==c&&c.getField(field).get(null)==value&&((Enum)value).ordinal()==ordinal&&((Enum)value).name().equals(field);f.put("valid",valid);f.put("class_sha256",ExecutionKernelHooks.classHash(c));f.put("constant",field);f.put("ordinal",ordinal);row.put("foundation_enum",f);
 }
}
