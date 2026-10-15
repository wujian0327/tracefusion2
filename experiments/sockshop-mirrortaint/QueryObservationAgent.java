import java.io.*;
import java.lang.instrument.*;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Business-name-independent collector, driven exclusively by a frozen plan. */
public final class QueryObservationAgent implements ClassFileTransformer,Opcodes {
    static final String R="QueryObservationAgent$Recorder";
    static Map<String,Object> plan;
    static Set<String> sites,fields;
    static Map<String,String> hashes;
    public static void premain(String args,Instrumentation instrumentation)throws Exception {
        plan=new ObjectMapper().readValue(Paths.get(System.getProperty("query.plan")).toFile(),Map.class);
        String mode=System.getProperty("query.mode","selective");
        if(!Arrays.asList("full","selective","fixed").contains(mode))throw new IllegalArgumentException("Unknown capture mode");
        sites=new HashSet<>((List<String>)plan.get(mode.equals("full")?"full_sites":mode.equals("fixed")?"mandatory_sites":"selected_sites"));
        fields=new HashSet<>((List<String>)plan.get(mode.equals("full")?"full_snapshot_fields":"snapshot_fields"));
        hashes=(Map<String,String>)plan.get("class_sha256");Recorder.start();instrumentation.addTransformer(new QueryObservationAgent());
    }
    public byte[] transform(ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes) {
        if(owner==null||!hashes.containsKey(owner))return null;
        try {
            if(!Recorder.hash(bytes).equals(hashes.get(owner)))throw new IllegalStateException("Frozen application class differs: "+owner);
            ClassNode cls=new ClassNode(ASM9);new ClassReader(bytes).accept(cls,ClassReader.EXPAND_FRAMES);boolean changed=false;
            for(MethodNode method:cls.methods) {
                if((method.access&(ACC_ABSTRACT|ACC_NATIVE))!=0)continue;
                String key=owner+"."+method.name+method.desc;List<AbstractInsnNode> code=new ArrayList<>();
                for(AbstractInsnNode n:method.instructions.toArray())if(n.getOpcode()>=0)code.add(n);
                boolean root=key.equals(plan.get("entry"));
                for(int i=0;i<code.size();i++) {
                    AbstractInsnNode n=code.get(i);String site=key+"@"+i;
                    if(n instanceof FieldInsnNode) {
                        FieldInsnNode f=(FieldInsnNode)n;boolean read=f.getOpcode()==GETFIELD&&sites.contains(site);
                        boolean write=f.getOpcode()==PUTFIELD&&fields.contains(f.owner+"."+f.name);
                        if(read||write){observeField(method,f,site,write,sites.contains(site));changed=true;}
                    }
                    if(n instanceof JumpInsnNode&&n.getOpcode()!=GOTO&&sites.contains(site)) {
                        JumpInsnNode jump=(JumpInsnNode)n;LabelNode original=jump.label,taken=new LabelNode(),next=new LabelNode();jump.label=taken;
                        InsnList hook=new InsnList();branch(hook,site,false);hook.add(new JumpInsnNode(GOTO,next));hook.add(taken);branch(hook,site,true);hook.add(new JumpInsnNode(GOTO,original));hook.add(next);method.instructions.insert(n,hook);changed=true;
                    }
                }
                if(root) {
                    if(method.name.equals("<init>"))throw new IllegalStateException("Constructor roots unsupported");
                    InsnList enter=new InsnList();arguments(enter,method);
                    enter.add(new MethodInsnNode(INVOKESTATIC,R,"enter","([Ljava/lang/Object;)V",false));
                    LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode();enter.add(start);method.instructions.insert(enter);
                    for(AbstractInsnNode n:code)if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN) {
                        InsnList exit=new InsnList();exit.add(new MethodInsnNode(INVOKESTATIC,R,"exit","()V",false));method.instructions.insertBefore(n,exit);
                    }
                    method.instructions.add(end);method.instructions.add(handler);int error=method.maxLocals++;
                    method.instructions.add(new VarInsnNode(ASTORE,error));method.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"abort","()V",false));method.instructions.add(new VarInsnNode(ALOAD,error));method.instructions.add(new InsnNode(ATHROW));
                    method.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));changed=true;
                }
            }
            Recorder.transformed(owner,bytes);
            if(!changed)return null;
            ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_FRAMES|ClassWriter.COMPUTE_MAXS){protected String getCommonSuperClass(String a,String b){return "java/lang/Object";}};
            cls.accept(writer);return writer.toByteArray();
        }catch(Throwable error){Recorder.problem("transform:"+owner+":"+error);return null;}
    }
    static void branch(InsnList hook,String site,boolean taken){hook.add(new LdcInsnNode(site));hook.add(new InsnNode(taken?ICONST_1:ICONST_0));hook.add(new MethodInsnNode(INVOKESTATIC,R,"branch","(Ljava/lang/String;Z)V",false));}
    static void observeField(MethodNode method,FieldInsnNode f,String site,boolean write,boolean log) {
        Type type=Type.getType(f.desc);int object=method.maxLocals++,value=method.maxLocals;method.maxLocals+=type.getSize();
        InsnList before=new InsnList(),after=new InsnList();
        if(!write){before.add(new InsnNode(DUP));before.add(new VarInsnNode(ASTORE,object));after.add(new InsnNode(type.getSize()==2?DUP2:DUP));after.add(new VarInsnNode(type.getOpcode(ISTORE),value));}
        else{before.add(new VarInsnNode(type.getOpcode(ISTORE),value));before.add(new VarInsnNode(ASTORE,object));before.add(new VarInsnNode(ALOAD,object));before.add(new VarInsnNode(type.getOpcode(ILOAD),value));}
        after.add(new VarInsnNode(ALOAD,object));after.add(new LdcInsnNode(f.owner+"."+f.name));after.add(new VarInsnNode(type.getOpcode(ILOAD),value));box(after,type);after.add(new LdcInsnNode(site));after.add(new InsnNode(write?ICONST_1:ICONST_0));after.add(new InsnNode(log?ICONST_1:ICONST_0));
        after.add(new MethodInsnNode(INVOKESTATIC,R,"field","(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/Object;Ljava/lang/String;ZZ)V",false));method.instructions.insertBefore(f,before);method.instructions.insert(f,after);
    }
    static void arguments(InsnList code,MethodNode method) {
        Type[] args=Type.getArgumentTypes(method.desc);boolean stat=(method.access&ACC_STATIC)!=0;code.add(new LdcInsnNode(args.length+(stat?0:1)));code.add(new TypeInsnNode(ANEWARRAY,"java/lang/Object"));int index=0,slot=0;
        if(!stat){code.add(new InsnNode(DUP));code.add(new LdcInsnNode(index++));code.add(new VarInsnNode(ALOAD,slot++));code.add(new InsnNode(AASTORE));}
        for(Type arg:args){code.add(new InsnNode(DUP));code.add(new LdcInsnNode(index++));code.add(new VarInsnNode(arg.getOpcode(ILOAD),slot));box(code,arg);code.add(new InsnNode(AASTORE));slot+=arg.getSize();}
    }
    static void box(InsnList code,Type type) {
        String[] wrappers={null,"Boolean","Character","Byte","Short","Integer","Float","Long","Double"};int kind=type.getSort();
        if(kind>=Type.BOOLEAN&&kind<=Type.DOUBLE){String owner="java/lang/"+wrappers[kind];code.add(new MethodInsnNode(INVOKESTATIC,owner,"valueOf","("+type.getDescriptor()+")L"+owner+";",false));}
    }
    public static final class Recorder {
        static final ObjectMapper JSON=new ObjectMapper();static BufferedWriter output;static long sequence,frameCounter,fieldHooks,branchHooks;
        static final IdentityHashMap<Object,String> IDS=new IdentityHashMap<>();static final Map<String,Integer> VERSIONS=new HashMap<>();
        static final ThreadLocal<Frame> FRAME=new ThreadLocal<>();static final Map<String,Set<String>> ACTIVE=new HashMap<>();
        static final CyclicBarrier BARRIER=new CyclicBarrier(12);
        static final class Frame {String id;Object[] args;Set<String> owners=new HashSet<>();}
        static String id(Object o){if(o==null)return null;String v=IDS.get(o);if(v==null){v="o"+(IDS.size()+1);IDS.put(o,v);}return v;}
        public static String hash(byte[] bytes){try{StringBuilder s=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))s.append(String.format("%02x",b&255));return s.toString();}catch(Exception e){throw new IllegalStateException(e);}}
        static Map<String,Object> row(){Map<String,Object> r=new LinkedHashMap<>();r.put("frame",FRAME.get()==null?null:FRAME.get().id);r.put("thread",Thread.currentThread().getId());return r;}
        static Map<String,Object> value(Object o){Map<String,Object> r=new LinkedHashMap<>();r.put("object",id(o));r.put("value",o);return r;}
        static Map<String,Object> observed(Object o){Map<String,Object> r=new LinkedHashMap<>();r.put("object",id(o));r.put("value",o instanceof Number||o instanceof Boolean||o instanceof String?o:o==null?null:String.valueOf(o));return r;}
        static List<Object> snapshot(Object[] args,boolean end)throws Exception {
            List<Object> result=new ArrayList<>();List<String> descs=(List<String>)plan.get("root_arguments");Set<String> targets=new HashSet<>((List<String>)plan.get("targets"));
            for(int i=0;i<args.length;i++) {
                Object object=args[i];String desc=descs.get(i);Map<String,Object> a=new LinkedHashMap<>();a.put("argument",i);a.put("object",id(object));a.put("type",desc);
                if(!desc.startsWith("L")||desc.equals("Ljava/lang/String;")){a.put("scalar",observed(object));result.add(a);continue;}
                if(object==null)throw new IllegalStateException("Null root DTO");
                if(!object.getClass().getName().replace('.','/').equals(desc.substring(1,desc.length()-1)))throw new IllegalStateException("Runtime DTO type differs from model");
                List<Object> leaves=new ArrayList<>();
                for(Field f:object.getClass().getDeclaredFields()) {
                    if(Modifier.isStatic(f.getModifiers()))continue;String field=f.getDeclaringClass().getName().replace('.','/')+"."+f.getName();
                    if(!(end?targets:fields).contains(field))continue;f.setAccessible(true);Map<String,Object> leaf=new LinkedHashMap<>();leaf.put("field",field);leaf.put("version",VERSIONS.getOrDefault(id(object)+":"+field,0));Map<String,Object> v=observed(f.get(object));if(f.getType().isPrimitive())v.put("object",null);leaf.put("observed",v);leaves.add(leaf);
                }
                a.put("fields",leaves);result.add(a);
            }return result;
        }
        public static void start()throws Exception {
            output=Files.newBufferedWriter(Paths.get(System.getProperty("query.events")));Map<String,Object> r=new LinkedHashMap<>();r.put("mode",System.getProperty("query.mode","selective"));r.put("plan_sha256",hash(Files.readAllBytes(Paths.get(System.getProperty("query.plan")))));emit("start",r);
            Runtime.getRuntime().addShutdownHook(new Thread(()->{synchronized(Recorder.class){Map<String,Object> m=row();m.put("field_hook_calls",fieldHooks);m.put("branch_hook_calls",branchHooks);emit("metrics",m);}}));
        }
        public static void enter(Object[] args) {
            synchronized(Recorder.class) {
                try {
                    if(FRAME.get()!=null)throw new IllegalStateException("Nested root");Frame f=new Frame();f.id="f"+(++frameCounter);f.args=args;FRAME.set(f);
                    List<Number> writable=(List<Number>)plan.get("writable_arguments");
                    for(Number w:writable)for(int j=0;j<args.length;j++)if(w.intValue()!=j&&args[w.intValue()]==args[j])throw new IllegalStateException("Mutable root arguments alias");
                    for(Object a:args)if(a!=null&&!(a instanceof String||a instanceof Number||a instanceof Boolean))f.owners.add(id(a));
                    for(String owner:f.owners){Set<String> users=ACTIVE.computeIfAbsent(owner,k->new HashSet<>());if(!users.isEmpty())throw new IllegalStateException("Shared active DTO outside thread-owned contract");users.add(f.id);}
                    Map<String,Object> r=row();r.put("request_id",Thread.currentThread().getName());r.put("arguments",snapshot(args,false));emit("enter",r);
                }catch(Exception e){problem(e.toString());throw new IllegalStateException(e);}
            }
            // Optional test scheduling; independent of query/values/source labels.
            if(Boolean.getBoolean("query.test.barrier")&&Thread.currentThread().getName().startsWith("parallel-"))try{BARRIER.await(15,TimeUnit.SECONDS);}catch(Exception e){problem(e.toString());throw new IllegalStateException(e);}
        }
        public static synchronized void exit(){try{Frame f=FRAME.get();Map<String,Object> r=row();r.put("arguments",snapshot(f.args,true));emit("exit",r);for(String owner:f.owners)ACTIVE.get(owner).remove(f.id);FRAME.remove();}catch(Exception e){problem(e.toString());throw new IllegalStateException(e);}}
        public static synchronized void abort(){emit("abort",row());FRAME.remove();}
        public static synchronized void field(Object owner,String field,Object value,String site,boolean write,boolean log) {
            fieldHooks++;String key=id(owner)+":"+field;int version=VERSIONS.getOrDefault(key,0);if(write)VERSIONS.put(key,++version);
            if(write&&ACTIVE.containsKey(id(owner)))for(String user:ACTIVE.get(id(owner)))if(FRAME.get()==null||!user.equals(FRAME.get().id)){problem("Unowned concurrent write");throw new IllegalStateException("Unowned write");}
            if(FRAME.get()!=null&&log){Map<String,Object> r=row();r.put("site",site);r.put("owner",id(owner));r.put("field",field);r.put("version",version);r.put("observed",observed(value));emit(write?"write":"read",r);}
        }
        public static synchronized void branch(String site,boolean taken){branchHooks++;Map<String,Object> r=row();r.put("site",site);r.put("taken",taken);emit("branch",r);}
        public static synchronized void transformed(String owner,byte[] bytes){Map<String,Object> r=row();r.put("class",owner);r.put("sha256",hash(bytes));emit("transformed",r);}
        public static synchronized void problem(String message){Map<String,Object> r=row();r.put("error",message);emit("problem",r);}
        static synchronized void emit(String kind,Map<String,Object> r){try{r.put("kind",kind);r.put("seq",++sequence);output.write(JSON.writeValueAsString(r));output.newLine();output.flush();}catch(IOException e){throw new IllegalStateException(e);}}
    }
}
