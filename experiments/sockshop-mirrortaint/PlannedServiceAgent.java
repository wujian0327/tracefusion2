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
    static boolean root(String method){Map cfg=(Map)plan.get("session_history");return method.equals(plan.get("entry"))||(cfg!=null&&((List)cfg.get("roots")).contains(method));}
    public byte[] transform(final ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes) {
        if(!hashes.containsKey(owner))return null;
        try {
            if(!Recorder.hash(bytes).equals(hashes.get(owner)))throw new IllegalStateException("Frozen class changed: "+owner);
            ClassNode cls=new ClassNode(ASM9);new ClassReader(bytes).accept(cls,ClassReader.EXPAND_FRAMES);ResponseBindingHooks.registerClass(cls,loader);boolean changed=false;
            List effectOwners=ExecutionKernelHooks.enabled()?(List)((Map)plan.get("execution_kernel")).getOrDefault("initialized_effect_owners",Collections.emptyList()):Collections.emptyList();
            if(effectOwners.contains(owner)&&cls.methods.stream().noneMatch(m->m.name.equals("<clinit>"))){MethodNode init=new MethodNode(ACC_STATIC,"<clinit>","()V",null,null);init.instructions.add(new InsnNode(RETURN));cls.methods.add(init);}
            for(MethodNode m:cls.methods) {
                if((m.access&(ACC_ABSTRACT|ACC_NATIVE))!=0)continue;String key=owner+"."+m.name+m.desc;
                List<AbstractInsnNode> code=new ArrayList<>();for(AbstractInsnNode n:m.instructions.toArray())if(n.getOpcode()>=0)code.add(n);
                if(m.name.equals("<clinit>")&&ExecutionKernelHooks.enabled()&&(((List)((Map)plan.get("execution_kernel")).getOrDefault("initialized_lambda_owners",Collections.emptyList())).contains(owner)||effectOwners.contains(owner))){
                    for(AbstractInsnNode n:code)if(n.getOpcode()==RETURN){InsnList init=new InsnList();init.add(new LdcInsnNode(Type.getObjectType(owner)));init.add(new MethodInsnNode(INVOKESTATIC,"ExecutionKernelHooks","classInitialized","(Ljava/lang/Class;)V",false));m.instructions.insertBefore(n,init);changed=true;}
                }
                if(CollectionServiceHooks.instrument(m,key,code))changed=true;
                if(ExecutionKernelHooks.instrument(m,key,code))changed=true;
                if(SourceObservationHooks.instrument(m,key,code))changed=true;
                if(ResponseBindingHooks.instrument(m,key,code))changed=true;
                boolean initialized=!m.name.equals("<init>");AbstractInsnNode entry=null;
                for(int i=0;i<code.size();i++) {
                    AbstractInsnNode n=code.get(i);String site=key+"@"+i;
                    if(!initialized&&n instanceof MethodInsnNode){MethodInsnNode c=(MethodInsnNode)n;if(c.getOpcode()==INVOKESPECIAL&&c.name.equals("<init>")&&(c.owner.equals(owner)||c.owner.equals(cls.superName))){initialized=true;entry=n;continue;}}
                    if(!initialized)continue;
                    if(n instanceof FieldInsnNode) {
                        FieldInsnNode f=(FieldInsnNode)n;String field=canonicalField(f);
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
                    InsnList h=new InsnList();h.add(new LdcInsnNode(key));h.add((m.access&ACC_STATIC)!=0?new InsnNode(ACONST_NULL):new VarInsnNode(ALOAD,0));arguments(h,m);h.add(new MethodInsnNode(INVOKESTATIC,R,"enter","(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;",false));int scope=m.maxLocals++;h.add(new VarInsnNode(ASTORE,scope));LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode();h.add(start);
                    if(entry==null)m.instructions.insert(h);else m.instructions.insert(entry,h);
                    for(AbstractInsnNode n:code)if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN) {
                        InsnList e=new InsnList();Type t=Type.getReturnType(m.desc);if(t.getSort()==Type.VOID)e.add(new InsnNode(ACONST_NULL));else{e.add(new InsnNode(t.getSize()==2?DUP2:DUP));box(e,t);}e.add(new VarInsnNode(ALOAD,scope));e.add(new MethodInsnNode(INVOKESTATIC,R,"exit","(Ljava/lang/Object;Ljava/lang/Object;)V",false));m.instructions.insertBefore(n,e);
                    }
                    m.instructions.add(end);m.instructions.add(handler);int error=m.maxLocals++;m.instructions.add(new VarInsnNode(ASTORE,error));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new VarInsnNode(ALOAD,scope));m.instructions.add(new LdcInsnNode(Type.getObjectType(owner)));m.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"abort","(Ljava/lang/Throwable;Ljava/lang/Object;Ljava/lang/Class;)V",false));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));changed=true;
                }
            }
            MonitorSafety.instrument(cls);Recorder.transformed(owner);RequestScopeHooks.coverage(owner);
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
    static String canonicalField(FieldInsnNode f){return (String)((Map)plan.getOrDefault("field_declarations",Collections.emptyMap())).getOrDefault(f.owner+"."+f.name+":"+f.desc,f.owner+"."+f.name);}
    static void field(MethodNode m,FieldInsnNode f,String site,boolean write,boolean log) {
        Type t=Type.getType(f.desc);int object=m.maxLocals++,value=m.maxLocals;m.maxLocals+=t.getSize();InsnList a=new InsnList(),b=new InsnList();
        if(write){a.add(new VarInsnNode(t.getOpcode(ISTORE),value));a.add(new VarInsnNode(ASTORE,object));a.add(new VarInsnNode(ALOAD,object));a.add(new VarInsnNode(t.getOpcode(ILOAD),value));}
        else{a.add(new InsnNode(DUP));a.add(new VarInsnNode(ASTORE,object));b.add(new InsnNode(t.getSize()==2?DUP2:DUP));b.add(new VarInsnNode(t.getOpcode(ISTORE),value));}
        InsnList event=new InsnList();event.add(new VarInsnNode(ALOAD,object));event.add(new LdcInsnNode(canonicalField(f)));event.add(new VarInsnNode(t.getOpcode(ILOAD),value));boolean primitive=t.getSort()>=1&&t.getSort()<=8;if(!primitive)event.add(new LdcInsnNode(f.desc));event.add(new LdcInsnNode(site));event.add(new InsnNode(write?ICONST_1:ICONST_0));event.add(new InsnNode(log?ICONST_1:ICONST_0));event.add(new MethodInsnNode(INVOKESTATIC,R,primitive?"field"+f.desc:"field","(Ljava/lang/Object;Ljava/lang/String;"+(primitive?f.desc:"Ljava/lang/Object;Ljava/lang/String;")+"Ljava/lang/String;ZZ)V",false));
        if(write&&ExecutionKernelHooks.applicationCandidate(site,canonicalField(f))!=null){
            LabelNode observe=new LabelNode(),done=new LabelNode();b.add(new VarInsnNode(ALOAD,object));b.add(new LdcInsnNode(site));b.add(new LdcInsnNode(canonicalField(f)));b.add(new MethodInsnNode(INVOKESTATIC,"ExecutionKernelHooks","versionOnly","(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;)Z",false));b.add(new JumpInsnNode(IFEQ,observe));
            b.add(new VarInsnNode(ALOAD,object));b.add(new LdcInsnNode(canonicalField(f)));b.add(new LdcInsnNode(site));b.add(new MethodInsnNode(INVOKESTATIC,R,"fieldVersionRecord","(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;)V",false));b.add(new JumpInsnNode(GOTO,done));b.add(observe);b.add(event);b.add(done);
        }else if(write&&ExecutionKernelHooks.closureCandidate(site,canonicalField(f))){
            LabelNode observe=new LabelNode(),done=new LabelNode();b.add(new LdcInsnNode(site));b.add(new LdcInsnNode(canonicalField(f)));b.add(new MethodInsnNode(INVOKESTATIC,"ExecutionKernelHooks","omitWrite","(Ljava/lang/String;Ljava/lang/String;)Z",false));b.add(new JumpInsnNode(IFEQ,observe));
            b.add(new VarInsnNode(ALOAD,object));b.add(new LdcInsnNode(canonicalField(f)));b.add(new LdcInsnNode(site));b.add(new MethodInsnNode(INVOKESTATIC,R,"fieldVersion","(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;)V",false));b.add(new JumpInsnNode(GOTO,done));b.add(observe);b.add(event);b.add(done);
        }else if(!write&&BodyObservationHooks.config()!=null){
            LabelNode done=new LabelNode();b.add(new VarInsnNode(ALOAD,object));b.add(new LdcInsnNode(canonicalField(f)));b.add(new LdcInsnNode(site));b.add(new MethodInsnNode(INVOKESTATIC,"BodyObservationHooks","omitRead","(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;)Z",false));b.add(new JumpInsnNode(IFNE,done));b.add(event);b.add(done);
        }else b.add(event);
        m.instructions.insertBefore(f,a);m.instructions.insert(f,b);
    }
    static void arguments(InsnList h,MethodNode m){Type[] ts=Type.getArgumentTypes(m.desc);h.add(new LdcInsnNode(ts.length));h.add(new TypeInsnNode(ANEWARRAY,"java/lang/Object"));int slot=(m.access&ACC_STATIC)!=0?0:1;for(int i=0;i<ts.length;i++){h.add(new InsnNode(DUP));h.add(new LdcInsnNode(i));h.add(new VarInsnNode(ts[i].getOpcode(ILOAD),slot));box(h,ts[i]);h.add(new InsnNode(AASTORE));slot+=ts[i].getSize();}}
    static void box(InsnList h,Type t){String[] ws={null,"Boolean","Character","Byte","Short","Integer","Float","Long","Double"};if(t.getSort()>=1&&t.getSort()<=8){String o="java/lang/"+ws[t.getSort()];h.add(new MethodInsnNode(INVOKESTATIC,o,"valueOf","("+t.getDescriptor()+")L"+o+";",false));}}
    public static final class Recorder {
        // Optional diagnosis only. No event or source validation depends on it.
        static final class Diagnostic {
            static final boolean enabled=Boolean.getBoolean("service.diagnostic.timing");
            static volatile boolean active;
            static final java.lang.management.ThreadMXBean threads=enabled?java.lang.management.ManagementFactory.getThreadMXBean():null;
            static void start(){if(!enabled)return;Thread sampler=new Thread(()->{
                try(BufferedWriter file=Files.newBufferedWriter(Paths.get(System.getProperty("service.events")+".diagnostic.jsonl"),StandardOpenOption.CREATE_NEW)){
                    int count=0;while(count<2000){Thread.sleep(250);if(!active)continue;Map<String,Object> sample=new LinkedHashMap<>();sample.put("monotonic_ns",System.nanoTime());List<Object> rows=new ArrayList<>();
                        for(java.lang.management.ThreadInfo info:threads.dumpAllThreads(true,true)){if(info==null)continue;Map<String,Object> row=new LinkedHashMap<>();row.put("id",info.getThreadId());row.put("name",info.getThreadName());row.put("state",info.getThreadState().name());row.put("lock",info.getLockName());row.put("lock_owner",info.getLockOwnerId());row.put("cpu_ns",threads.getThreadCpuTime(info.getThreadId()));List<String> stack=new ArrayList<>();for(StackTraceElement frame:info.getStackTrace())stack.add(frame.toString());row.put("stack",stack);rows.add(row);}sample.put("threads",rows);file.write(JSON.writeValueAsString(sample));file.newLine();file.flush();count++;
                    }
                }catch(Exception failure){System.err.println("Optional agent diagnosis stopped: "+failure.getClass().getName());}
            },"tf2-diagnostic-sampler");sampler.setDaemon(true);sampler.start();}
        }
        static final ObjectMapper JSON=new ObjectMapper();static BufferedWriter output;static long seq,framesCounter,fieldHooks,branches;
        static final WeakIdentityMap<Object,String> IDS=new WeakIdentityMap<>("IDS",100000,Recorder::retiredIdentity,Recorder::canRetireIdentity);static final OwnerVersions VERSIONS=new OwnerVersions();
        static long allocatedIds,idLookups;
        static String captureSession,processInstance; static int historyVersion; static boolean httpExchange;
        static final Set<String> CHECKED_CLASSES=new HashSet<>();
        static final ThreadLocal<Deque<Frame>> STACK=new ThreadLocal<Deque<Frame>>(){protected Deque<Frame> initialValue(){return new ArrayDeque<>();}};
        static final ThreadLocal<String> PENDING=new ThreadLocal<>();static final Map<String,Set<String>> ACTIVE=new HashMap<>();
        static volatile boolean captureInvalid;
        static class Frame{String id,method;List<String> locked=new ArrayList<>();List<Object> inputs;}
        static synchronized String id(Object o){if(o==null)return null;if((++idLookups&63)==0)drainRetired(16);String s=IDS.get(o);if(s==null){if(allocatedIds==Long.MAX_VALUE)throw new IllegalStateException("Identity serial exhausted");s="o"+(allocatedIds+1);IDS.put(o,s);allocatedIds++;}return s;}
        static boolean canRetireIdentity(String id){Set<String> users=ACTIVE.get(id);return users==null||users.isEmpty();}
        static void retiredIdentity(String id){VERSIONS.retireOwner(id);ACTIVE.remove(id);}
        public static synchronized void drainRetired(int budget){
            IDS.drain(budget);VERSIONS.drain(budget);ExecutionKernelHooks.ARRAY_VERSIONS.drain(budget);ExecutionKernelHooks.ARRAY_SLOTS.drain(budget);
            CollectionServiceHooks.READ_ONLY_INDEX.drain(budget);CollectionServiceHooks.CONTENTS.drain(budget);CollectionServiceHooks.EPOCHS.drain(budget);AsyncTaskHooks.FUTURES.drain(budget);TemporalDateHooks.WIRE.drain(budget);
        }
        public static synchronized Map<String,Object> lifecycle(){drainRetired(64);Map<String,Object> r=new LinkedHashMap<>();r.put("ids_allocated",allocatedIds);r.put("ids_registered",IDS.size());r.put("ids_retired",IDS.retiredCount);r.put("ids_weak_cleared",IDS.weakClearedCount);r.put("ids_terminal_deferred",IDS.pending());r.put("field_version_entries",VERSIONS.size());r.put("field_versions_retired",VERSIONS.retiredEntries);r.put("field_cleanup_pending",VERSIONS.pending);r.put("field_owners",VERSIONS.owners.size());r.put("array_version_entries",ExecutionKernelHooks.ARRAY_VERSIONS.size());r.put("array_slot_entries",ExecutionKernelHooks.ARRAY_SLOTS.size());r.put("readonly_entries",CollectionServiceHooks.READ_ONLY_INDEX.size());r.put("contents_entries",CollectionServiceHooks.CONTENTS.size());r.put("epoch_entries",CollectionServiceHooks.EPOCHS.size());r.put("future_entries",AsyncTaskHooks.FUTURES.size());r.put("date_wire_entries",TemporalDateHooks.WIRE.size());r.put("retained_streams",ExecutionKernelHooks.STREAMS.size());r.put("retained_initialized_classes",ExecutionKernelHooks.INITIALIZED.size());r.put("retained_library_classes",ExecutionKernelHooks.LIBRARY_HASHES.size());r.put("retained_checked_class_names",CHECKED_CLASSES.size());r.put("retained_source_captures",SourceEvidenceHooks.CAPTURES.size());r.put("retained_feign_commands",FeignEffectHooks.COMMANDS.size());r.put("retained_feign_inputs",FeignEffectHooks.INPUTS.size());r.put("retained_json_loaders",JsonTreeObservationHooks.LOADED.size());r.put("retained_json_field_classes",JsonTreeObservationHooks.FIELDS.size());r.put("retained_wrapper_loaders",ResponseBindingHooks.WRAPPER_CLASSES.size());r.put("retained_copy_loaders",JsonListCopyHooks.LOADED.size());r.put("retained_copy_initialized",JsonListCopyHooks.INITIALIZED.size());r.put("retained_scope_loaders",RequestScopeHooks.CHECKED.size());r.put("retained_root_messages",RequestScopeHooks.ROOTS.size());r.put("retained_return_messages",ResponseBindingHooks.RETURN_MESSAGES.size());r.put("current_thread_read_streams",ReadEffectHooks.STREAMS.get().size());r.put("current_thread_optionals",ReadEffectHooks.OPTIONALS.get().size());r.put("current_thread_sequence_pipes",SequenceKernelHooks.PIPES.get().size());r.put("current_thread_sequence_collectors",SequenceKernelHooks.COLLECTORS.get().size());r.put("current_thread_async_active",AsyncTaskHooks.ACTIVE.get()!=null);r.put("current_thread_monitor",MonitorSafety.inspect());return r;}

        static Map<String,Object> row(){Map<String,Object> r=new LinkedHashMap<>();r.put("frame",STACK.get().isEmpty()?null:STACK.get().peek().id);return r;}
        static synchronized Map<String,Object> value(Object o){Map<String,Object> r=new LinkedHashMap<>();r.put("object",id(o));if(ScalarProjectionHooks.enumeration(o))return ScalarProjectionHooks.observed((Enum)o);if(TemporalDateHooks.date(o))return TemporalDateHooks.observe((java.util.Date)o);if(UuidProjectionHooks.uuid(o)){r.put("value",o.toString());r.put("uuid_type","java.util.UUID");return r;}if(o instanceof Character&&ExecutionKernelHooks.extended())r.put("value",(int)((Character)o).charValue());else if(o==null||o instanceof Number||o instanceof String||o instanceof Boolean)r.put("value",o);return r;}
        static Map<String,Object> primitiveValue(Object value,String descriptor){
            Map<String,Object> r=new LinkedHashMap<>();r.put("object",null);r.put("primitive",descriptor);r.put("value",value instanceof Character?(int)((Character)value).charValue():value);
            if(descriptor.equals("F"))r.put("bits",Integer.toHexString(Float.floatToRawIntBits((Float)value)));
            if(descriptor.equals("D"))r.put("bits",Long.toHexString(Double.doubleToRawLongBits((Double)value)));return r;
        }
        static Map<String,Object> fieldValue(Object v,String descriptor){return descriptor.length()==1&&"ZBCSIJFD".contains(descriptor)?primitiveValue(v,descriptor):value(v);}
        static String methodDescriptor(String key){if(key==null||key.indexOf('(')<0)throw new IllegalStateException("Original method descriptor absent");return key.substring(key.indexOf('('));}
        static List<Object> methodArguments(Object[] args,String descriptor){Type[] types=Type.getArgumentTypes(descriptor);if(types.length!=args.length)throw new IllegalStateException("Method argument count differs");List<Object> values=new ArrayList<>();for(int i=0;i<args.length;i++)values.add(fieldValue(args[i],types[i].getDescriptor()));return values;}
        static Map<String,Object> methodResult(Object result,String descriptor){String returned=Type.getReturnType(descriptor).getDescriptor();if(returned.equals("V")){if(result!=null)throw new IllegalStateException("Non-null void observation");Map<String,Object> r=value(null);r.put("void",true);return r;}return fieldValue(result,returned);}
        static String fieldDescriptor(Object owner,String field){try{String name=field.substring(0,field.lastIndexOf('.'));for(Class c=owner.getClass();c!=null;c=c.getSuperclass())if(c.getName().replace('.','/').equals(name))return Type.getDescriptor(c.getDeclaredField(field.substring(field.lastIndexOf('.')+1)).getType());throw new IllegalStateException("Declared field absent: "+field);}catch(Exception e){throw new IllegalStateException(e);}}
        static String hash(byte[] data)throws Exception{StringBuilder s=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(data))s.append(String.format("%02x",b&255));return s.toString();}
        public static synchronized void start()throws Exception{if(plan.get("session_history")!=null){Map cfg=(Map)plan.get("session_history");historyVersion=((Number)cfg.get("version")).intValue();if((historyVersion!=1&&historyVersion!=2)||!"full".equals(mode))throw new IllegalArgumentException("Session history requires full observation and supported version");}httpExchange=plan.get("http_exchange")!=null;if(httpExchange||historyVersion>0){captureSession=UUID.randomUUID().toString();processInstance=UUID.randomUUID().toString();}output=Files.newBufferedWriter(Paths.get(System.getProperty("service.events")),StandardOpenOption.CREATE_NEW);Map<String,Object> r=row();r.put("mode",mode);r.put("exception_dispatch_version",1);r.put("field_value_version",1);r.put("method_value_version",1);r.put("identity_lifecycle_version",1);r.put("plan_sha256",hash(Files.readAllBytes(Paths.get(System.getProperty("service.plan")))));emit("start",r);Runtime.getRuntime().addShutdownHook(new Thread(()->{synchronized(Recorder.class){Map<String,Object> m=row();m.put("capture_invalid",captureInvalid);m.put("lifecycle",lifecycle());m.put("field_hook_calls",fieldHooks);m.put("branch_hook_calls",branches);m.put("ids_size",IDS.size());m.put("versions_size",VERSIONS.size());m.put("active_owners",ACTIVE.size());m.put("checked_classes_size",CHECKED_CLASSES.size());m.put("library_hashes_size",ExecutionKernelHooks.LIBRARY_HASHES.size());m.put("array_versions_size",ExecutionKernelHooks.ARRAY_VERSIONS.size());m.put("array_slots_size",ExecutionKernelHooks.ARRAY_SLOTS.size());m.put("initialized_classes_size",ExecutionKernelHooks.INITIALIZED.size());emit("metrics",m);}}));}
        public static synchronized void callsite(String site){if(!STACK.get().isEmpty())PENDING.set(site);}
        static List<Object> snapshot(Object o,boolean target)throws Exception{
            List<Object> out=new ArrayList<>();if(o==null)return out;Set<String> wanted=new HashSet<>((List<String>)plan.get(target?"snapshot_fields":full?"full_snapshot_fields":"mapper_fields"));
            for(Class<?> c=o.getClass();c!=null&&c!=Object.class;c=c.getSuperclass())for(Field f:c.getDeclaredFields()) {
                String name=c.getName().replace('.','/')+"."+f.getName();if(Modifier.isStatic(f.getModifiers())||!wanted.contains(name))continue;f.setAccessible(true);
                Map<String,Object> r=new LinkedHashMap<>();r.put("owner",id(o));r.put("field",name);r.put("version",VERSIONS.getOrDefault(id(o)+":"+name,0));r.put("descriptor",Type.getDescriptor(f.getType()));r.put("observed",fieldValue(f.get(o),Type.getDescriptor(f.getType())));out.add(r);
            }return out;
        }
        public static synchronized Object enter(String method,Object self,Object[] args){MonitorSafety.Scope scope=MonitorSafety.open(method);if(scope.failed)return scope;try{
            Frame f=new Frame();f.id="f"+(++framesCounter);f.method=method;scope.frame=f;Map<String,Object> r=row();r.put("parent",r.get("frame"));r.put("frame",f.id);r.put("method",method);r.put("receiver",id(self));r.put("callsite",PENDING.get());PENDING.remove();String descriptor=methodDescriptor(method);r.put("method_descriptor",descriptor);r.put("args",methodArguments(args,descriptor));ExecutionKernelHooks.callbackSite(r);AsyncTaskHooks.frame(r);
            ExecutionKernelHooks.constructorFrame(r,method,self);
            if(method.equals(plan.get("entry")))try{r.put("trace_id",Class.forName("org.slf4j.MDC",false,Thread.currentThread().getContextClassLoader()).getMethod("get",String.class).invoke(null,"X-B3-TraceId"));}catch(Exception ignored){}
            if(method.equals(plan.get("entry"))&&"identity-return".equals(plan.get("profile"))){Object a=args[((Number)plan.get("input_argument")).intValue()];if(a==null||!a.getClass().getName().replace('.','/').equals(plan.get("input_owner")))throw new IllegalStateException("Runtime input DTO differs");r.put("input_object",id(a));r.put("input_fields",snapshot(a,true));Set<String> users=ACTIVE.computeIfAbsent(id(a),k->new HashSet<>());if(!users.isEmpty())throw new IllegalStateException("Shared active input DTO");users.add(f.id);f.locked.add(id(a));}
            if(method.equals(plan.get("producer_method"))) {
                int index=((Number)((Map)plan.get("reduction")).get("input_argument")).intValue();Object a=args[index];if(!(a instanceof List))throw new IllegalStateException("Only ordered List reduction supported");
                List<Object> inputs=new ArrayList<>();for(Object member:(List<?>)a){if(inputs.size()>=10000)throw new IllegalStateException("Collection bound");if(member==null||!member.getClass().getName().replace('.','/').equals(plan.get("mapper_owner")))throw new IllegalStateException("Runtime mapper DTO differs");Map<String,Object> v=new LinkedHashMap<>();v.put("object",id(member));v.put("fields",snapshot(member,false));inputs.add(v);}
                f.inputs=inputs;r.put("inputs",inputs);for(Object member:(List<?>)a){String o=id(member);Set<String> users=ACTIVE.computeIfAbsent(o,k->new HashSet<>());if(!users.isEmpty()&&!users.contains(f.id))throw new IllegalStateException("Concurrent shared mapper DTO");users.add(f.id);f.locked.add(o);}
            }
            RequestScopeHooks.root(method,f.id);MonitorSafety.fault("enter-active",method);STACK.get().push(f);emit("enter",r);MonitorSafety.fault("enter",method);
            if(root(method))ResponseBindingHooks.enter(args);
        }catch(Throwable e){MonitorSafety.fatal(e);scope.fail("enter",e);}return scope;}
        public static synchronized void exit(Object result,Object token){finish(token,result,false);}
        public static synchronized void abort(Throwable error,Object token,Class caller){if(token instanceof MonitorSafety.Scope && !((MonitorSafety.Scope)token).failed){Map r=row();r.put("exception",error.getClass().getName());r.put("observed",value(error));r.put("exception_dispatch",ExecutionKernelHooks.exceptionDispatch(error,caller));ABORT.set(r);}try{finish(token,null,true);}finally{ABORT.remove();}}
        static final ThreadLocal<Map> ABORT=new ThreadLocal<>();
        static void finish(Object token,Object result,boolean exceptional){
            if(!(token instanceof MonitorSafety.Scope))return;MonitorSafety.Scope scope=(MonitorSafety.Scope)token;if(scope.closed)return;
            try{if(scope.failed)return;if(STACK.get().peek()!=scope.frame)throw new IllegalStateException("Frame completion owner differs");Frame f=scope.frame;
                MonitorSafety.fault(exceptional?"abort":"exit",f.method);
                if(exceptional){if(root(f.method))ResponseBindingHooks.abort();Map r=ABORT.get()==null?row():ABORT.get();r.put("method_descriptor",methodDescriptor(f.method));emit("abort",r);}
                else{Map<String,Object> r=row();String descriptor=methodDescriptor(f.method);r.put("method_descriptor",descriptor);r.put("result",methodResult(result,descriptor));if(root(f.method)){r.put("fields",snapshot(result,true));ResponseBindingHooks.exit(result);}emit("exit",r);}
            }catch(Throwable e){MonitorSafety.fatal(e);scope.fail(exceptional?"abort":"exit",e);}finally{scope.close();}
        }
        public static synchronized void field(Object o,String field,Object v,String site,boolean write,boolean log){field(o,field,v,fieldDescriptor(o,field),site,write,log);}
        public static synchronized void field(Object o,String field,Object v,String descriptor,String site,boolean write,boolean log){fieldObserved(o,field,!STACK.get().isEmpty()&&log?fieldValue(v,descriptor):null,descriptor,site,write,log);}
        static synchronized void fieldObserved(Object o,String field,Map<String,Object> observed,String descriptor,String site,boolean write,boolean log){fieldHooks++;String key=id(o)+":"+field;int version=VERSIONS.getOrDefault(key,0);if(write){VERSIONS.put(key,++version);if(ACTIVE.containsKey(id(o))&&!ACTIVE.get(id(o)).isEmpty()){problem("Source mutated within read-only reduction epoch");throw new IllegalStateException("Source mutation");}}
            if(!STACK.get().isEmpty()&&log){Map<String,Object> r=row();r.put("owner",id(o));r.put("field",field);r.put("version",version);r.put("descriptor",descriptor);r.put("observed",observed);r.put("site",site);emit(write?"write":"read",r);}}
        public static synchronized void fieldZ(Object o,String field,boolean v,String site,boolean write,boolean log){fieldObserved(o,field,!STACK.get().isEmpty()&&log?primitiveValue(v,"Z") :null,"Z",site,write,log);}
        public static synchronized void fieldB(Object o,String field,byte v,String site,boolean write,boolean log){fieldObserved(o,field,!STACK.get().isEmpty()&&log?primitiveValue(v,"B") :null,"B",site,write,log);}
        public static synchronized void fieldC(Object o,String field,char v,String site,boolean write,boolean log){fieldObserved(o,field,!STACK.get().isEmpty()&&log?primitiveValue(v,"C") :null,"C",site,write,log);}
        public static synchronized void fieldS(Object o,String field,short v,String site,boolean write,boolean log){fieldObserved(o,field,!STACK.get().isEmpty()&&log?primitiveValue(v,"S") :null,"S",site,write,log);}
        public static synchronized void fieldI(Object o,String field,int v,String site,boolean write,boolean log){fieldObserved(o,field,!STACK.get().isEmpty()&&log?primitiveValue(v,"I") :null,"I",site,write,log);}
        public static synchronized void fieldJ(Object o,String field,long v,String site,boolean write,boolean log){fieldObserved(o,field,!STACK.get().isEmpty()&&log?primitiveValue(v,"J") :null,"J",site,write,log);}
        public static synchronized void fieldF(Object o,String field,float v,String site,boolean write,boolean log){fieldObserved(o,field,!STACK.get().isEmpty()&&log?primitiveValue(v,"F") :null,"F",site,write,log);}
        public static synchronized void fieldD(Object o,String field,double v,String site,boolean write,boolean log){fieldObserved(o,field,!STACK.get().isEmpty()&&log?primitiveValue(v,"D") :null,"D",site,write,log);}
        public static synchronized void fieldVersion(Object o,String field,String site){fieldHooks++;String key=id(o)+":"+field;VERSIONS.put(key,VERSIONS.getOrDefault(key,0)+1);if(ACTIVE.containsKey(id(o))&&!ACTIVE.get(id(o)).isEmpty()){problem("Source mutated within read-only reduction epoch");throw new IllegalStateException("Source mutation");}ExecutionKernelHooks.elidedWrite(site,field);}
        public static synchronized void fieldVersionRecord(Object o,String field,String site){if(!ExecutionKernelHooks.versionOnly(o,site,field))throw new IllegalStateException("Uncertified application write-value omission");fieldHooks++;String key=id(o)+":"+field;int version=VERSIONS.getOrDefault(key,0)+1;VERSIONS.put(key,version);if(ACTIVE.containsKey(id(o))&&!ACTIVE.get(id(o)).isEmpty()){problem("Source mutated within read-only reduction epoch");throw new IllegalStateException("Source mutation");}Map<String,Object> r=row();r.put("owner",id(o));r.put("field",field);r.put("version",version);r.put("site",site);emit("write-version",r);}
        public static synchronized void branch(String site,boolean taken){branches++;if(BodyObservationHooks.omitBranch())return;if(!STACK.get().isEmpty()){Map<String,Object> r=row();r.put("site",site);r.put("taken",taken);emit("branch",r);}}
        public static synchronized void sumStart(Object s){Map<String,Object> r=row();r.put("parallel",((java.util.stream.DoubleStream)s).isParallel());emit("sum-enter",r);}
        public static synchronized void sumEnd(double d){Map<String,Object> r=row();r.put("value",d);emit("sum-exit",r);}
        public static synchronized void transformed(String owner){CHECKED_CLASSES.add(owner);Map<String,Object> r=row();r.put("class",owner);emit("class",r);}
        public static synchronized void problem(String message){captureInvalid=true;try{Files.write(Paths.get(System.getProperty("service.events")+".invalid"),Collections.singletonList(message),StandardOpenOption.CREATE,StandardOpenOption.APPEND);}catch(Exception ignored){}try{Map<String,Object> r=row();r.put("message",message);emit("problem",r);}catch(Exception ignored){}try{System.err.println("QUERY_SERVICE: "+message);}catch(Exception ignored){}}
        static void safeEvent(Object value,IdentityHashMap<Object,Boolean> seen,int depth){
            if(value==null||value instanceof String||value instanceof Boolean)return;
            String type=value.getClass().getName();if(Arrays.asList("java.lang.Byte","java.lang.Short","java.lang.Integer","java.lang.Long","java.lang.Float","java.lang.Double","java.math.BigDecimal","java.math.BigInteger").contains(type))return;
            if(depth>40||seen.put(value,true)!=null)throw new IllegalArgumentException("Cyclic/deep event metadata");
            try{
                if(value instanceof Map&&type.startsWith("java.util.")){for(Object raw:((Map)value).entrySet()){Map.Entry entry=(Map.Entry)raw;if(!(entry.getKey() instanceof String))throw new IllegalArgumentException("Event key is not String");safeEvent(entry.getValue(),seen,depth+1);}return;}
                if(value instanceof Collection&&type.startsWith("java.util.")){for(Object item:(Collection)value)safeEvent(item,seen,depth+1);return;}
                throw new IllegalArgumentException("Live object in event metadata: "+type);
            }finally{seen.remove(value);}
        }
        static synchronized void emit(String kind,Map<String,Object> r){try{if(captureSession!=null){if(historyVersion>0)r.put("session_history_version",historyVersion);if(httpExchange){r.put("http_exchange_version",1);if("metrics".equals(kind))r.put("http_exchange_event_count",seq+1);}r.put("capture_session",captureSession);r.put("process_instance",processInstance);if("metrics".equals(kind))r.put("session_history_event_count",seq+1);}BodyObservationHooks.observe(kind,r);if(Diagnostic.enabled){r.put("diagnostic_monotonic_ns",System.nanoTime());r.put("diagnostic_thread_cpu_ns",Diagnostic.threads.getCurrentThreadCpuTime());if(kind.equals("start"))Diagnostic.start();if(kind.equals("enter"))Diagnostic.active=true;}safeEvent(r,new IdentityHashMap<Object,Boolean>(),0);if(++seq>1000000)throw new IllegalStateException("Event bound");r.put("seq",seq);r.put("kind",kind);r.put("thread",Thread.currentThread().getId());output.write(JSON.writeValueAsString(r));output.newLine();
            // BufferedWriter is bounded (8 KiB chars); the encoder is bounded
            // too. Keep every event in order, but avoid a flush/syscall per
            // instruction while all instrumented workers share this monitor.
            // Offline acceptance still requires a complete metrics footer.
            if(kind.equals("start")||kind.equals("metrics")||kind.equals("problem")||kind.equals("abort"))output.flush();
        }catch(Exception e){throw new IllegalStateException(e);}}
    }
}
