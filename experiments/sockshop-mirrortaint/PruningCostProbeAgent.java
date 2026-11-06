import java.lang.instrument.*;
import java.lang.management.*;
import java.nio.file.*;
import java.security.ProtectionDomain;
import java.util.*;
import java.util.concurrent.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
/** Diagnostic only. Times explicit observer methods, never original business invokes. */
public class PruningCostProbeAgent implements Opcodes {
 static final boolean COARSE=Boolean.getBoolean("probe.coarse");
 static final ThreadLocal<Set<String>> KEYS=ThreadLocal.withInitial(HashSet::new);
 static final Span SKIP=new Span(null,false);
 static final ThreadMXBean CPU=ManagementFactory.getThreadMXBean();
 static class Span {String key;long wall,cpu,childWall,childCpu;Span(String k){this(k,true);}Span(String k,boolean timed){key=k;if(timed){wall=System.nanoTime();cpu=CPU.getCurrentThreadCpuTime();}}}
 static final ThreadLocal<Deque<Span>> STACK=ThreadLocal.withInitial(ArrayDeque::new);
 static final ConcurrentMap<String,long[]> TIMES=new ConcurrentHashMap<>();
 public static void begin(String key){if(COARSE&&(!KEYS.get().add(key)||Thread.currentThread().getName().startsWith("tf2-diagnostic"))){STACK.get().push(SKIP);return;}STACK.get().push(new Span(key));}
 public static void end(){Deque<Span>s=STACK.get();if(s.isEmpty())throw new IllegalStateException("Diagnostic span underflow");Span v=s.pop();if(v==SKIP)return;if(COARSE)KEYS.get().remove(v.key);long w=System.nanoTime()-v.wall,c=CPU.getCurrentThreadCpuTime()-v.cpu;if(!s.isEmpty()){for(Span p:s)if(p!=SKIP){p.childWall+=w;p.childCpu+=c;break;}}long[]t=TIMES.computeIfAbsent(v.key,k->new long[5]);synchronized(t){t[0]++;t[1]+=w;t[2]+=c;t[3]+=w-v.childWall;t[4]+=c-v.childCpu;}}
 public static Object reflectGet(java.lang.reflect.Field f,Object o)throws IllegalAccessException{begin("raw_reflective_field_get");try{return f.get(o);}finally{end();}}
 public static Object reflectGetQualification(java.lang.reflect.Field f,Object o)throws IllegalAccessException{begin("qualification_field_read");try{return f.get(o);}finally{end();}}
 public static java.lang.reflect.Field lookup(Class c,String name)throws NoSuchFieldException{begin("metadata_declared_field_lookup");try{return c.getDeclaredField(name);}finally{end();}}
 public static void write(java.io.BufferedWriter w,String s)throws java.io.IOException{begin("buffered_write");try{w.write(s);}finally{end();}}
 public static void newline(java.io.BufferedWriter w)throws java.io.IOException{begin("buffered_newline");try{w.newLine();}finally{end();}}
 public static void flush(java.io.BufferedWriter w)throws java.io.IOException{begin("buffered_flush");try{w.flush();}finally{end();}}
 static String group(String c,String n){
  if(COARSE&&c.equals("SourceLocalityHooks")&&Arrays.asList("begin","mapper","reader","decoded","returned","complete","cacheOperations").contains(n))return "required_RPC_locality_qualification";
  if(COARSE&&c.equals("SqlResultLocalityHooks")&&Arrays.asList("begin","complete","handlerBegin","mapperInvoker").contains(n))return "required_SQL_locality_qualification";
  if(COARSE&&c.equals("PlannedServiceAgent$Recorder")&&Arrays.asList("row","value","id").contains(n))return null;
  if(c.equals("tracefusion/internal/jackson/databind/ObjectMapper")&&n.equals("writeValueAsString"))return "json_encoding";
  if(c.equals("JsonTreeObservationHooks")&&Arrays.asList("elements","entries","get").contains(n))return "raw_container_and_field_read";
  if((c.equals("JsonTreeObservationHooks")&&Arrays.asList("field","check").contains(n))||(c.equals("ResponseBindingHooks")&&Arrays.asList("field","checkWrapper","mapWrapper").contains(n))||c.equals("JdkContractProbe")&&n.equals("selected"))return "metadata_and_qualification";
  if(c.equals("JsonTreeObservationHooks$Snapshot")&&n.equals("verify"))return "structure_recheck";
  if(c.equals("ResponseBindingHooks")&&n.equals("walk"))return "snapshot_and_binding";
  if(c.equals("PlannedServiceAgent$Recorder")&&Arrays.asList("row","value","field","fieldVersion","fieldVersionRecord","branch","safeEvent").contains(n))return "evidence_and_state";
  if(c.equals("PlannedServiceAgent$Recorder")&&n.equals("emit"))return "emit_state_encode_write";
  if(c.equals("PlannedServiceAgent$Recorder")&&n.equals("id"))return "identity_and_state";
  if(c.equals("BodyObservationHooks")&&Arrays.asList("observe","omitRead","omitBranch").contains(n))return "body_guard_and_state";
  return null;
 }
 static InsnList call(String n,String value){InsnList x=new InsnList();if(value!=null)x.add(new LdcInsnNode(value));x.add(new MethodInsnNode(INVOKESTATIC,"PruningCostProbeAgent",n,value==null?"()V":"(Ljava/lang/String;)V",false));return x;}
 public static void premain(String path,Instrumentation inst){
  if(CPU.isThreadCpuTimeSupported()&&!CPU.isThreadCpuTimeEnabled())CPU.setThreadCpuTimeEnabled(true);
  Runtime.getRuntime().addShutdownHook(new Thread(()->{try{StringBuilder s=new StringBuilder("{\"diagnostic_only\":true,\"columns\":[\"calls\",\"inclusive_wall_ns\",\"inclusive_cpu_ns\",\"self_wall_ns\",\"self_cpu_ns\"],\"methods\":{");boolean first=true;for(String k:new TreeSet<>(TIMES.keySet())){if(!first)s.append(',');first=false;s.append('"').append(k).append("\":").append(Arrays.toString(TIMES.get(k)));}s.append("}}\n");Files.write(Paths.get(path),s.toString().getBytes("UTF-8"));}catch(Exception e){throw new IllegalStateException(e);}},"tf2-cost-probe-shutdown"));
  inst.addTransformer(new ClassFileTransformer(){public byte[] transform(ClassLoader l,String name,Class<?> old,ProtectionDomain domain,byte[] bytes){
   if(!(name.startsWith("JsonTreeObservationHooks")||name.equals("ResponseBindingHooks")||name.equals("JdkContractProbe")||name.equals("PlannedServiceAgent$Recorder")||name.equals("BodyObservationHooks")||(COARSE&&(name.equals("SourceLocalityHooks")||name.equals("SqlResultLocalityHooks")))||name.equals("tracefusion/internal/jackson/databind/ObjectMapper")))return null;
   ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);boolean changed=false;
   for(MethodNode m:c.methods){String g=group(name,m.name);if(g==null||(m.access&(ACC_NATIVE|ACC_ABSTRACT))!=0)continue;changed=true;AbstractInsnNode[] prior=m.instructions.toArray();LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode();InsnList prefix=call("begin",g+":"+name+"."+m.name+m.desc);prefix.add(start);m.instructions.insert(prefix);
    for(AbstractInsnNode n:prior)if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN)m.instructions.insertBefore(n,call("end",null));
    m.instructions.add(end);m.instructions.add(handler);int slot=m.maxLocals++;m.instructions.add(new VarInsnNode(ASTORE,slot));m.instructions.add(call("end",null));m.instructions.add(new VarInsnNode(ALOAD,slot));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,null));
   }
   for(MethodNode m:c.methods)for(AbstractInsnNode ins:m.instructions.toArray())if(ins instanceof MethodInsnNode){MethodInsnNode x=(MethodInsnNode)ins;String n=null,d=null;
    if(!name.startsWith("tracefusion/")&&x.owner.equals("java/lang/reflect/Field")&&x.name.equals("get")&&x.desc.equals("(Ljava/lang/Object;)Ljava/lang/Object;")){n=COARSE&&(name.equals("SourceLocalityHooks")||name.equals("SqlResultLocalityHooks")||name.equals("ResponseBindingHooks")&&m.name.equals("member"))?"reflectGetQualification":"reflectGet";d="(Ljava/lang/reflect/Field;Ljava/lang/Object;)Ljava/lang/Object;";}
    else if(!name.startsWith("tracefusion/")&&x.owner.equals("java/lang/Class")&&x.name.equals("getDeclaredField")){n="lookup";d="(Ljava/lang/Class;Ljava/lang/String;)Ljava/lang/reflect/Field;";}
    else if(name.equals("PlannedServiceAgent$Recorder")&&m.name.equals("emit")&&x.owner.equals("java/io/BufferedWriter")){
     if(x.name.equals("write")&&x.desc.equals("(Ljava/lang/String;)V")){n="write";d="(Ljava/io/BufferedWriter;Ljava/lang/String;)V";}
     if(x.name.equals("newLine")||x.name.equals("flush")){n=x.name.equals("flush")?"flush":"newline";d="(Ljava/io/BufferedWriter;)V";}
    }
    if(n!=null){changed=true;m.instructions.set(x,new MethodInsnNode(INVOKESTATIC,"PruningCostProbeAgent",n,d,false));}
   }
   if(!changed)return null;ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_FRAMES|ClassWriter.COMPUTE_MAXS){protected String getCommonSuperClass(String a,String b){try{Class<?>x=Class.forName(a.replace('/','.'),false,l),y=Class.forName(b.replace('/','.'),false,l);if(x.isAssignableFrom(y))return a;if(y.isAssignableFrom(x))return b;if(x.isInterface()||y.isInterface())return "java/lang/Object";do{x=x.getSuperclass();}while(!x.isAssignableFrom(y));return x.getName().replace('.','/');}catch(Throwable e){return "java/lang/Object";}}};c.accept(w);return w.toByteArray();
  }});
 }
}
