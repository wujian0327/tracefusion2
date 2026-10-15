import java.lang.instrument.*;
import java.lang.reflect.*;
import java.security.ProtectionDomain;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Reusable default-Jackson / Spring HTTP observations, without provenance labels. */
public final class SpringTransportAgent implements ClassFileTransformer,Opcodes {
    static final String R="SpringTransportAgent$Transport";
    public static void premain(String args,Instrumentation i)throws Exception{PlannedServiceAgent.premain(args,i);Transport.start();i.addTransformer(new SpringTransportAgent());}
    public byte[] transform(final ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes){
        if(!Arrays.asList("org/springframework/web/client/RestTemplate","org/springframework/http/client/support/HttpAccessor","org/springframework/http/converter/json/AbstractJackson2HttpMessageConverter").contains(owner))return null;
        try{ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);boolean changed=false;
            boolean typedWrite=false;for(MethodNode m:c.methods)if(m.name.equals("writeInternal")&&m.desc.startsWith("(Ljava/lang/Object;Ljava/lang/reflect/Type;"))typedWrite=true;
            for(MethodNode m:c.methods){
                boolean rpc=owner.endsWith("/RestTemplate")&&m.name.equals("doExecute")&&m.desc.startsWith("(Ljava/net/URI;Lorg/springframework/http/HttpMethod;");
                boolean request=owner.endsWith("/HttpAccessor")&&m.name.equals("createRequest");
                boolean read=owner.endsWith("/AbstractJackson2HttpMessageConverter")&&m.name.equals("readJavaType");
                boolean write=owner.endsWith("/AbstractJackson2HttpMessageConverter")&&m.name.equals("writeInternal")&&(typedWrite?m.desc.startsWith("(Ljava/lang/Object;Ljava/lang/reflect/Type;"):m.desc.startsWith("(Ljava/lang/Object;Lorg/springframework/http/HttpOutputMessage;"));
                if(!(rpc||request||read||write)||(m.access&(ACC_ABSTRACT|ACC_NATIVE))!=0)continue;
                AbstractInsnNode[] original=m.instructions.toArray();LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode();
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
        }catch(Throwable e){PlannedServiceAgent.Recorder.problem("transport-transform:"+owner+":"+e);return null;}
    }
    public static final class Transport {
        static final String HEADER="X-TraceFusion-Message";
        static final ThreadLocal<Deque<Map<String,Object>>> RPC=new ThreadLocal<Deque<Map<String,Object>>>(){protected Deque<Map<String,Object>> initialValue(){return new ArrayDeque<>();}};
        static Map<String,List<Map<String,Object>>> schema;
        static void start(){schema=(Map)PlannedServiceAgent.plan.get("json_schema");if(schema==null)throw new IllegalArgumentException("JSON schema missing");}
        static Object api(Object o,String cls,String method,Class<?>[] types,Object...args)throws Exception{return Class.forName(cls,false,Thread.currentThread().getContextClassLoader()).getMethod(method,types).invoke(o,args);}
        static String incoming()throws Exception{Object a=Class.forName("org.springframework.web.context.request.RequestContextHolder",false,Thread.currentThread().getContextClassLoader()).getMethod("getRequestAttributes").invoke(null);if(a==null)return null;Object req=a.getClass().getMethod("getRequest").invoke(a);String v=(String)api(req,"javax.servlet.http.HttpServletRequest","getHeader",new Class[]{String.class},HEADER);if(v==null){v=(String)api(req,"javax.servlet.http.HttpServletRequest","getAttribute",new Class[]{String.class},"tf.message");if(v==null){v=UUID.randomUUID().toString();api(req,"javax.servlet.http.HttpServletRequest","setAttribute",new Class[]{String.class,Object.class},"tf.message",v);}}return v;}
        static String serverUri()throws Exception{Object a=Class.forName("org.springframework.web.context.request.RequestContextHolder",false,Thread.currentThread().getContextClassLoader()).getMethod("getRequestAttributes").invoke(null);if(a==null)return null;Object req=a.getClass().getMethod("getRequest").invoke(a);return (String)api(req,"javax.servlet.http.HttpServletRequest","getRequestURI",new Class[0]);}
        static Object headers(Object message)throws Exception{return api(message,"org.springframework.http.HttpMessage","getHeaders",new Class[0]);}
        static String header(Object message)throws Exception{return (String)api(headers(message),"org.springframework.http.HttpHeaders","getFirst",new Class[]{String.class},HEADER);}
        static void setHeader(Object message,String id)throws Exception{api(headers(message),"org.springframework.http.HttpHeaders","set",new Class[]{String.class,String.class},HEADER,id);}
        static Map<String,Object> context()throws Exception{Map<String,Object> r=new LinkedHashMap<>();if(!RPC.get().isEmpty()){r.putAll(RPC.get().peek());r.put("direction","request");}else{r.put("message",incoming());r.put("uri",serverUri());r.put("direction","response");}return r;}
        static void emit(String kind,Map<String,Object> r){synchronized(PlannedServiceAgent.Recorder.class){r.put("frame",PlannedServiceAgent.Recorder.row().get("frame"));PlannedServiceAgent.Recorder.emit(kind,r);}}
        public static void rpcEnter(Object uri,Object method){Map<String,Object> r=new LinkedHashMap<>();r.put("message",UUID.randomUUID().toString());r.put("uri",String.valueOf(uri));r.put("method",String.valueOf(method));try{r.put("parent_message",incoming());}catch(Exception e){PlannedServiceAgent.Recorder.problem("http-parent-context:"+e);}RPC.get().push(r);emit("http-rpc-enter",new LinkedHashMap<>(r));}
        public static void rpcExit(){emit("http-rpc-exit",new LinkedHashMap<>(RPC.get().pop()));}
        public static void rpcAbort(){if(!RPC.get().isEmpty())emit("http-rpc-abort",new LinkedHashMap<>(RPC.get().pop()));}
        public static void request(Object req){try{if(!RPC.get().isEmpty())setHeader(req,(String)RPC.get().peek().get("message"));}catch(Throwable e){PlannedServiceAgent.Recorder.problem("http-request:"+e);}}
        static boolean primitive(Object o){return o==null||o instanceof String||o instanceof Number||o instanceof Boolean;}
        static List<Object> snapshot(Object root)throws Exception{List<Object> r=new ArrayList<>();walk(root,"",r,new IdentityHashMap<>(),0);return r;}
        static String escape(String s){return s.replace("~","~0").replace("/","~1");}
        static void walk(Object o,String path,List<Object> result,IdentityHashMap<Object,Boolean> active,int depth)throws Exception{
            if(o==null||primitive(o))return;if(depth>12||result.size()>10000)throw new IllegalStateException("JSON observation bound");if(active.put(o,true)!=null)throw new IllegalStateException("Cyclic JSON object");
            try{if(o instanceof Collection){int i=0;for(Object item:(Collection<?>)o)walk(item,path+"/"+(i++),result,active,depth+1);return;}
                List<Map<String,Object>> props=schema.get(o.getClass().getName().replace('.','/'));if(props==null)return;
                for(Map<String,Object> p:props){String field=(String)p.get("field");Field f=o.getClass().getDeclaredField(field.substring(field.lastIndexOf('.')+1));f.setAccessible(true);Object value=f.get(o);String sub=path+"/"+escape((String)p.get("property"));
                    if(primitive(value)){Map<String,Object> v=new LinkedHashMap<>();v.put("path",sub);synchronized(PlannedServiceAgent.Recorder.class){v.put("owner",PlannedServiceAgent.Recorder.id(o));v.put("field",field);v.put("version",PlannedServiceAgent.Recorder.VERSIONS.getOrDefault(PlannedServiceAgent.Recorder.id(o)+":"+field,0));Map<String,Object> observed=PlannedServiceAgent.Recorder.value(value);if(f.getType().isPrimitive())observed.put("object",null);v.put("observed",observed);}v.put("descriptor",p.get("descriptor"));result.add(v);}
                    else walk(value,sub,result,active,depth+1);
                }
            }finally{active.remove(o);}
        }
        public static Object writeStart(Object body,Object message){try{Map<String,Object> r=context();if(r.get("message")==null)return null;setHeader(message,(String)r.get("message"));r.put("fields",snapshot(body));r.put("phase","write");return r;}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-write-start:"+e);return null;}}
        public static void writeEnd(Object token,Object body){if(token==null)return;try{Map<String,Object> r=(Map)token;if(!r.get("fields").equals(snapshot(body)))throw new IllegalStateException("DTO changed during serialization");emit("http-json",r);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-write-end:"+e);}}
        public static void writeAbort(Object token){if(token!=null)emit("http-json-abort",(Map)token);}
        public static void read(Object body,Object message){try{Map<String,Object> r=new LinkedHashMap<>();if(!RPC.get().isEmpty()){r.putAll(RPC.get().peek());r.put("direction","response");r.put("echo",header(message));}else{r.put("message",incoming());r.put("direction","request");r.put("uri",serverUri());}if(r.get("message")==null)return;r.put("phase","read");r.put("fields",snapshot(body));emit("http-json",r);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-read:"+e);}}
        public static void instrumented(String cls){Map<String,Object> r=new LinkedHashMap<>();r.put("class",cls);emit("http-framework",r);}
    }
}
