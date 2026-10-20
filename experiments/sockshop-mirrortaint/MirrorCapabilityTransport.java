import java.lang.instrument.*;
import java.lang.reflect.*;
import java.security.ProtectionDomain;
import java.util.*;
import java.util.concurrent.Callable;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Shared HTTP/JSON instance evidence only. No dependency graph, taint propagation or oracle. */
public final class MirrorCapabilityTransport implements ClassFileTransformer,Opcodes {
    static final String R="MirrorCapabilityTransport$Transport";
    public static void premain(String args,Instrumentation i)throws Exception{Evidence.start();Transport.start();i.addTransformer(new MirrorCapabilityTransport());}
    public byte[] transform(final ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes){
        if(Evidence.schemaOwners.contains(owner))return observeWrites(owner,bytes);
        if(!Arrays.asList("org/springframework/web/client/RestTemplate","org/springframework/http/client/support/HttpAccessor","org/springframework/http/converter/json/AbstractJackson2HttpMessageConverter","org/springframework/aop/interceptor/AsyncExecutionAspectSupport").contains(owner))return null;
        try{ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);boolean changed=false;
            boolean typedWrite=false;for(MethodNode m:c.methods)if(m.name.equals("writeInternal")&&m.desc.startsWith("(Ljava/lang/Object;Ljava/lang/reflect/Type;"))typedWrite=true;
            for(MethodNode m:c.methods){
                boolean rpc=owner.endsWith("/RestTemplate")&&m.name.equals("doExecute")&&m.desc.startsWith("(Ljava/net/URI;Lorg/springframework/http/HttpMethod;");
                boolean async=owner.endsWith("/AsyncExecutionAspectSupport")&&m.name.equals("doSubmit")&&m.desc.startsWith("(Ljava/util/concurrent/Callable;");
                boolean request=owner.endsWith("/HttpAccessor")&&m.name.equals("createRequest");
                boolean read=owner.endsWith("/AbstractJackson2HttpMessageConverter")&&m.name.equals("readJavaType");
                boolean write=owner.endsWith("/AbstractJackson2HttpMessageConverter")&&m.name.equals("writeInternal")&&(typedWrite?m.desc.startsWith("(Ljava/lang/Object;Ljava/lang/reflect/Type;"):m.desc.startsWith("(Ljava/lang/Object;Lorg/springframework/http/HttpOutputMessage;"));
                if(!(rpc||request||read||write||async)||(m.access&(ACC_ABSTRACT|ACC_NATIVE))!=0)continue;
                AbstractInsnNode[] original=m.instructions.toArray();LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode();
                if(async){InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,1));h.add(new MethodInsnNode(INVOKESTATIC,R,"wrap","(Ljava/util/concurrent/Callable;)Ljava/util/concurrent/Callable;",false));h.add(new VarInsnNode(ASTORE,1));m.instructions.insert(h);}
                if(rpc){InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,1));h.add(new VarInsnNode(ALOAD,2));h.add(new MethodInsnNode(INVOKESTATIC,R,"rpcEnter","(Ljava/lang/Object;Ljava/lang/Object;)V",false));h.add(start);m.instructions.insert(h);}
                int token=-1;
                if(write){token=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,1));h.add(new VarInsnNode(ALOAD,typedWrite?3:2));h.add(new MethodInsnNode(INVOKESTATIC,R,"writeStart","(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,token));h.add(start);m.instructions.insert(h);}
                for(AbstractInsnNode n:original)if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN){InsnList h=new InsnList();
                    if(request){h.add(new InsnNode(DUP));h.add(new MethodInsnNode(INVOKESTATIC,R,"request","(Ljava/lang/Object;)V",false));}
                    if(read){h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,2));h.add(new MethodInsnNode(INVOKESTATIC,R,"read","(Ljava/lang/Object;Ljava/lang/Object;)V",false));}
                    if(write){h.add(new VarInsnNode(ALOAD,token));h.add(new VarInsnNode(ALOAD,1));h.add(new MethodInsnNode(INVOKESTATIC,R,"writeEnd","(Ljava/lang/Object;Ljava/lang/Object;)V",false));}
                    if(rpc)h.add(new MethodInsnNode(INVOKESTATIC,R,"rpcExit","()V",false));m.instructions.insertBefore(n,h);
                }
                if(rpc||write){m.instructions.add(end);m.instructions.add(handler);int error=m.maxLocals++;m.instructions.add(new VarInsnNode(ASTORE,error));if(rpc)m.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"rpcAbort","()V",false));else{m.instructions.add(new VarInsnNode(ALOAD,token));m.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"writeAbort","(Ljava/lang/Object;)V",false));}m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));}changed=true;
            }
            if(!changed)throw new IllegalStateException("No supported framework methods: "+owner);
            ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){try{Class<?> x=Class.forName(a.replace('/','.'),false,loader),y=Class.forName(b.replace('/','.'),false,loader);if(x.isAssignableFrom(y))return a;if(y.isAssignableFrom(x))return b;if(x.isInterface()||y.isInterface())return "java/lang/Object";do{x=x.getSuperclass();}while(!x.isAssignableFrom(y));return x.getName().replace('.','/');}catch(Exception e){throw new IllegalStateException(e);}}};c.accept(w);Transport.instrumented(owner);return w.toByteArray();
        }catch(Throwable e){Evidence.problem("transport-transform:"+owner+":"+e);return null;}
    }

    static byte[] observeWrites(String owner,byte[] bytes){
        ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,0);
        for(MethodNode m:c.methods)for(AbstractInsnNode n:m.instructions.toArray()){
            if(!(n instanceof FieldInsnNode)||n.getOpcode()!=PUTFIELD)continue;
            FieldInsnNode f=(FieldInsnNode)n;if(!Evidence.schemaOwners.contains(f.owner))continue;
            org.objectweb.asm.Type t=org.objectweb.asm.Type.getType(f.desc);int slot=m.maxLocals;m.maxLocals+=t.getSize();
            InsnList h=new InsnList();h.add(new VarInsnNode(t.getOpcode(ISTORE),slot));h.add(new InsnNode(DUP));h.add(new VarInsnNode(t.getOpcode(ILOAD),slot));
            m.instructions.insertBefore(n,h);InsnList end=new InsnList();end.add(new LdcInsnNode(f.owner+"."+f.name));
            end.add(new MethodInsnNode(INVOKESTATIC,"MirrorCapabilityTransport","written","(Ljava/lang/Object;Ljava/lang/String;)V",false));m.instructions.insert(n,end);
        }
        ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS);c.accept(w);return w.toByteArray();
    }
    public static void written(Object owner,String field){synchronized(Evidence.class){String key=Evidence.id(owner)+":"+field;Evidence.VERSIONS.put(key,Evidence.VERSIONS.getOrDefault(key,0)+1);}}
    public static void rpcStarted(String id){Evidence.PENDING.set(id);}
    public static Map<String,Object> fieldCoordinate(Object owner,String field){
        synchronized(Evidence.class){Map<String,Object> r=new LinkedHashMap<>();r.put("owner",Evidence.id(owner));r.put("field",field);r.put("version",Evidence.VERSIONS.getOrDefault(Evidence.id(owner)+":"+field,0));return r;}
    }
    public static Map<String,Object> currentContext(){try{return Transport.context();}catch(Exception e){throw new IllegalStateException(e);}}
    public static final class Evidence {
        static java.io.BufferedWriter output;static long seq;static Map<String,Object> plan;
        static final Set<String> schemaOwners=new HashSet<>();
        static final IdentityHashMap<Object,String> IDS=new IdentityHashMap<>();
        static final Map<String,Integer> VERSIONS=new HashMap<>();
        static final ThreadLocal<String> PENDING=new ThreadLocal<>();
        static final com.fasterxml.jackson.databind.ObjectMapper JSON=new com.fasterxml.jackson.databind.ObjectMapper();
        static void start()throws Exception{
            byte[] bytes=java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(System.getProperty("instance.schema")));
            plan=JSON.readValue(bytes,Map.class);schemaOwners.addAll(((Map<String,Object>)plan.get("json_schema")).keySet());
            output=java.nio.file.Files.newBufferedWriter(java.nio.file.Paths.get(System.getProperty("instance.events")),java.nio.file.StandardOpenOption.CREATE_NEW);
            Map<String,Object> first=new LinkedHashMap<>();first.put("schema_sha256",hash(bytes));emit("start",first);
            Runtime.getRuntime().addShutdownHook(new Thread(()->{synchronized(Evidence.class){emit("metrics",new LinkedHashMap<String,Object>());}}));
        }
        static String hash(byte[] b)throws Exception{StringBuilder s=new StringBuilder();for(byte x:java.security.MessageDigest.getInstance("SHA-256").digest(b))s.append(String.format("%02x",x&255));return s.toString();}
        static String id(Object o){if(o==null)return null;String s=IDS.get(o);if(s==null){s="o"+(IDS.size()+1);IDS.put(o,s);}return s;}
        static Map<String,Object> row(){return new LinkedHashMap<>();}
        static Map<String,Object> value(Object o){Map<String,Object> r=new LinkedHashMap<>();r.put("object",id(o));if(o==null||o instanceof Number||o instanceof String||o instanceof Boolean)r.put("value",o);else if(o instanceof Date)r.put("value",((Date)o).getTime());else if(o instanceof UUID||o instanceof Character||o instanceof java.net.URI||o.getClass().isEnum())r.put("value",String.valueOf(o));return r;}
        static void emit(String kind,Map<String,Object> r){try{r.put("seq",++seq);r.put("kind",kind);r.put("thread",Thread.currentThread().getId());output.write(JSON.writeValueAsString(r));output.newLine();output.flush();}catch(Exception e){throw new IllegalStateException(e);}}
        static synchronized void problem(String why){Map<String,Object> r=new LinkedHashMap<>();r.put("message",why);emit("problem",r);System.err.println("INSTANCE_PROBE error="+why);}
    }
    public static final class Transport {
        static final String HEADER="traceparent",STATE="tracestate";
        static final ThreadLocal<Deque<Map<String,Object>>> RPC=new ThreadLocal<Deque<Map<String,Object>>>(){protected Deque<Map<String,Object>> initialValue(){return new ArrayDeque<>();}};
        static final ThreadLocal<Deque<W3CTraceContext>> SPANS=new ThreadLocal<Deque<W3CTraceContext>>(){protected Deque<W3CTraceContext> initialValue(){return new ArrayDeque<>();}};
        static final ThreadLocal<W3CTraceContext> ASYNC=new ThreadLocal<>();
        static Map<String,List<Map<String,Object>>> schema;
        static void start(){schema=(Map)Evidence.plan.get("json_schema");if(schema==null)throw new IllegalArgumentException("JSON schema missing");}
        static Object api(Object o,String cls,String method,Class<?>[] types,Object...args)throws Exception{return Class.forName(cls,false,Thread.currentThread().getContextClassLoader()).getMethod(method,types).invoke(o,args);}
        static Object servlet()throws Exception{Object a=Class.forName("org.springframework.web.context.request.RequestContextHolder",false,Thread.currentThread().getContextClassLoader()).getMethod("getRequestAttributes").invoke(null);return a==null?null:a.getClass().getMethod("getRequest").invoke(a);}
        static String incomingHeader(Object req,String name)throws Exception{Enumeration<?> vs=(Enumeration<?>)api(req,"javax.servlet.http.HttpServletRequest","getHeaders",new Class[]{String.class},name);List<String> values=new ArrayList<>();while(vs.hasMoreElements())values.add(String.valueOf(vs.nextElement()));return values.isEmpty()?null:String.join(",",values);}
        static W3CTraceContext incomingContext()throws Exception{
            Object req=servlet();if(req==null)return ASYNC.get();
            Object cached=api(req,"javax.servlet.http.HttpServletRequest","getAttribute",new Class[]{String.class},"tf.w3c.context");if(cached!=null)return (W3CTraceContext)cached;
            String parent=incomingHeader(req,HEADER);
            String state=incomingHeader(req,STATE);
            W3CTraceContext c=W3CTraceContext.server(parent,state);api(req,"javax.servlet.http.HttpServletRequest","setAttribute",new Class[]{String.class,Object.class},"tf.w3c.context",c);Map<String,Object> audit=c.fields();audit.put("wire_traceparent",parent);audit.put("wire_tracestate",state);audit.put("uri",serverUri());emit("http-server-context",audit);return c;
        }
        static W3CTraceContext current()throws Exception{return SPANS.get().isEmpty()?incomingContext():SPANS.get().peek();}
        static String serverUri()throws Exception{Object req=servlet();return req==null?null:(String)api(req,"javax.servlet.http.HttpServletRequest","getRequestURI",new Class[0]);}
        static Object headers(Object message)throws Exception{return api(message,"org.springframework.http.HttpMessage","getHeaders",new Class[0]);}
        static void setHeader(Object message,String name,String value)throws Exception{api(headers(message),"org.springframework.http.HttpHeaders","set",new Class[]{String.class,String.class},name,value);}
        static Map<String,Object> context()throws Exception{Map<String,Object> r=new LinkedHashMap<>();if(!RPC.get().isEmpty()){r.putAll(RPC.get().peek());r.put("direction","request");}else{W3CTraceContext c=incomingContext();if(c==null)return r;r.putAll(c.fields());r.put("uri",serverUri());r.put("direction","response");}return r;}
        static void emit(String kind,Map<String,Object> r){synchronized(Evidence.class){r.put("frame",Evidence.row().get("frame"));Evidence.emit(kind,r);}}
        public static Callable<Object> wrap(final Callable<?> work){
            try{final W3CTraceContext captured=current();return new Callable<Object>(){public Object call()throws Exception{W3CTraceContext previous=ASYNC.get();try{if(captured==null)ASYNC.remove();else ASYNC.set(captured);return work.call();}finally{if(previous==null)ASYNC.remove();else ASYNC.set(previous);}}};}
            catch(Exception e){Evidence.problem("http-async-context:"+e);return (Callable)work;}
        }
        public static void rpcEnter(Object uri,Object method){
            W3CTraceContext parent=null;try{parent=current();}catch(Exception e){Evidence.problem("http-parent-context:"+e);}
            W3CTraceContext c=W3CTraceContext.client(parent);Map<String,Object> r=c.fields();r.put("uri",String.valueOf(uri));r.put("method",String.valueOf(method));r.put("parent_message",parent==null?null:parent.message());r.put("mt_rpc_event_id",Evidence.PENDING.get());Evidence.PENDING.remove();SPANS.get().push(c);RPC.get().push(r);emit("http-rpc-enter",new LinkedHashMap<>(r));
        }
        public static void rpcExit(){emit("http-rpc-exit",new LinkedHashMap<>(RPC.get().pop()));SPANS.get().pop();}
        public static void rpcAbort(){if(!RPC.get().isEmpty()){emit("http-rpc-abort",new LinkedHashMap<>(RPC.get().pop()));SPANS.get().pop();}}
        public static void request(Object req){try{if(!SPANS.get().isEmpty()){W3CTraceContext c=SPANS.get().peek();setHeader(req,HEADER,c.wire());if(c.state!=null)setHeader(req,STATE,c.state);else api(headers(req),"java.util.Map","remove",new Class[]{Object.class},STATE);Map<String,Object> audit=new LinkedHashMap<>(RPC.get().peek());audit.put("wire_traceparent",api(headers(req),"org.springframework.http.HttpHeaders","getFirst",new Class[]{String.class},HEADER));audit.put("wire_tracestate",api(headers(req),"org.springframework.http.HttpHeaders","getFirst",new Class[]{String.class},STATE));emit("http-request-context",audit);}}catch(Throwable e){Evidence.problem("http-request:"+e);}}
        static boolean primitive(Object o){return o==null||o instanceof String||o instanceof Number||o instanceof Boolean||o instanceof Date||o instanceof UUID||o instanceof Character||o instanceof java.net.URI||o.getClass().isEnum();}
        static List<Object> snapshot(Object root)throws Exception{List<Object> r=new ArrayList<>();walk(root,"",r,new IdentityHashMap<>(),0);return r;}
        static String escape(String s){return s.replace("~","~0").replace("/","~1");}
        static void cell(Object container,Object value,String field,String path,List<Object> result){
            Map<String,Object> v=new LinkedHashMap<>();v.put("path",path);v.putAll(MirrorCapabilityTransport.fieldCoordinate(container,field));v.put("observed",Evidence.value(value));v.put("descriptor","Ljava/lang/Object;");v.put("coordinate_scope","observed-container-slot");result.add(v);
        }
        static void walk(Object o,String path,List<Object> result,IdentityHashMap<Object,Boolean> active,int depth)throws Exception{
            if(o==null||primitive(o))return;if(depth>12||result.size()>10000)throw new IllegalStateException("JSON observation bound");if(active.put(o,true)!=null)throw new IllegalStateException("Cyclic JSON object");
            try{if(o instanceof Collection){int i=0;for(Object item:(Collection<?>)o){String sub=path+"/"+i;if(primitive(item))cell(o,item,"@list:"+i,sub,result);else walk(item,sub,result,active,depth+1);i++;}return;}
                if(o instanceof Map){for(Map.Entry<?,?> e:((Map<?,?>)o).entrySet()){if(!(e.getKey() instanceof String))throw new IllegalStateException("Nonstring JSON Map key");String key=(String)e.getKey(),sub=path+"/"+escape(key);if(primitive(e.getValue()))cell(o,e.getValue(),"@map:"+escape(key),sub,result);else walk(e.getValue(),sub,result,active,depth+1);}return;}
                List<Map<String,Object>> props=schema.get(o.getClass().getName().replace('.','/'));if(props==null)return;
                for(Map<String,Object> p:props){String field=(String)p.get("field");Field f=o.getClass().getDeclaredField(field.substring(field.lastIndexOf('.')+1));f.setAccessible(true);Object value=f.get(o);String sub=path+"/"+escape((String)p.get("property"));
                    if(primitive(value)){Map<String,Object> v=new LinkedHashMap<>();v.put("path",sub);synchronized(Evidence.class){v.put("owner",Evidence.id(o));v.put("field",field);v.put("version",Evidence.VERSIONS.getOrDefault(Evidence.id(o)+":"+field,0));Map<String,Object> observed=Evidence.value(value);if(f.getType().isPrimitive())observed.put("object",null);v.put("observed",observed);}v.put("descriptor",p.get("descriptor"));result.add(v);}
                    else walk(value,sub,result,active,depth+1);
                }
            }finally{active.remove(o);}
        }
        public static Object writeStart(Object body,Object message){try{Map<String,Object> r=context();if(r.get("message")==null)return null;r.put("fields",snapshot(body));r.put("phase","write");return r;}catch(Throwable e){Evidence.problem("json-write-start:"+e);return null;}}
        public static void writeEnd(Object token,Object body){if(token==null)return;try{Map<String,Object> r=(Map)token;if(!r.get("fields").equals(snapshot(body)))throw new IllegalStateException("DTO changed during serialization");emit("http-json",r);}catch(Throwable e){Evidence.problem("json-write-end:"+e);}}
        public static void writeAbort(Object token){if(token!=null)emit("http-json-abort",(Map)token);}
        public static void read(Object body,Object message){try{Map<String,Object> r=new LinkedHashMap<>();if(!RPC.get().isEmpty()){r.putAll(RPC.get().peek());r.put("direction","response");}else{W3CTraceContext c=incomingContext();if(c==null)return;r.putAll(c.fields());r.put("direction","request");r.put("uri",serverUri());}if(r.get("message")==null)return;r.put("phase","read");r.put("fields",snapshot(body));emit("http-json",r);}catch(Throwable e){Evidence.problem("json-read:"+e);}}
        public static void instrumented(String cls){Map<String,Object> r=new LinkedHashMap<>();r.put("class",cls);emit("http-framework",r);}
    }
}
