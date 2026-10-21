import java.io.*;
import java.lang.instrument.*;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Frozen-plan observation only; provenance computation runs offline. */
public final class PlannedServiceAgent implements ClassFileTransformer,Opcodes {
    static final String R="PlannedServiceAgent$Recorder";
    static Map<String,Object> plan;static Map<String,String> hashes;
    static Set<String> frames,tracked;static boolean full,boundary;static String mode;
    public static void premain(String args,Instrumentation instrumentation)throws Exception {
        plan=new ObjectMapper().readValue(new File(System.getProperty("service.plan")),Map.class);
        hashes=(Map<String,String>)plan.get("class_sha256");frames=new HashSet<>((List<String>)plan.get("frame_methods"));
        tracked=new HashSet<>((List<String>)plan.get("snapshot_fields"));
        mode=System.getProperty("service.mode","selective");if(!Arrays.asList("full","selective","boundary").contains(mode))throw new IllegalArgumentException("Unknown mode");full=mode.equals("full");boundary=mode.equals("boundary");
        // HTTP field coordinates still need the same admitted DTO write counts.
        // Boundary mode removes internal dependency evidence, not those counts.
        if(boundary)frames.clear();
        Recorder.start();instrumentation.addTransformer(new PlannedServiceAgent());
    }
    public byte[] transform(final ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes) {
        if(!hashes.containsKey(owner))return null;
        try {
            if(!Recorder.hash(bytes).equals(hashes.get(owner)))throw new IllegalStateException("Frozen class changed: "+owner);
            ClassNode cls=new ClassNode(ASM9);new ClassReader(bytes).accept(cls,ClassReader.EXPAND_FRAMES);boolean changed=false;
            for(MethodNode m:cls.methods) {
                if((m.access&(ACC_ABSTRACT|ACC_NATIVE))!=0)continue;String key=owner+"."+m.name+m.desc;
                List<AbstractInsnNode> code=new ArrayList<>();for(AbstractInsnNode n:m.instructions.toArray())if(n.getOpcode()>=0)code.add(n);
                if(CollectionServiceHooks.instrument(m,key,code))changed=true;
                if(ExecutionKernelHooks.instrument(m,key,code))changed=true;
                if(ResponseBindingHooks.instrument(m,key,code))changed=true;
                boolean initialized=!m.name.equals("<init>");AbstractInsnNode entry=null;
                for(int i=0;i<code.size();i++) {
                    AbstractInsnNode n=code.get(i);String site=key+"@"+i;
                    if(!initialized&&n instanceof MethodInsnNode){MethodInsnNode c=(MethodInsnNode)n;if(c.getOpcode()==INVOKESPECIAL&&c.name.equals("<init>")&&(c.owner.equals(owner)||c.owner.equals(cls.superName))){initialized=true;entry=n;continue;}}
                    if(!initialized)continue;
                    if(n instanceof FieldInsnNode) {
                        FieldInsnNode f=(FieldInsnNode)n;String field=f.owner+"."+f.name;
                        boolean write=f.getOpcode()==PUTFIELD,read=!boundary&&f.getOpcode()==GETFIELD&&(full||((List)plan.getOrDefault("selected_read_sites",Collections.emptyList())).contains(site));
                        if((write&&(tracked.contains(field)||full))||read){field(m,f,site,write,full||read||field.equals(plan.get("target"))||ExecutionKernelHooks.enabled());changed=true;}
                    }
                    if(!boundary&&(site.equals(plan.get("producer_callsite"))||site.equals(plan.get("writer_site"))||((List)plan.getOrDefault("binding_callsites",Collections.emptyList())).contains(site))) {
                        InsnList h=new InsnList();h.add(new LdcInsnNode(site));h.add(new MethodInsnNode(INVOKESTATIC,R,"callsite","(Ljava/lang/String;)V",false));m.instructions.insertBefore(n,h);changed=true;
                    }
                    if(!boundary&&site.equals(((Map)plan.get("reduction")).get("site"))) {
                        InsnList a=new InsnList();a.add(new InsnNode(DUP));a.add(new MethodInsnNode(INVOKESTATIC,R,"sumStart","(Ljava/lang/Object;)V",false));m.instructions.insertBefore(n,a);
                        InsnList b=new InsnList();b.add(new InsnNode(DUP2));b.add(new MethodInsnNode(INVOKESTATIC,R,"sumEnd","(D)V",false));m.instructions.insert(n,b);changed=true;
                    }
                    if(full&&n instanceof JumpInsnNode&&n.getOpcode()!=GOTO) {
                        JumpInsnNode j=(JumpInsnNode)n;LabelNode original=j.label,taken=new LabelNode(),next=new LabelNode();j.label=taken;InsnList h=new InsnList();branch(h,site,false);h.add(new JumpInsnNode(GOTO,next));h.add(taken);branch(h,site,true);h.add(new JumpInsnNode(GOTO,original));h.add(next);m.instructions.insert(n,h);changed=true;
                    }
                }
                if(frames.contains(key)) {
                    if(!initialized)throw new IllegalStateException("Uninitialized framed constructor");
                    InsnList h=new InsnList();h.add(new LdcInsnNode(key));h.add((m.access&ACC_STATIC)!=0?new InsnNode(ACONST_NULL):new VarInsnNode(ALOAD,0));arguments(h,m);h.add(new MethodInsnNode(INVOKESTATIC,R,"enter","(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)V",false));LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode();h.add(start);
                    if(entry==null)m.instructions.insert(h);else m.instructions.insert(entry,h);
                    for(AbstractInsnNode n:code)if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN) {
                        InsnList e=new InsnList();Type t=Type.getReturnType(m.desc);if(t.getSort()==Type.VOID)e.add(new InsnNode(ACONST_NULL));else{e.add(new InsnNode(t.getSize()==2?DUP2:DUP));box(e,t);}e.add(new MethodInsnNode(INVOKESTATIC,R,"exit","(Ljava/lang/Object;)V",false));m.instructions.insertBefore(n,e);
                    }
                    m.instructions.add(end);m.instructions.add(handler);int error=m.maxLocals++;m.instructions.add(new VarInsnNode(ASTORE,error));m.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"abort","()V",false));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));changed=true;
                }
            }
            Recorder.transformed(owner);
            if(!changed)return null;
            ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return commonType(loader,a,b);}};cls.accept(w);return w.toByteArray();
        }catch(Throwable e){Recorder.problem("transform:"+owner+":"+e);return null;}
    }
    // Loading application classes during another transform suppresses recursive
    // transformation. Read hierarchy bytes instead, so required write counters
    // cannot silently disappear when frame computation sees a DTO type.
    static ClassReader hierarchy(ClassLoader loader,String name){try(InputStream in=loader==null?ClassLoader.getSystemResourceAsStream(name+".class"):loader.getResourceAsStream(name+".class")){if(in==null)throw new IllegalStateException("Missing hierarchy: "+name);return new ClassReader(in);}catch(IOException e){throw new IllegalStateException(e);}}
    static boolean assignable(ClassLoader loader,String target,String from,Set<String> seen){if(target.equals(from)||target.equals("java/lang/Object"))return true;if(!seen.add(from))return false;ClassReader r=hierarchy(loader,from);for(String i:r.getInterfaces())if(assignable(loader,target,i,seen))return true;return r.getSuperName()!=null&&assignable(loader,target,r.getSuperName(),seen);}
    static String commonType(ClassLoader loader,String a,String b){
        if(a.equals(b))return a;
        if(a.equals("java/lang/Object")||b.equals("java/lang/Object"))return "java/lang/Object";
        if(a.startsWith("[")||b.startsWith("[")){
            if(a.startsWith("[")&&b.startsWith("[")){
                String x=a.substring(1),y=b.substring(1);if(x.length()==1||y.length()==1)return "java/lang/Object";
                String inner=commonType(loader,x.startsWith("L")?x.substring(1,x.length()-1):x,y.startsWith("L")?y.substring(1,y.length()-1):y);
                return inner.startsWith("[")?"["+inner:"[L"+inner+";";
            }
            String other=a.startsWith("[")?b:a;
            return other.equals("java/lang/Cloneable")||other.equals("java/io/Serializable")?other:"java/lang/Object";
        }
        if(assignable(loader,a,b,new HashSet<>()))return a;if(assignable(loader,b,a,new HashSet<>()))return b;
        if((hierarchy(loader,a).getAccess()&ACC_INTERFACE)!=0||(hierarchy(loader,b).getAccess()&ACC_INTERFACE)!=0)return "java/lang/Object";
        do{a=hierarchy(loader,a).getSuperName();}while(a!=null&&!assignable(loader,a,b,new HashSet<>()));
        return a==null?"java/lang/Object":a;
    }
    static void branch(InsnList h,String site,boolean taken){h.add(new LdcInsnNode(site));h.add(new InsnNode(taken?ICONST_1:ICONST_0));h.add(new MethodInsnNode(INVOKESTATIC,R,"branch","(Ljava/lang/String;Z)V",false));}
    static void field(MethodNode m,FieldInsnNode f,String site,boolean write,boolean log) {
        Type t=Type.getType(f.desc);int object=m.maxLocals++,value=m.maxLocals;m.maxLocals+=t.getSize();InsnList a=new InsnList(),b=new InsnList();
        if(write){a.add(new VarInsnNode(t.getOpcode(ISTORE),value));a.add(new VarInsnNode(ASTORE,object));a.add(new VarInsnNode(ALOAD,object));a.add(new VarInsnNode(t.getOpcode(ILOAD),value));}
        else{a.add(new InsnNode(DUP));a.add(new VarInsnNode(ASTORE,object));b.add(new InsnNode(t.getSize()==2?DUP2:DUP));b.add(new VarInsnNode(t.getOpcode(ISTORE),value));}
        b.add(new VarInsnNode(ALOAD,object));b.add(new LdcInsnNode(f.owner+"."+f.name));b.add(new VarInsnNode(t.getOpcode(ILOAD),value));box(b,t);b.add(new LdcInsnNode(site));b.add(new InsnNode(write?ICONST_1:ICONST_0));b.add(new InsnNode(log?ICONST_1:ICONST_0));b.add(new MethodInsnNode(INVOKESTATIC,R,"field","(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/Object;Ljava/lang/String;ZZ)V",false));m.instructions.insertBefore(f,a);m.instructions.insert(f,b);
    }
    static void arguments(InsnList h,MethodNode m){Type[] ts=Type.getArgumentTypes(m.desc);h.add(new LdcInsnNode(ts.length));h.add(new TypeInsnNode(ANEWARRAY,"java/lang/Object"));int slot=(m.access&ACC_STATIC)!=0?0:1;for(int i=0;i<ts.length;i++){h.add(new InsnNode(DUP));h.add(new LdcInsnNode(i));h.add(new VarInsnNode(ts[i].getOpcode(ILOAD),slot));box(h,ts[i]);h.add(new InsnNode(AASTORE));slot+=ts[i].getSize();}}
    static void box(InsnList h,Type t){String[] ws={null,"Boolean","Character","Byte","Short","Integer","Float","Long","Double"};if(t.getSort()>=1&&t.getSort()<=8){String o="java/lang/"+ws[t.getSort()];h.add(new MethodInsnNode(INVOKESTATIC,o,"valueOf","("+t.getDescriptor()+")L"+o+";",false));}}
    public static final class Recorder {
        static final ObjectMapper JSON=new ObjectMapper();static BufferedWriter output;static long seq,framesCounter,fieldHooks,branches;
        static final IdentityHashMap<Object,String> IDS=new IdentityHashMap<>();static final Map<String,Integer> VERSIONS=new HashMap<>();
        static final Set<String> CHECKED_CLASSES=new HashSet<>();
        static final ThreadLocal<Deque<Frame>> STACK=new ThreadLocal<Deque<Frame>>(){protected Deque<Frame> initialValue(){return new ArrayDeque<>();}};
        static final ThreadLocal<String> PENDING=new ThreadLocal<>();static final Map<String,Set<String>> ACTIVE=new HashMap<>();
        static class Frame{String id,method;List<String> locked=new ArrayList<>();List<Object> inputs;}
        static String id(Object o){if(o==null)return null;String s=IDS.get(o);if(s==null){if(IDS.size()>100000)throw new IllegalStateException("Object bound");s="o"+(IDS.size()+1);IDS.put(o,s);}return s;}
        static Map<String,Object> row(){Map<String,Object> r=new LinkedHashMap<>();r.put("frame",STACK.get().isEmpty()?null:STACK.get().peek().id);return r;}
        static Map<String,Object> value(Object o){Map<String,Object> r=new LinkedHashMap<>();r.put("object",id(o));if(TemporalDateHooks.date(o))return TemporalDateHooks.observe((java.util.Date)o);if(o instanceof Character&&ExecutionKernelHooks.extended())r.put("value",(int)((Character)o).charValue());else if(o==null||o instanceof Number||o instanceof String||o instanceof Boolean)r.put("value",o);return r;}
        static String hash(byte[] data)throws Exception{StringBuilder s=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(data))s.append(String.format("%02x",b&255));return s.toString();}
        public static synchronized void start()throws Exception{output=Files.newBufferedWriter(Paths.get(System.getProperty("service.events")),StandardOpenOption.CREATE_NEW);Map<String,Object> r=row();r.put("mode",mode);r.put("plan_sha256",hash(Files.readAllBytes(Paths.get(System.getProperty("service.plan")))));emit("start",r);Runtime.getRuntime().addShutdownHook(new Thread(()->{synchronized(Recorder.class){Map<String,Object> m=row();m.put("field_hook_calls",fieldHooks);m.put("branch_hook_calls",branches);emit("metrics",m);}}));}
        public static synchronized void callsite(String site){if(!STACK.get().isEmpty())PENDING.set(site);}
        static List<Object> snapshot(Object o,boolean target)throws Exception{
            List<Object> out=new ArrayList<>();if(o==null)return out;Set<String> wanted=new HashSet<>((List<String>)plan.get(target?"snapshot_fields":full?"full_snapshot_fields":"mapper_fields"));
            for(Class<?> c=o.getClass();c!=null&&c!=Object.class;c=c.getSuperclass())for(Field f:c.getDeclaredFields()) {
                String name=c.getName().replace('.','/')+"."+f.getName();if(Modifier.isStatic(f.getModifiers())||!wanted.contains(name))continue;f.setAccessible(true);
                Map<String,Object> r=new LinkedHashMap<>();r.put("owner",id(o));r.put("field",name);r.put("version",VERSIONS.getOrDefault(id(o)+":"+name,0));r.put("observed",value(f.get(o)));out.add(r);
            }return out;
        }
        public static synchronized void enter(String method,Object self,Object[] args){try{
            Frame f=new Frame();f.id="f"+(++framesCounter);f.method=method;Map<String,Object> r=row();r.put("parent",r.get("frame"));r.put("frame",f.id);r.put("method",method);r.put("receiver",id(self));r.put("callsite",PENDING.get());PENDING.remove();List<Object> vs=new ArrayList<>();for(Object a:args)vs.add(value(a));r.put("args",vs);ExecutionKernelHooks.callbackSite(r);AsyncTaskHooks.frame(r);
            if(method.equals(plan.get("entry")))try{r.put("trace_id",Class.forName("org.slf4j.MDC",false,Thread.currentThread().getContextClassLoader()).getMethod("get",String.class).invoke(null,"X-B3-TraceId"));}catch(Exception ignored){}
            if(method.equals(plan.get("entry"))&&"identity-return".equals(plan.get("profile"))){Object a=args[((Number)plan.get("input_argument")).intValue()];if(a==null||!a.getClass().getName().replace('.','/').equals(plan.get("input_owner")))throw new IllegalStateException("Runtime input DTO differs");r.put("input_object",id(a));r.put("input_fields",snapshot(a,true));Set<String> users=ACTIVE.computeIfAbsent(id(a),k->new HashSet<>());if(!users.isEmpty())throw new IllegalStateException("Shared active input DTO");users.add(f.id);f.locked.add(id(a));}
            if(method.equals(plan.get("producer_method"))) {
                int index=((Number)((Map)plan.get("reduction")).get("input_argument")).intValue();Object a=args[index];if(!(a instanceof List))throw new IllegalStateException("Only ordered List reduction supported");
                List<Object> inputs=new ArrayList<>();for(Object member:(List<?>)a){if(inputs.size()>=10000)throw new IllegalStateException("Collection bound");if(member==null||!member.getClass().getName().replace('.','/').equals(plan.get("mapper_owner")))throw new IllegalStateException("Runtime mapper DTO differs");Map<String,Object> v=new LinkedHashMap<>();v.put("object",id(member));v.put("fields",snapshot(member,false));inputs.add(v);}
                f.inputs=inputs;r.put("inputs",inputs);for(Object member:(List<?>)a){String o=id(member);Set<String> users=ACTIVE.computeIfAbsent(o,k->new HashSet<>());if(!users.isEmpty()&&!users.contains(f.id))throw new IllegalStateException("Concurrent shared mapper DTO");users.add(f.id);f.locked.add(o);}
            }
            STACK.get().push(f);emit("enter",r);
            if(method.equals(plan.get("entry")))ResponseBindingHooks.enter(args);
        }catch(Throwable e){problem("enter:"+e);throw new IllegalStateException(e);}}
        public static synchronized void exit(Object result){try{Frame f=STACK.get().peek();Map<String,Object> r=row();r.put("result",value(result));
            if(f.method.equals(plan.get("entry"))){r.put("fields",snapshot(result,true));ResponseBindingHooks.exit(result);}
            for(String o:f.locked)ACTIVE.get(o).remove(f.id);
            emit("exit",r);STACK.get().pop();
        }catch(Throwable e){problem("exit:"+e);throw new IllegalStateException(e);}}
        public static synchronized void abort(){try{if(!STACK.get().isEmpty()){Frame f=STACK.get().peek();if(f.method.equals(plan.get("entry")))ResponseBindingHooks.abort();for(String o:f.locked)ACTIVE.get(o).remove(f.id);emit("abort",row());STACK.get().pop();}PENDING.remove();}catch(Throwable e){problem("abort:"+e);throw new IllegalStateException(e);}}
        public static synchronized void field(Object o,String field,Object v,String site,boolean write,boolean log){fieldHooks++;String key=id(o)+":"+field;int version=VERSIONS.getOrDefault(key,0);if(write){VERSIONS.put(key,++version);if(ACTIVE.containsKey(id(o))&&!ACTIVE.get(id(o)).isEmpty()){problem("Source mutated within read-only reduction epoch");throw new IllegalStateException("Source mutation");}}
            if(!STACK.get().isEmpty()&&log){Map<String,Object> r=row();r.put("owner",id(o));r.put("field",field);r.put("version",version);r.put("observed",value(v));r.put("site",site);emit(write?"write":"read",r);}}
        public static synchronized void branch(String site,boolean taken){branches++;if(!STACK.get().isEmpty()){Map<String,Object> r=row();r.put("site",site);r.put("taken",taken);emit("branch",r);}}
        public static synchronized void sumStart(Object s){Map<String,Object> r=row();r.put("parallel",((java.util.stream.DoubleStream)s).isParallel());emit("sum-enter",r);}
        public static synchronized void sumEnd(double d){Map<String,Object> r=row();r.put("value",d);emit("sum-exit",r);}
        public static synchronized void transformed(String owner){CHECKED_CLASSES.add(owner);Map<String,Object> r=row();r.put("class",owner);emit("class",r);}
        public static synchronized void problem(String message){Map<String,Object> r=row();r.put("message",message);emit("problem",r);System.err.println("QUERY_SERVICE: "+message);}
        static void emit(String kind,Map<String,Object> r){try{if(++seq>1000000)throw new IllegalStateException("Event bound");r.put("seq",seq);r.put("kind",kind);r.put("thread",Thread.currentThread().getId());output.write(JSON.writeValueAsString(r));output.newLine();output.flush();}catch(Exception e){throw new IllegalStateException(e);}}
    }
}
