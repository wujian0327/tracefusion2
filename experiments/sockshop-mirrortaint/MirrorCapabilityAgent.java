import java.lang.instrument.*;
import java.security.ProtectionDomain;
import java.util.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.lang.reflect.Field;
import com.google.gson.*;
import com.shadow.taint.agent.runtime.*;
import com.shadow.taint.agent.model.A;
import org.stack.taint.asm.*;
import org.stack.taint.asm.tree.*;

/** Boundary configuration and native-label export ONLY. No dependency inference. */
public final class MirrorCapabilityAgent implements ClassFileTransformer, Opcodes {
    static String entry, prefix;
    static Set<String> sources = new HashSet<String>();
    static final ThreadLocal<String> ROOT = new ThreadLocal<String>();
    static final ThreadLocal<Integer> CALL = new ThreadLocal<Integer>();
    static final ThreadLocal<String> ATOMIC_SOURCE = new ThreadLocal<String>();
    static final java.util.concurrent.ConcurrentHashMap<String,String> REQUEST_ROOTS=new java.util.concurrent.ConcurrentHashMap<String,String>();
    static final java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicInteger> COUNTS=new java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicInteger>();
    static long seq;
    static Path log;
    public static void premain(String arg, Instrumentation inst) throws Exception {
        if("transport".equals(arg)){MirrorCapabilityTransport.premain(arg,inst);return;}
        JsonObject c = new JsonParser().parse(new String(Files.readAllBytes(Paths.get(System.getProperty("capability.config"))),StandardCharsets.UTF_8)).getAsJsonObject();
        entry=c.get("entry").getAsString(); prefix=c.get("prefix").getAsString();
        for(JsonElement s:c.getAsJsonArray("source_calls"))sources.add(s.getAsString());
        log=Paths.get(System.getProperty("capability.events"));
        inst.addTransformer(new MirrorCapabilityAgent());
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable(){public void run(){emit("closed",new LinkedHashMap<String,Object>());}}));
    }
    static void pushString(InsnList x,String s){x.add(new LdcInsnNode(s));}
    static void box(InsnList x,Type t){
        String o=null;
        switch(t.getSort()){
        case Type.BOOLEAN:o="java/lang/Boolean";break;case Type.BYTE:o="java/lang/Byte";break;
        case Type.CHAR:o="java/lang/Character";break;case Type.SHORT:o="java/lang/Short";break;
        case Type.INT:o="java/lang/Integer";break;case Type.FLOAT:o="java/lang/Float";break;
        case Type.LONG:o="java/lang/Long";break;case Type.DOUBLE:o="java/lang/Double";break;}
        if(o!=null)x.add(new MethodInsnNode(INVOKESTATIC,o,"valueOf","("+t.getDescriptor()+")L"+o+";",false));
    }
    static void args(InsnList h,MethodNode m){
        Type[] ts=Type.getArgumentTypes(m.desc);h.add(new LdcInsnNode(ts.length));h.add(new TypeInsnNode(ANEWARRAY,"java/lang/Object"));
        int slot=(m.access&ACC_STATIC)==0?1:0;
        for(int i=0;i<ts.length;i++){h.add(new InsnNode(DUP));h.add(new LdcInsnNode(i));h.add(new VarInsnNode(ts[i].getOpcode(ILOAD),slot));box(h,ts[i]);h.add(new InsnNode(AASTORE));slot+=ts[i].getSize();}
    }
    public byte[] transform(ClassLoader loader,String owner,Class<?> prior,ProtectionDomain pd,byte[] bytes){
        if(owner==null||!owner.startsWith(prefix))return null;
        try{
            ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,0);boolean changed=false;
            if(entry.startsWith(owner+"."))Files.write(log.getParent().resolve("native-root-before-export.class"),bytes);
            for(MethodNode m:c.methods){
                boolean root=(owner+"."+m.name+m.desc).equals(entry);
                AbstractInsnNode[] original=m.instructions.toArray();
                boolean nativeCollector=false;
                if(root)for(AbstractInsnNode n:original)if(n instanceof MethodInsnNode){MethodInsnNode i=(MethodInsnNode)n;if(i.owner.equals("com/shadow/taint/agent/runtime/TaintCollector")&&i.name.equals("collect")&&i.desc.equals("(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V"))nativeCollector=true;}
                if(root){
                    InsnList h=new InsnList();args(h,m);h.add(new MethodInsnNode(INVOKESTATIC,"MirrorCapabilityAgent","begin","([Ljava/lang/Object;)V",false));
                    AbstractInsnNode after=null;
                    for(AbstractInsnNode n:original)if(n instanceof MethodInsnNode){MethodInsnNode i=(MethodInsnNode)n;if(i.owner.equals("com/shadow/taint/agent/runtime/TaintTagger")&&(i.name.equals("tagFacade")||i.name.equals("tagGateway")))after=n;}
                    if(after==null)m.instructions.insert(h);else m.instructions.insert(after,h);
                    System.err.println("MT_CAPABILITY root="+entry+" afterFacade="+(after!=null));changed=true;
                }
                for(AbstractInsnNode n:original){
                    if(root&&!nativeCollector&&n.getOpcode()==ARETURN){InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new MethodInsnNode(INVOKESTATIC,"MirrorCapabilityAgent","returned","(Ljava/lang/Object;)V",false));m.instructions.insertBefore(n,h);}
                    if(!(n instanceof MethodInsnNode))continue;
                    MethodInsnNode i=(MethodInsnNode)n;String key=i.owner+"."+i.name+i.desc;
                    if(!root&&i.owner.equals("com/shadow/taint/agent/runtime/TaintCollector")&&i.name.equals("collect")&&i.desc.equals("(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V")){
                        InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new MethodInsnNode(INVOKESTATIC,"MirrorCapabilityAgent","checkpoint","(Ljava/lang/Object;)V",false));m.instructions.insertBefore(n,h);changed=true;
                    }
                    if(root&&i.owner.equals("com/shadow/taint/agent/runtime/TaintCollector")&&i.name.equals("collect")&&i.desc.equals("(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V")){
                        InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new MethodInsnNode(INVOKESTATIC,"MirrorCapabilityAgent","returned","(Ljava/lang/Object;)V",false));m.instructions.insertBefore(n,h);
                    }
                    if(!sources.contains(key))continue;
                    Type r=Type.getReturnType(i.desc);if(r.getSort()!=Type.OBJECT&&r.getSort()!=Type.ARRAY)throw new IllegalStateException("non-reference source "+key);
                    InsnList h=new InsnList();h.add(new InsnNode(DUP));pushString(h,key);h.add(new MethodInsnNode(INVOKESTATIC,"MirrorCapabilityAgent","source","(Ljava/lang/Object;Ljava/lang/String;)V",false));m.instructions.insert(n,h);changed=true;
                }
            }
            if(!changed)return null;
            ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS);c.accept(w);return w.toByteArray();
        }catch(Throwable t){Map<String,Object> e=new LinkedHashMap<String,Object>();e.put("class",owner);e.put("error",t.toString());emit("problem",e);return null;}
    }
    static synchronized void emit(String kind,Map<String,Object> row){
        try{row.put("kind",kind);row.put("seq",++seq);row.put("thread",Thread.currentThread().getId());row.put("root",ROOT.get());row.put("native_available",TaintHeap.available());
            row.put("context","closed".equals(kind)?Collections.emptyMap():MirrorCapabilityTransport.currentContext());
            Files.write(log,(new GsonBuilder().serializeNulls().create().toJson(row)+"\n").getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        }catch(Throwable t){System.err.println("MT_CAPABILITY_FATAL "+t);}
    }
    static boolean leaf(Object x){return x==null||x instanceof String||x instanceof Number||x instanceof Boolean||x instanceof Character||x instanceof Date||x instanceof UUID||x instanceof java.net.URI;}
    static List<String> ids(A a){List<String> ids=new ArrayList<String>();if(a!=null&&a.A()!=null)for(com.shadow.taint.agent.model.C s:a.A())ids.add(s.C());return ids;}
    static String esc(String x){return x.replace("~","~0").replace("/","~1");}
    static Object jsonValue(Object x){if(x==null||x instanceof Number||x instanceof Boolean||x instanceof String)return x;if(x instanceof Date)return ((Date)x).getTime();return String.valueOf(x);}
    static void walk(Object value,Object parent,Field field,String path,List<Object> result,IdentityHashMap<Object,Boolean> active,int depth)throws Exception{
        if(depth>18||result.size()>20000)throw new IllegalStateException("snapshot bound");
        if(leaf(value)){
            Map<String,Object> f=new LinkedHashMap<String,Object>();f.put("path",path);f.put("value",jsonValue(value));
            if(value instanceof UUID&&ATOMIC_SOURCE.get()!=null){
                A prior=TaintHeap.queryTaint(value);
                if(prior==null||prior.A()==null||prior.A().isEmpty())
                    TaintTagger.tagManually(value,ATOMIC_SOURCE.get()+"/immutable-uuid"+path);
            }
            A tag=field!=null&&field.getType().isPrimitive()?TaintHeap.queryPrimitiveFieldTaint(parent,field.getName()):TaintHeap.queryTaint(value);
            f.put("tag_present",tag!=null);f.put("native_ids",ids(tag));
            if(field!=null)f.putAll(MirrorCapabilityTransport.fieldCoordinate(parent,field.getDeclaringClass().getName().replace('.','/')+"."+field.getName()));
            else if(parent!=null){Map<String,Object> coord=MirrorCapabilityTransport.fieldCoordinate(parent,(parent instanceof Map?"@map:":"@list:")+path.substring(path.lastIndexOf('/')+1));f.putAll(coord);}
            result.add(f);return;
        }
        if(active.put(value,true)!=null)throw new IllegalStateException("cyclic snapshot at "+path);
        try{
            if(value instanceof List){int i=0;for(Object item:(List<?>)value)walk(item,value,null,path+"/"+i++,result,active,depth+1);return;}
            if(value instanceof Map){for(Map.Entry<?,?> e:((Map<?,?>)value).entrySet()){if(!(e.getKey() instanceof String))throw new IllegalStateException("nonstring Map key");walk(e.getValue(),value,null,path+"/"+esc((String)e.getKey()),result,active,depth+1);}return;}
            String name=value.getClass().getName();
            if(name.equals("org.springframework.http.ResponseEntity")){walk(value.getClass().getMethod("getBody").invoke(value),null,null,path+"/body",result,active,depth+1);return;}
            if(name.equals("org.springframework.hateoas.Resource")){walk(value.getClass().getMethod("getContent").invoke(value),null,null,path+"/content",result,active,depth+1);return;}
            if(name.startsWith("java."))throw new IllegalStateException("unmodeled snapshot type "+name);
            for(Class<?> c=value.getClass();c!=null&&c!=Object.class;c=c.getSuperclass())for(Field f:c.getDeclaredFields()){
                if(java.lang.reflect.Modifier.isStatic(f.getModifiers())||f.isSynthetic())continue;f.setAccessible(true);walk(f.get(value),value,f,path+"/"+esc(f.getName()),result,active,depth+1);
            }
        }finally{active.remove(value);}
    }
    static List<Object> snapshot(Object x)throws Exception{List<Object> r=new ArrayList<Object>();walk(x,null,null,"",r,new IdentityHashMap<Object,Boolean>(),0);return r;}
    public static void begin(Object[] args){
        ROOT.set(UUID.randomUUID().toString());CALL.set(0);
        try{
            COUNTS.put(ROOT.get(),new java.util.concurrent.atomic.AtomicInteger());
            Object message=MirrorCapabilityTransport.currentContext().get("message");
            if(message!=null&&REQUEST_ROOTS.putIfAbsent(message.toString(),ROOT.get())!=null)throw new IllegalStateException("overlapping root for concrete request");
            if(!TaintHeap.available())TaintHeap.startup();
            for(int i=0;i<args.length;i++){
                Object a=args[i];if(a!=null&&a.getClass().getName().equals("org.springframework.http.HttpHeaders"))continue;
                source(a,"@argument:"+i);
            }
            emit("root-enter",new LinkedHashMap<String,Object>());
        }catch(Throwable t){problem(t);}
    }
    static void problem(Throwable t){Map<String,Object> r=new LinkedHashMap<String,Object>();r.put("error",t.toString());emit("problem",r);}
    public static void source(Object value,String call){
        boolean borrowed=false;
        try{
            if(ROOT.get()==null){Object message=MirrorCapabilityTransport.currentContext().get("message");String root=message==null?null:REQUEST_ROOTS.get(message.toString());if(root==null)return;ROOT.set(root);borrowed=true;}
            java.util.concurrent.atomic.AtomicInteger counter=COUNTS.get(ROOT.get());if(counter==null)throw new IllegalStateException("source outside open request");
            int ordinal=counter.incrementAndGet();String label="capability/"+ROOT.get()+"/"+ordinal;
            // Native public API creates source labels. No expected origin list is consulted.
            TaintTagger.tagDbQueryResult("capability",label,value);
            Map<String,Object> r=new LinkedHashMap<String,Object>();r.put("call",call);r.put("ordinal",ordinal);r.put("label",label);
            ATOMIC_SOURCE.set(label);try{r.put("fields",snapshot(value));}finally{ATOMIC_SOURCE.remove();}emit("source",r);
        }catch(Throwable t){problem(t);}finally{ATOMIC_SOURCE.remove();if(borrowed)ROOT.remove();}
    }
    public static void returned(Object value){
        try{Map<String,Object> r=new LinkedHashMap<String,Object>();r.put("fields",snapshot(value));emit("target",r);}catch(Throwable t){problem(t);}
        finally{String root=ROOT.get();if(root!=null){COUNTS.remove(root);for(Map.Entry<String,String> e:REQUEST_ROOTS.entrySet())if(e.getValue().equals(root))REQUEST_ROOTS.remove(e.getKey(),root);}ROOT.remove();CALL.remove();}
    }
    public static void checkpoint(Object value){
        if(ROOT.get()==null||!TaintHeap.available())return;
        try{Map<String,Object> r=new LinkedHashMap<String,Object>();r.put("fields",snapshot(value));r.put("basis","existing-native-collector-before-shutdown");emit("native-observation",r);}catch(Throwable t){problem(t);}
    }
}
