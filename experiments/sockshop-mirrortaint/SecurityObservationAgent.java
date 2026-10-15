import java.io.*;
import java.lang.instrument.*;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Opt-in bounded security frontend. Observes values/identities/versions/branch outcomes.
 * Does not set or propagate provenance labels. Offline replay consumes its class model.
 */
public final class SecurityObservationAgent implements ClassFileTransformer, Opcodes {
    static final String R="SecurityObservationAgent$Recorder";
    public static void premain(String args, Instrumentation instrumentation) throws Exception {
        Recorder.start();instrumentation.addTransformer(new SecurityObservationAgent());
    }
    public byte[] transform(ClassLoader loader,String name,Class<?> prior,ProtectionDomain domain,byte[] bytes) {
        boolean flow="SecurityLeakLab$Flow".equals(name),wire="SecurityLeakLab$Wire".equals(name),sink="SecurityLeakLab$Sink".equals(name);
        boolean jndi="org/apache/logging/log4j/core/lookup/JndiLookup".equals(name);
        if (!flow&&!wire&&!sink&&!jndi) return null;
        try {
            ClassNode clazz=new ClassNode(ASM9);new ClassReader(bytes).accept(clazz,ClassReader.EXPAND_FRAMES);
            for(MethodNode method:clazz.methods) {
                if(flow&&method.name.equals("run")) instrumentFlow(method);
                if(wire&&method.name.equals("send")) {
                    InsnList hook=new InsnList();hook.add(new VarInsnNode(ALOAD,1));hook.add(new VarInsnNode(ALOAD,2));hook.add(new VarInsnNode(ALOAD,3));
                    hook.add(new MethodInsnNode(INVOKESTATIC,R,"send","(Ljava/lang/Object;Ljava/lang/String;[B)V",false));method.instructions.insert(hook);
                }
                if(sink&&method.name.equals("write")) for(AbstractInsnNode n:method.instructions.toArray()) if(n instanceof MethodInsnNode) {
                    MethodInsnNode call=(MethodInsnNode)n;
                    if(call.owner.equals("org/apache/logging/log4j/Logger")&&call.name.equals("info")&&call.desc.equals("(Ljava/lang/String;)V")) {
                        InsnList hook=new InsnList();hook.add(new InsnNode(DUP));hook.add(new MethodInsnNode(INVOKESTATIC,R,"logArgument","(Ljava/lang/Object;)V",false));method.instructions.insertBefore(n,hook);
                    }
                }
                if(jndi&&method.name.equals("lookup")&&method.desc.equals("(Lorg/apache/logging/log4j/core/LogEvent;Ljava/lang/String;)Ljava/lang/String;")) {
                    InsnList hook=new InsnList();hook.add(new VarInsnNode(ALOAD,2));hook.add(new MethodInsnNode(INVOKESTATIC,R,"lookup","(Ljava/lang/String;)V",false));method.instructions.insert(hook);
                }
            }
            ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_FRAMES|ClassWriter.COMPUTE_MAXS) {
                protected String getCommonSuperClass(String a,String b) { return "java/lang/Object"; }
            };
            clazz.accept(writer);
            Map<String,Object> event=new LinkedHashMap<>();event.put("class",name);event.put("sha256",Recorder.hash(bytes));Recorder.emit("transformed",event);
            Files.write(Paths.get(System.getProperty("lab.events")).getParent().resolve(name.replace('/','_')+".original.class"),bytes);
            return writer.toByteArray();
        } catch(Throwable error) { Recorder.problem("transform:"+name+":"+error);return null; }
    }
    static void instrumentFlow(MethodNode method) {
        List<AbstractInsnNode> code=new ArrayList<>();for(AbstractInsnNode n:method.instructions.toArray()) if(n.getOpcode()>=0)code.add(n);
        Map<AbstractInsnNode,Integer> indices=new IdentityHashMap<>();for(int i=0;i<code.size();i++)indices.put(code.get(i),i);
        List<Object> model=new ArrayList<>();
        for(int i=0;i<code.size();i++) {
            AbstractInsnNode n=code.get(i);Map<String,Object> row=new LinkedHashMap<>();row.put("site",i);row.put("op",n.getOpcode());
            if(n instanceof VarInsnNode)row.put("var",((VarInsnNode)n).var);
            if(n instanceof TypeInsnNode)row.put("type",((TypeInsnNode)n).desc);
            if(n instanceof LdcInsnNode)row.put("constant",String.valueOf(((LdcInsnNode)n).cst));
            if(n instanceof FieldInsnNode) {FieldInsnNode f=(FieldInsnNode)n;row.put("owner",f.owner);row.put("name",f.name);row.put("desc",f.desc);observeField(method,f,i);}
            if(n instanceof MethodInsnNode) {
                MethodInsnNode call=(MethodInsnNode)n;row.put("owner",call.owner);row.put("name",call.name);row.put("desc",call.desc);
                if(call.owner.equals("SecurityLeakLab$Sink")&&call.name.equals("write")) {
                    InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new LdcInsnNode(i));h.add(new MethodInsnNode(INVOKESTATIC,R,"sinkArgument","(Ljava/lang/Object;I)V",false));method.instructions.insertBefore(n,h);
                }
            }
            if(n instanceof JumpInsnNode) {
                JumpInsnNode jump=(JumpInsnNode)n;AbstractInsnNode target=jump.label;while(target!=null&&target.getOpcode()<0)target=target.getNext();
                row.put("target",indices.get(target));
                if(n.getOpcode()!=GOTO) {
                    LabelNode original=jump.label,taken=new LabelNode(),next=new LabelNode();jump.label=taken;
                    InsnList hook=new InsnList();branch(hook,i,false);hook.add(new JumpInsnNode(GOTO,next));hook.add(taken);branch(hook,i,true);hook.add(new JumpInsnNode(GOTO,original));hook.add(next);method.instructions.insert(n,hook);
                }
            }
            model.add(row);
        }
        Map<String,Object> event=new LinkedHashMap<>();event.put("method",method.name+method.desc);event.put("instructions",model);Recorder.emit("model",event);
        InsnList entry=new InsnList();entry.add(new VarInsnNode(ALOAD,0));entry.add(new VarInsnNode(ALOAD,2));entry.add(new VarInsnNode(ALOAD,3));entry.add(new VarInsnNode(ALOAD,4));
        entry.add(new MethodInsnNode(INVOKESTATIC,R,"enter","(Ljava/lang/Object;Ljava/lang/String;[BLjava/lang/String;)V",false));
        LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode();entry.add(start);method.instructions.insert(entry);
        for(AbstractInsnNode n:code)if(n.getOpcode()==RETURN) {InsnList exit=new InsnList();exit.add(new MethodInsnNode(INVOKESTATIC,R,"exit","()V",false));method.instructions.insertBefore(n,exit);}
        method.instructions.add(end);method.instructions.add(handler);int slot=method.maxLocals++;
        method.instructions.add(new VarInsnNode(ASTORE,slot));method.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"abort","()V",false));method.instructions.add(new VarInsnNode(ALOAD,slot));method.instructions.add(new InsnNode(ATHROW));
        method.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));
    }
    static void branch(InsnList code,int site,boolean taken) {
        code.add(new LdcInsnNode(site));code.add(new InsnNode(taken?ICONST_1:ICONST_0));code.add(new MethodInsnNode(INVOKESTATIC,R,"branch","(IZ)V",false));
    }
    static void observeField(MethodNode method,FieldInsnNode field,int site) {
        if(field.getOpcode()!=GETFIELD&&field.getOpcode()!=PUTFIELD)return;
        if(!field.desc.startsWith("L"))throw new IllegalStateException("Only reference fields supported");
        int object=method.maxLocals++,value=method.maxLocals++;InsnList before=new InsnList(),after=new InsnList();
        if(field.getOpcode()==GETFIELD) {before.add(new InsnNode(DUP));before.add(new VarInsnNode(ASTORE,object));after.add(new InsnNode(DUP));after.add(new VarInsnNode(ASTORE,value));}
        else {before.add(new VarInsnNode(ASTORE,value));before.add(new VarInsnNode(ASTORE,object));before.add(new VarInsnNode(ALOAD,object));before.add(new VarInsnNode(ALOAD,value));}
        after.add(new VarInsnNode(ALOAD,object));after.add(new LdcInsnNode(field.owner+"."+field.name));after.add(new VarInsnNode(ALOAD,value));after.add(new LdcInsnNode(site));after.add(new InsnNode(field.getOpcode()==PUTFIELD?ICONST_1:ICONST_0));
        after.add(new MethodInsnNode(INVOKESTATIC,R,"field","(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/Object;IZ)V",false));method.instructions.insertBefore(field,before);method.instructions.insert(field,after);
    }
    public static final class Recorder {
        static BufferedWriter output;static long sequence,frames;static final String PROCESS=UUID.randomUUID().toString();
        static final IdentityHashMap<Object,String> IDS=new IdentityHashMap<>();static final Map<String,Integer> VERSIONS=new HashMap<>();
        static final ThreadLocal<String> FRAME=new ThreadLocal<>();
        public static void start() throws IOException {output=Files.newBufferedWriter(Paths.get(System.getProperty("lab.events")),StandardCharsets.UTF_8);emit("start",new LinkedHashMap<>());}
        static String id(Object object) {if(object==null)return null;String value=IDS.get(object);if(value==null){value="o"+(IDS.size()+1);IDS.put(object,value);}return value;}
        static Map<String,Object> context() {Map<String,Object> r=new LinkedHashMap<>();r.put("frame",FRAME.get());r.put("thread",Thread.currentThread().getId());return r;}
        static Map<String,Object> value(Object object) {Map<String,Object> r=new LinkedHashMap<>();r.put("object",id(object));r.put("value",object==null?null:String.valueOf(object));return r;}
        static List<Object> snapshot(Object object) throws Exception {
            List<Object> rows=new ArrayList<>();for(Field field:object.getClass().getFields())if(field.getType()==String.class) {
                Map<String,Object> r=new LinkedHashMap<>();r.put("owner",id(object));r.put("field",object.getClass().getName()+"."+field.getName());r.put("property",field.getName());
                r.put("version",VERSIONS.getOrDefault(id(object)+":"+r.get("field"),0));r.put("observed",value(field.get(object)));rows.add(r);
            }return rows;
        }
        public static synchronized void send(Object record,String message,byte[] bytes) {
            try {Map<String,Object> r=context();r.put("message",message);r.put("fields",snapshot(record));r.put("wire",new String(bytes,StandardCharsets.UTF_8));r.put("wire_sha256",hash(bytes));emit("http-send",r);}catch(Exception e){problem(e.toString());}
        }
        public static synchronized void enter(Object record,String message,byte[] bytes,String request) {
            try {if(FRAME.get()!=null)throw new IllegalStateException("Nested flow");FRAME.set("f"+(++frames));Map<String,Object> r=context();r.put("record",id(record));r.put("message",message);r.put("request_id",request);r.put("fields",snapshot(record));r.put("wire",new String(bytes,StandardCharsets.UTF_8));r.put("wire_sha256",hash(bytes));emit("enter",r);}catch(Exception e){problem(e.toString());}
        }
        public static synchronized void field(Object owner,String field,Object value,int site,boolean write) {
            Map<String,Object> r=context();String key=id(owner)+":"+field;int v=VERSIONS.getOrDefault(key,0);if(write)VERSIONS.put(key,++v);
            r.put("owner",id(owner));r.put("field",field);r.put("version",v);r.put("observed",value(value));r.put("site",site);emit(write?"write":"read",r);
        }
        public static synchronized void branch(int site,boolean taken) {Map<String,Object> r=context();r.put("site",site);r.put("taken",taken);emit("branch",r);}
        public static synchronized void sinkArgument(Object value,int site) {Map<String,Object> r=context();r.put("site",site);r.put("observed",value(value));emit("sink-argument",r);}
        public static synchronized void logArgument(Object value) {Map<String,Object> r=context();r.put("observed",value(value));emit("log-argument",r);}
        public static synchronized void lookup(String key) {Map<String,Object> r=context();r.put("key",key);emit("jndi-lookup",r);}
        public static synchronized void exit() {emit("exit",context());FRAME.remove();}
        public static synchronized void abort() {emit("abort",context());FRAME.remove();}
        public static synchronized void problem(String text) {Map<String,Object> r=context();r.put("error",text);emit("problem",r);}
        public static String hash(byte[] bytes) {try {StringBuilder s=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))s.append(String.format("%02x",b&255));return s.toString();}catch(Exception e){throw new IllegalStateException(e);}}
        static synchronized void emit(String kind,Map<String,Object> row) {
            try {row.put("kind",kind);row.put("seq",++sequence);row.put("process",PROCESS);output.write(json(row));output.newLine();output.flush();}catch(IOException e){throw new IllegalStateException(e);}
        }
        static String json(Object value) {
            if(value==null)return "null";if(value instanceof Number||value instanceof Boolean)return value.toString();
            if(value instanceof Map){StringJoiner j=new StringJoiner(",","{","}");for(Map.Entry<?,?> e:((Map<?,?>)value).entrySet())j.add(json(e.getKey().toString())+":"+json(e.getValue()));return j.toString();}
            if(value instanceof Iterable){StringJoiner j=new StringJoiner(",","[","]");for(Object item:(Iterable<?>)value)j.add(json(item));return j.toString();}
            String s=value.toString();StringBuilder b=new StringBuilder("\"");for(int i=0;i<s.length();i++){char c=s.charAt(i);if(c=='"'||c=='\\')b.append('\\').append(c);else if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}return b.append('"').toString();
        }
    }
}
