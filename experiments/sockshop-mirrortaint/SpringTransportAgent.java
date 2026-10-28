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
        if(TemporalDateHooks.effects()!=null&&owner.equals("com/mongodb/CompoundDBObjectCodec")){
            try{Map pins=(Map)TemporalDateHooks.effects().get("codec_class_sha256");if(!PlannedServiceAgent.Recorder.hash(bytes).equals(pins.get(owner)))throw new IllegalStateException("Date encoder hash differs");ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);for(MethodNode m:c.methods)if(m.name.equals("encode")&&m.desc.contains("Lcom/mongodb/DBObject;")){InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKESTATIC,"SaveEffectHooks","codec","(Ljava/lang/Object;)V",false));m.instructions.insert(h);}MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS);c.accept(w);return w.toByteArray();}catch(Throwable e){PlannedServiceAgent.Recorder.problem("date-codec-transform:"+e);return null;}
        }
        if(SaveEffectHooks.config()!=null&&(owner.equals("org/springframework/data/mongodb/repository/support/SimpleMongoRepository")||owner.equals("org/springframework/context/event/SimpleApplicationEventMulticaster")||owner.equals("org/springframework/context/event/ApplicationListenerMethodAdapter"))){
            try{
                Map pins=(Map)SaveEffectHooks.config().get("class_sha256");if(!PlannedServiceAgent.Recorder.hash(bytes).equals(pins.get(owner)))throw new IllegalStateException("Save framework hash differs");
                ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);boolean changed=false;
                for(MethodNode m:c.methods){
                    if(owner.endsWith("/SimpleMongoRepository")&&m.name.equals("save")&&m.desc.equals("(Ljava/lang/Object;)Ljava/lang/Object;")){
                        int token=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,0));h.add(new VarInsnNode(ALOAD,1));h.add(new MethodInsnNode(INVOKESTATIC,"SaveEffectHooks","begin","(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,token));m.instructions.insert(h);
                        for(AbstractInsnNode n:m.instructions.toArray())if(n.getOpcode()==ARETURN){InsnList end=new InsnList();end.add(new InsnNode(DUP));end.add(new VarInsnNode(ALOAD,token));end.add(new InsnNode(SWAP));end.add(new MethodInsnNode(INVOKESTATIC,"SaveEffectHooks","end","(Ljava/lang/Object;Ljava/lang/Object;)V",false));m.instructions.insertBefore(n,end);}changed=true;
                    }
                    if(owner.endsWith("/SimpleApplicationEventMulticaster"))for(AbstractInsnNode n:m.instructions.toArray())if(n instanceof MethodInsnNode&&((MethodInsnNode)n).name.equals("getApplicationListeners")){InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,0));h.add(new VarInsnNode(ALOAD,1));h.add(new MethodInsnNode(INVOKESTATIC,"SaveEffectHooks","listeners","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V",false));m.instructions.insert(n,h);changed=true;}
                    if(owner.endsWith("/ApplicationListenerMethodAdapter")&&m.name.equals("doInvoke")){InsnList h=new InsnList();h.add(new MethodInsnNode(INVOKESTATIC,"SaveEffectHooks","handler","()V",false));m.instructions.insert(h);changed=true;}
                }
                if(changed){MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS);c.accept(w);return w.toByteArray();}return null;
            }catch(Throwable e){PlannedServiceAgent.Recorder.problem("save-transform:"+e);return null;}
        }
        if(!Arrays.asList("org/springframework/web/client/RestTemplate","org/springframework/http/client/support/HttpAccessor","org/springframework/http/converter/json/AbstractJackson2HttpMessageConverter","org/springframework/aop/interceptor/AsyncExecutionAspectSupport","org/springframework/aop/interceptor/AsyncExecutionInterceptor$1","org/springframework/aop/interceptor/AsyncExecutionInterceptor","org/springframework/scheduling/annotation/AsyncResult").contains(owner))return null;
        try{boolean protocol=AsyncTaskHooks.enabled();
            if(protocol&&((Map)AsyncTaskHooks.config().get("class_sha256")).containsKey(owner))AsyncTaskHooks.framework(owner,bytes);
            boolean worker=owner.equals("org/springframework/aop/interceptor/AsyncExecutionInterceptor$1");
            if(owner.equals("org/springframework/aop/interceptor/AsyncExecutionInterceptor")||owner.equals("org/springframework/scheduling/annotation/AsyncResult")||(worker&&!protocol))return null;
            ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);boolean changed=false;
            boolean typedWrite=false;for(MethodNode m:c.methods)if(m.name.equals("writeInternal")&&m.desc.startsWith("(Ljava/lang/Object;Ljava/lang/reflect/Type;"))typedWrite=true;
            for(MethodNode m:c.methods){
                boolean rpc=owner.endsWith("/RestTemplate")&&m.name.equals("doExecute")&&m.desc.startsWith("(Ljava/net/URI;Lorg/springframework/http/HttpMethod;");
                boolean async=owner.endsWith("/AsyncExecutionAspectSupport")&&m.name.equals("doSubmit")&&m.desc.startsWith("(Ljava/util/concurrent/Callable;");
                boolean request=owner.endsWith("/HttpAccessor")&&m.name.equals("createRequest");
                boolean read=owner.endsWith("/AbstractJackson2HttpMessageConverter")&&m.name.equals("readJavaType");
                boolean write=owner.endsWith("/AbstractJackson2HttpMessageConverter")&&m.name.equals("writeInternal")&&(typedWrite?m.desc.startsWith("(Ljava/lang/Object;Ljava/lang/reflect/Type;"):m.desc.startsWith("(Ljava/lang/Object;Lorg/springframework/http/HttpOutputMessage;"));
                boolean workerCall=worker&&m.name.equals("call")&&m.desc.equals("()Ljava/lang/Object;");
                if(!(rpc||request||read||write||async||workerCall)||(m.access&(ACC_ABSTRACT|ACC_NATIVE))!=0)continue;
                AbstractInsnNode[] original=m.instructions.toArray();LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode();
                if(async){InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,1));h.add(new MethodInsnNode(INVOKESTATIC,R,"wrap","(Ljava/util/concurrent/Callable;)Ljava/util/concurrent/Callable;",false));h.add(new VarInsnNode(ASTORE,1));if(protocol)h.add(start);m.instructions.insert(h);}
                if(read){InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,2));h.add(new MethodInsnNode(INVOKESTATIC,"SourceEvidenceHooks","input","(Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new TypeInsnNode(CHECKCAST,"org/springframework/http/HttpInputMessage"));h.add(new VarInsnNode(ASTORE,2));h.add(start);m.instructions.insert(h);}
                int rpcToken=-1;
                if(rpc){rpcToken=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,1));h.add(new VarInsnNode(ALOAD,2));h.add(new MethodInsnNode(INVOKESTATIC,R,"rpcEnter","(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,rpcToken));h.add(start);m.instructions.insert(h);}
                int token=-1;
                if(write){token=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,1));h.add(new VarInsnNode(ALOAD,typedWrite?3:2));h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKEVIRTUAL,owner,"getObjectMapper","()Lcom/fasterxml/jackson/databind/ObjectMapper;",false));h.add(new MethodInsnNode(INVOKESTATIC,R,"writeStartWithMapper","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,token));h.add(start);m.instructions.insert(h);}
                if(workerCall)for(AbstractInsnNode n:original)if(n instanceof MethodInsnNode){MethodInsnNode call=(MethodInsnNode)n;
                    String hook=call.owner.equals("org/aopalliance/intercept/MethodInvocation")&&call.name.equals("proceed")?"inner":call.owner.equals("java/util/concurrent/Future")&&call.name.equals("get")?"unwrapped":null;
                    if(hook!=null){InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new MethodInsnNode(INVOKESTATIC,"AsyncTaskHooks",hook,"(Ljava/lang/Object;)V",false));m.instructions.insert(n,h);}
                }
                for(AbstractInsnNode n:original)if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN){InsnList h=new InsnList();
                    if(async&&protocol){h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,1));h.add(new InsnNode(SWAP));h.add(new MethodInsnNode(INVOKESTATIC,"AsyncTaskHooks","submitted","(Ljava/util/concurrent/Callable;Ljava/lang/Object;)V",false));}
                    if(request){h.add(new InsnNode(DUP));h.add(new MethodInsnNode(INVOKESTATIC,R,"request","(Ljava/lang/Object;)V",false));}
                    if(read){h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,2));h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKEVIRTUAL,owner,"getObjectMapper","()Lcom/fasterxml/jackson/databind/ObjectMapper;",false));h.add(new MethodInsnNode(INVOKESTATIC,"SourceEvidenceHooks","read","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V",false));h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKEVIRTUAL,owner,"getObjectMapper","()Lcom/fasterxml/jackson/databind/ObjectMapper;",false));h.add(new VarInsnNode(ALOAD,1));h.add(new MethodInsnNode(INVOKESTATIC,R,"decoder","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V",false));h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,2));h.add(new MethodInsnNode(INVOKESTATIC,R,"read","(Ljava/lang/Object;Ljava/lang/Object;)V",false));}
                    if(write){h.add(new VarInsnNode(ALOAD,token));h.add(new VarInsnNode(ALOAD,1));h.add(new MethodInsnNode(INVOKESTATIC,R,"writeEnd","(Ljava/lang/Object;Ljava/lang/Object;)V",false));}
                    if(rpc){h.add(new VarInsnNode(ALOAD,rpcToken));h.add(new MethodInsnNode(INVOKESTATIC,R,"rpcExit","(Ljava/lang/Object;)V",false));}m.instructions.insertBefore(n,h);
                }
                if(async&&protocol){m.instructions.add(end);m.instructions.add(handler);int error=m.maxLocals++;m.instructions.add(new VarInsnNode(ASTORE,error));m.instructions.add(new VarInsnNode(ALOAD,1));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new MethodInsnNode(INVOKESTATIC,"AsyncTaskHooks","rejected","(Ljava/util/concurrent/Callable;Ljava/lang/Throwable;)V",false));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));}
                if(rpc||write||read){m.instructions.add(end);m.instructions.add(handler);int error=m.maxLocals++;m.instructions.add(new VarInsnNode(ASTORE,error));if(rpc){m.instructions.add(new VarInsnNode(ALOAD,rpcToken));m.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"rpcAbort","(Ljava/lang/Object;)V",false));}else if(read){m.instructions.add(new VarInsnNode(ALOAD,2));m.instructions.add(new MethodInsnNode(INVOKESTATIC,"SourceEvidenceHooks","abort","(Ljava/lang/Object;)V",false));}else{m.instructions.add(new VarInsnNode(ALOAD,token));m.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"writeAbort","(Ljava/lang/Object;)V",false));}m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));}changed=true;
            }
            if(!changed)throw new IllegalStateException("No supported framework methods: "+owner);
            MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){try{Class<?> x=Class.forName(a.replace('/','.'),false,loader),y=Class.forName(b.replace('/','.'),false,loader);if(x.isAssignableFrom(y))return a;if(y.isAssignableFrom(x))return b;if(x.isInterface()||y.isInterface())return "java/lang/Object";do{x=x.getSuperclass();}while(!x.isAssignableFrom(y));return x.getName().replace('.','/');}catch(Exception e){throw new IllegalStateException(e);}}};c.accept(w);Transport.instrumented(owner);return w.toByteArray();
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
            try{final W3CTraceContext captured=current();Callable<Object> contextual=new Callable<Object>(){public Object call()throws Exception{W3CTraceContext previous=ASYNC.get();try{if(captured==null)ASYNC.remove();else ASYNC.set(captured);return work.call();}finally{if(previous==null)ASYNC.remove();else ASYNC.set(previous);}}};return AsyncTaskHooks.enabled()?AsyncTaskHooks.wrap(work,contextual):contextual;}
            catch(Exception e){PlannedServiceAgent.Recorder.problem("http-async-context:"+e);return (Callable)work;}
        }
        static final class RpcScope {
            final Deque<Map<String,Object>> beforeRPC=new ArrayDeque<>(RPC.get());final Deque<W3CTraceContext> beforeSpans=new ArrayDeque<>(SPANS.get());
            Map<String,Object> own;boolean closed;
            void restore(){RPC.get().clear();RPC.get().addAll(beforeRPC);SPANS.get().clear();SPANS.get().addAll(beforeSpans);}
        }
        public static Object rpcEnter(Object uri,Object method){
            RpcScope token=new RpcScope();try{
                W3CTraceContext parent=current();W3CTraceContext c=W3CTraceContext.client(parent);Map<String,Object> r=c.fields();r.put("uri",String.valueOf(uri));r.put("method",String.valueOf(method));r.put("parent_message",parent==null?null:parent.message());token.own=r;SPANS.get().push(c);RPC.get().push(r);MonitorSafety.fault("rpc-enter","rpc");emit("http-rpc-enter",new LinkedHashMap<>(r));return token;
            }catch(Throwable failure){MonitorSafety.fatal(failure);token.restore();token.closed=true;MonitorSafety.failed("rpc-enter",failure);return token;}
        }
        static void rpcFinish(Object object,boolean aborted){
            if(!(object instanceof RpcScope))return;RpcScope token=(RpcScope)object;if(token.closed)return;token.closed=true;
            try{if(RPC.get().peek()!=token.own||SPANS.get().size()!=token.beforeSpans.size()+1)throw new IllegalStateException("RPC completion owner differs");MonitorSafety.fault(aborted?"rpc-abort":"rpc-exit","rpc");emit(aborted?"http-rpc-abort":"http-rpc-exit",new LinkedHashMap<>(token.own));}
            catch(Throwable failure){MonitorSafety.fatal(failure);MonitorSafety.failed("rpc-completion",failure);}finally{token.restore();}
        }
        public static void rpcExit(Object token){rpcFinish(token,false);}
        public static void rpcAbort(Object token){rpcFinish(token,true);}
        public static void request(Object req){try{if(!SPANS.get().isEmpty()){W3CTraceContext c=SPANS.get().peek();setHeader(req,HEADER,c.wire());if(c.state!=null)setHeader(req,STATE,c.state);else api(headers(req),"java.util.Map","remove",new Class[]{Object.class},STATE);Map<String,Object> audit=new LinkedHashMap<>(RPC.get().peek());audit.put("wire_traceparent",api(headers(req),"org.springframework.http.HttpHeaders","getFirst",new Class[]{String.class},HEADER));audit.put("wire_tracestate",api(headers(req),"org.springframework.http.HttpHeaders","getFirst",new Class[]{String.class},STATE));emit("http-request-context",audit);}}catch(Throwable e){PlannedServiceAgent.Recorder.problem("http-request:"+e);}}
        static boolean primitive(Object o){return o==null||o instanceof String||o instanceof Number||o instanceof Boolean||TemporalDateHooks.date(o)||UuidProjectionHooks.uuid(o);}
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
                    if(primitive(value)){Map<String,Object> v=new LinkedHashMap<>();v.put("path",sub);synchronized(PlannedServiceAgent.Recorder.class){v.put("owner",PlannedServiceAgent.Recorder.id(o));v.put("field",field);v.put("version",PlannedServiceAgent.Recorder.VERSIONS.getOrDefault(PlannedServiceAgent.Recorder.id(o)+":"+field,0));Map<String,Object> observed=PlannedServiceAgent.Recorder.value(value);if(f.getType().isPrimitive())observed.put("object",null);v.put("observed",observed);}v.put("descriptor",p.get("descriptor"));TemporalDateHooks.wire(value,v);result.add(v);}
                    else walk(value,sub,result,active,depth+1,field);
                }
            }finally{active.remove(o);}
        }
        static Map queryTransportPolicy(Map context)throws Exception{
            Object raw=PlannedServiceAgent.plan.get("transport_evidence_policy");
            if(raw==null)return null;
            if(!(raw instanceof Map)||!Integer.valueOf(2).equals(((Map)raw).get("version")))throw new IllegalStateException("Unknown query transport evidence policy");
            Map policy=(Map)raw,binding=(Map)PlannedServiceAgent.plan.get("response_binding");
            if(binding==null||!binding.get("path").equals(policy.get("response_path")))throw new IllegalStateException("Transport projection differs from query binding");
            if(!"response".equals(context.get("direction")))return null;
            synchronized(PlannedServiceAgent.Recorder.class){if(!ResponseBindingHooks.RETURN_MESSAGES.contains(context.get("message")))return null;}
            return policy;
        }
        static boolean projectQueryFields(Map policy){return "selective".equals(PlannedServiceAgent.mode)&&policy!=null&&Boolean.TRUE.equals(policy.get("project_bound_response_fields"));}
        static List<Object> queryResponseFields(List<Object> fields,String pattern){
            List<Object> chosen=new ArrayList<>();String[] target=pattern.split("/",-1);
            for(Object raw:fields){Map field=(Map)raw;String[] path=((String)field.get("path")).split("/",-1);if(path.length!=target.length)continue;boolean match=true;
                for(int i=0;i<path.length;i++)if(!target[i].equals(path[i])&&!(target[i].equals("*")&&path[i].matches("[0-9]+")))match=false;
                if(match)chosen.add(raw);
            }
            return chosen;
        }
        public static Object writeStartWithMapper(Object body,Object message,Object mapper){try{BusinessJackson.observe(mapper);ResponseBindingHooks.verifySerialization(body,mapper);Object token=writeStart(body,message);if(token!=null&&RequestEntityHooks.config()!=null){Map r=(Map)token,policy=queryTransportPolicy(r);if(policy==null||!Boolean.TRUE.equals(policy.get("request_proofs_outbound_only")))r.put("request_serialization",RequestEntityHooks.serialization(body,mapper));}return token;}catch(Throwable e){PlannedServiceAgent.Recorder.problem("binding-serializer:"+e);return null;}}
        public static Object writeStart(Object body,Object message){try{Map<String,Object> r=context();if(r.get("message")==null)return null;r.put("fields",snapshot(body));r.put("phase","write");return r;}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-write-start:"+e);return null;}}
        public static void writeEnd(Object token,Object body){if(token==null)return;try{Map<String,Object> r=(Map)token;if(!r.get("fields").equals(snapshot(body)))throw new IllegalStateException("DTO changed during serialization");Map policy=queryTransportPolicy(r);if(projectQueryFields(policy))r.put("fields",queryResponseFields((List)r.get("fields"),(String)policy.get("response_path")));emit("http-json",r);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-write-end:"+e);}}
        public static void writeAbort(Object token){if(token!=null)emit("http-json-abort",(Map)token);}
        static void received(Object o,IdentityHashMap<Object,Boolean> seen)throws Exception{if(o==null||primitive(o)||seen.put(o,true)!=null)return;if(o instanceof List){CollectionServiceHooks.received(o);for(Object v:(List)o)received(v,seen);}else if(o instanceof Map){CollectionServiceHooks.received(o);for(Object v:((Map)o).values())received(v,seen);}else{List<Map<String,Object>> props=schema.get(o.getClass().getName().replace('.','/'));if(props!=null)for(Map p:props){String name=(String)p.get("field");Field f=o.getClass().getDeclaredField(name.substring(name.lastIndexOf('.')+1));f.setAccessible(true);received(f.get(o),seen);}}}
        static final ThreadLocal<Map> DECODER=new ThreadLocal<Map>();
        public static void decoder(Object body,Object mapper,Object type){synchronized(PlannedServiceAgent.Recorder.class){try{BusinessJackson.observe(mapper);Map r=new LinkedHashMap();RequestEntityHooks.decoded(body,mapper,type,r);DECODER.set(r);}catch(Throwable e){DECODER.remove();PlannedServiceAgent.Recorder.problem("request-decoder:"+e);}}}
        public static void read(Object body,Object message){try{Map<String,Object> r=new LinkedHashMap<>();if(!RPC.get().isEmpty()){r.putAll(RPC.get().peek());r.put("direction","response");}else{W3CTraceContext c=incomingContext();if(c==null)return;r.putAll(c.fields());r.put("direction","request");r.put("uri",serverUri());}if(r.get("message")==null)return;r.put("phase","read");Map decoder=DECODER.get();DECODER.remove();if(decoder!=null)r.putAll(decoder);if(FrameworkCallHooks.config()!=null||RequestEntityHooks.config()!=null){r.put("decoded_body",PlannedServiceAgent.Recorder.value(body));r.put("decoded_type",body==null?null:body.getClass().getName());}List<Object> projected=snapshot(body);if(decoder!=null&&decoder.get("resource_decoder")!=null){Map d=(Map)decoder.get("resource_decoder");if(Boolean.TRUE.equals(d.get("valid"))){projected=new ArrayList<>();for(Object raw:(List)d.get("fields")){Map field=(Map)raw;String path=(String)field.get("path");if(((List)d.get("source_properties")).contains(path.substring(1)))projected.add(raw);}}}r.put("fields",projected);if(Boolean.TRUE.equals(PlannedServiceAgent.plan.get("collection_elements")))received(body,new IdentityHashMap<>());emit("http-json",r);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-read:"+e);}}
        public static void instrumented(String cls){Map<String,Object> r=new LinkedHashMap<>();r.put("class",cls);emit("http-framework",r);}
    }
}
