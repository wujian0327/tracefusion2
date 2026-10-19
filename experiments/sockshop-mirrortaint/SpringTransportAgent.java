import java.lang.instrument.*;
import java.lang.reflect.*;
import java.security.ProtectionDomain;
import java.util.*;
import java.util.concurrent.Callable;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Reusable default-Jackson / Spring HTTP observations, without provenance labels. */
public final class SpringTransportAgent implements ClassFileTransformer,Opcodes {
    static final String R="SpringTransportAgent$Transport";
    public static void premain(String args,Instrumentation i)throws Exception{PlannedServiceAgent.premain(args,i);Transport.start();i.addTransformer(new SpringTransportAgent());}
    public byte[] transform(final ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes){
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
                if(write){token=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,1));h.add(new VarInsnNode(ALOAD,typedWrite?3:2));h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKEVIRTUAL,owner,"getObjectMapper","()Lcom/fasterxml/jackson/databind/ObjectMapper;",false));h.add(new MethodInsnNode(INVOKESTATIC,R,"writeStartWithMapper","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,token));h.add(start);m.instructions.insert(h);}
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
        }catch(Throwable e){PlannedServiceAgent.Recorder.problem("transport-transform:"+owner+":"+e);return null;}
    }
    public static final class Transport {
        static final String HEADER="traceparent",STATE="tracestate";
        static final ThreadLocal<Deque<Map<String,Object>>> RPC=new ThreadLocal<Deque<Map<String,Object>>>(){protected Deque<Map<String,Object>> initialValue(){return new ArrayDeque<>();}};
        static final ThreadLocal<Deque<W3CTraceContext>> SPANS=new ThreadLocal<Deque<W3CTraceContext>>(){protected Deque<W3CTraceContext> initialValue(){return new ArrayDeque<>();}};
        static final ThreadLocal<W3CTraceContext> ASYNC=new ThreadLocal<>();
        static Map<String,List<Map<String,Object>>> schema;
        static void start(){schema=(Map)PlannedServiceAgent.plan.get("json_schema");if(schema==null)throw new IllegalArgumentException("JSON schema missing");}
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
        static void emit(String kind,Map<String,Object> r){synchronized(PlannedServiceAgent.Recorder.class){r.put("frame",PlannedServiceAgent.Recorder.row().get("frame"));PlannedServiceAgent.Recorder.emit(kind,r);}}
        public static Callable<Object> wrap(final Callable<?> work){
            try{final W3CTraceContext captured=current();return new Callable<Object>(){public Object call()throws Exception{W3CTraceContext previous=ASYNC.get();try{if(captured==null)ASYNC.remove();else ASYNC.set(captured);return work.call();}finally{if(previous==null)ASYNC.remove();else ASYNC.set(previous);}}};}
            catch(Exception e){PlannedServiceAgent.Recorder.problem("http-async-context:"+e);return (Callable)work;}
        }
        public static void rpcEnter(Object uri,Object method){
            W3CTraceContext parent=null;try{parent=current();}catch(Exception e){PlannedServiceAgent.Recorder.problem("http-parent-context:"+e);}
            W3CTraceContext c=W3CTraceContext.client(parent);Map<String,Object> r=c.fields();r.put("uri",String.valueOf(uri));r.put("method",String.valueOf(method));r.put("parent_message",parent==null?null:parent.message());SPANS.get().push(c);RPC.get().push(r);emit("http-rpc-enter",new LinkedHashMap<>(r));
        }
        public static void rpcExit(){emit("http-rpc-exit",new LinkedHashMap<>(RPC.get().pop()));SPANS.get().pop();}
        public static void rpcAbort(){if(!RPC.get().isEmpty()){emit("http-rpc-abort",new LinkedHashMap<>(RPC.get().pop()));SPANS.get().pop();}}
        public static void request(Object req){try{if(!SPANS.get().isEmpty()){W3CTraceContext c=SPANS.get().peek();setHeader(req,HEADER,c.wire());if(c.state!=null)setHeader(req,STATE,c.state);else api(headers(req),"java.util.Map","remove",new Class[]{Object.class},STATE);Map<String,Object> audit=new LinkedHashMap<>(RPC.get().peek());audit.put("wire_traceparent",api(headers(req),"org.springframework.http.HttpHeaders","getFirst",new Class[]{String.class},HEADER));audit.put("wire_tracestate",api(headers(req),"org.springframework.http.HttpHeaders","getFirst",new Class[]{String.class},STATE));emit("http-request-context",audit);}}catch(Throwable e){PlannedServiceAgent.Recorder.problem("http-request:"+e);}}
        static boolean primitive(Object o){return o==null||o instanceof String||o instanceof Number||o instanceof Boolean;}
        static List<Object> snapshot(Object root)throws Exception{List<Object> r=new ArrayList<>();walk(root,"",r,new IdentityHashMap<>(),0,null);return r;}
        static List<Object> conversionSnapshot(Object root)throws Exception{List<Object> r=new ArrayList<>();walk(root,"",r,new IdentityHashMap<>(),0,"@conversion");return r;}
        static String escape(String s){return s.replace("~","~0").replace("/","~1");}
        static void element(Object container,String field,Object value,String path,String anchor,List<Object> result){Map<String,Object> v=new LinkedHashMap<>();v.put("path",path);synchronized(PlannedServiceAgent.Recorder.class){v.put("owner",PlannedServiceAgent.Recorder.id(container));v.put("field",field);v.put("version",CollectionServiceHooks.epoch(container));v.put("observed",PlannedServiceAgent.Recorder.value(value));}v.put("descriptor","Ljava/lang/Object;");v.put("schema_field",anchor);result.add(v);}
        static void walk(Object o,String path,List<Object> result,IdentityHashMap<Object,Boolean> active,int depth,String anchor)throws Exception{
            if(o==null||primitive(o))return;if(depth>12||result.size()>10000)throw new IllegalStateException("JSON observation bound");if(active.put(o,true)!=null)throw new IllegalStateException("Cyclic JSON object");
            try{if(o instanceof Collection){int i=0;for(Object item:(Collection<?>)o){String sub=path+"/"+i;if(Boolean.TRUE.equals(PlannedServiceAgent.plan.get("collection_elements"))&&o instanceof List&&anchor!=null&&primitive(item))element(o,"@list:"+i,item,sub,anchor,result);else walk(item,sub,result,active,depth+1,anchor);i++;}return;}
                if(o instanceof Map&&Boolean.TRUE.equals(PlannedServiceAgent.plan.get("collection_elements"))){for(Object k:((Map)o).keySet()){if(!(k instanceof String))throw new IllegalStateException("Only String map keys admitted");Object item=((Map)o).get(k);String sub=path+"/"+escape((String)k);if(anchor!=null&&primitive(item))element(o,"@map:"+k,item,sub,anchor,result);else walk(item,sub,result,active,depth+1,anchor);}return;}
                List<Map<String,Object>> props=schema.get(o.getClass().getName().replace('.','/'));if(props==null)return;
                for(Map<String,Object> p:props){String field=(String)p.get("field");Field f=o.getClass().getDeclaredField(field.substring(field.lastIndexOf('.')+1));f.setAccessible(true);Object value=f.get(o);String sub=path+"/"+escape((String)p.get("property"));
                    if(primitive(value)){Map<String,Object> v=new LinkedHashMap<>();v.put("path",sub);synchronized(PlannedServiceAgent.Recorder.class){v.put("owner",PlannedServiceAgent.Recorder.id(o));v.put("field",field);v.put("version",PlannedServiceAgent.Recorder.VERSIONS.getOrDefault(PlannedServiceAgent.Recorder.id(o)+":"+field,0));Map<String,Object> observed=PlannedServiceAgent.Recorder.value(value);if(f.getType().isPrimitive())observed.put("object",null);v.put("observed",observed);}v.put("descriptor",p.get("descriptor"));result.add(v);}
                    else walk(value,sub,result,active,depth+1,field);
                }
            }finally{active.remove(o);}
        }
        public static Object writeStartWithMapper(Object body,Object message,Object mapper){try{ResponseBindingHooks.verifySerialization(body,mapper);return writeStart(body,message);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("binding-serializer:"+e);return null;}}
        public static Object writeStart(Object body,Object message){try{Map<String,Object> r=context();if(r.get("message")==null)return null;r.put("fields",snapshot(body));r.put("phase","write");return r;}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-write-start:"+e);return null;}}
        public static void writeEnd(Object token,Object body){if(token==null)return;try{Map<String,Object> r=(Map)token;if(!r.get("fields").equals(snapshot(body)))throw new IllegalStateException("DTO changed during serialization");emit("http-json",r);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-write-end:"+e);}}
        public static void writeAbort(Object token){if(token!=null)emit("http-json-abort",(Map)token);}
        static void received(Object o,IdentityHashMap<Object,Boolean> seen)throws Exception{if(o==null||primitive(o)||seen.put(o,true)!=null)return;if(o instanceof List){CollectionServiceHooks.received(o);for(Object v:(List)o)received(v,seen);}else if(o instanceof Map){CollectionServiceHooks.received(o);for(Object v:((Map)o).values())received(v,seen);}else{List<Map<String,Object>> props=schema.get(o.getClass().getName().replace('.','/'));if(props!=null)for(Map p:props){String name=(String)p.get("field");Field f=o.getClass().getDeclaredField(name.substring(name.lastIndexOf('.')+1));f.setAccessible(true);received(f.get(o),seen);}}}
        public static void read(Object body,Object message){try{Map<String,Object> r=new LinkedHashMap<>();if(!RPC.get().isEmpty()){r.putAll(RPC.get().peek());r.put("direction","response");}else{W3CTraceContext c=incomingContext();if(c==null)return;r.putAll(c.fields());r.put("direction","request");r.put("uri",serverUri());}if(r.get("message")==null)return;r.put("phase","read");r.put("fields",snapshot(body));if(Boolean.TRUE.equals(PlannedServiceAgent.plan.get("collection_elements")))received(body,new IdentityHashMap<>());emit("http-json",r);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-read:"+e);}}
        public static void instrumented(String cls){Map<String,Object> r=new LinkedHashMap<>();r.put("class",cls);emit("http-framework",r);}
    }
}
