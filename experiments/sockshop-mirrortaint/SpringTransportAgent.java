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
    /** Versioned message observations. Does not compute dependency edges. */
    public static final class Communication {
        static final String H="SpringTransportAgent$Communication",SYNC="feign/SynchronousMethodHandler",DEFAULT="feign/Client$Default",LB="org/springframework/cloud/openfeign/loadbalancer/FeignBlockingLoadBalancerClient",ADAPTER="org.springframework.cloud.openfeign.support.SpringDecoder$FeignResponseAdapter";
        static final ThreadLocal<Deque<Exchange>> ACTIVE=ThreadLocal.withInitial(ArrayDeque::new);
        static final Map<Object,Object> SERVER_INPUTS=Collections.synchronizedMap(new WeakHashMap<Object,Object>());
        static long calls;
        static final Set<Class<?>> VERIFIED=Collections.newSetFromMap(new IdentityHashMap<Class<?>,Boolean>());
        static void verify(Class<?> c)throws Exception{synchronized(PlannedServiceAgent.Recorder.class){String name=c.getName().replace('.','/');String hash=ExecutionKernelHooks.classHash(c);if(!hash.equals(((Map)config().get("class_sha256")).get(name)))throw new IllegalStateException("Communication runtime class differs: "+name);if(VERIFIED.add(c)){Map r=new LinkedHashMap();r.put("class",name);r.put("class_sha256",hash);emit("communication-class",r);}}}
        static Map config(){return PlannedServiceAgent.plan==null?null:(Map)PlannedServiceAgent.plan.get("communication_identity");}
        static boolean enabled(){return config()!=null;}
        static boolean owns(String name){return enabled()&&Arrays.asList(SYNC,DEFAULT,"feign/okhttp/OkHttpClient",LB,"org/springframework/cloud/openfeign/loadbalancer/RetryableFeignBlockingLoadBalancerClient","feign/Response","feign/Response$Builder","org/springframework/web/servlet/mvc/method/annotation/AbstractMessageConverterMethodArgumentResolver$EmptyBodyCheckingHttpInputMessage").contains(name);}
        static Object invoke(Object o,String name)throws Exception{return o.getClass().getMethod(name).invoke(o);}
        static Map context(Exchange e){return new LinkedHashMap(e.rpc.own);}
        static String id(Object o){return PlannedServiceAgent.Recorder.id(o);}
        static void emit(String kind,Map row){Transport.emit(kind,row);}
        static String header(Object request,String key)throws Exception{Map<String,Collection<String>> headers=(Map)invoke(request,"headers");List<String> values=new ArrayList<>();for(Map.Entry<String,Collection<String>> p:headers.entrySet())if(p.getKey().equalsIgnoreCase(key))values.addAll(p.getValue());return values.isEmpty()?null:String.join(",",values);}
        static final class Exchange {
            final Deque<Exchange> before=new ArrayDeque<>(ACTIVE.get());
            Transport.RpcScope rpc;Object original,wire,networkRequest,networkResponse;
            final Set<Object> requests=Collections.newSetFromMap(new IdentityHashMap<Object,Boolean>());
            final Map<Object,Object> responses=new IdentityHashMap<>(),builders=new IdentityHashMap<>();
            boolean closed,networkDone;
            void restore(){ACTIVE.get().clear();ACTIVE.get().addAll(before);}
        }
        public static Object begin(Object request){synchronized(PlannedServiceAgent.Recorder.class){Exchange e=new Exchange();try{
            e.original=request;e.rpc=(Transport.RpcScope)Transport.rpcEnterKind(invoke(request,"url"),invoke(request,"httpMethod"),"feign-synchronous-attempt");
            if(e.rpc.closed){e.closed=true;return e;}
            Map<String,Collection<String>> headers=new LinkedHashMap<>();for(Object raw:((Map)invoke(request,"headers")).entrySet()){Map.Entry p=(Map.Entry)raw;if(!p.getKey().toString().equalsIgnoreCase("traceparent")&&!p.getKey().toString().equalsIgnoreCase("tracestate"))headers.put(p.getKey().toString(),new ArrayList((Collection)p.getValue()));}
            headers.put("traceparent",Collections.singletonList("00-"+e.rpc.own.get("trace_id")+"-"+e.rpc.own.get("span_id")+"-"+e.rpc.own.get("trace_flags")));if(e.rpc.own.get("tracestate")!=null)headers.put("tracestate",Collections.singletonList((String)e.rpc.own.get("tracestate")));
            ClassLoader loader=request.getClass().getClassLoader();Class<?> type=Class.forName("feign.Request",false,loader),method=Class.forName("feign.Request$HttpMethod",false,loader),template=Class.forName("feign.RequestTemplate",false,loader);
            e.wire=type.getMethod("create",method,String.class,Map.class,byte[].class,java.nio.charset.Charset.class,template).invoke(null,invoke(request,"httpMethod"),invoke(request,"url"),headers,invoke(request,"body"),invoke(request,"charset"),invoke(request,"requestTemplate"));
            if(!Arrays.equals((byte[])invoke(request,"body"),(byte[])invoke(e.wire,"body")))throw new IllegalStateException("Tracing changed Feign request body");
            verify(e.wire.getClass());e.requests.add(e.wire);ACTIVE.get().push(e);Map row=context(e);row.put("original_request",id(request));row.put("request_object",id(e.wire));emit("http-client-attempt",row);return e;
        }catch(Throwable failure){MonitorSafety.fatal(failure);if(e.rpc!=null)Transport.rpcAbort(e.rpc);e.restore();e.closed=true;MonitorSafety.failed("communication-begin",failure);return e;}}}
        public static Object wireRequest(Object token,Object original){return token instanceof Exchange&&!((Exchange)token).closed?((Exchange)token).wire:original;}
        public static void finish(Object token,Throwable error){synchronized(PlannedServiceAgent.Recorder.class){if(!(token instanceof Exchange))return;Exchange e=(Exchange)token;if(e.closed)return;e.closed=true;try{
            if(ACTIVE.get().peek()!=e)throw new IllegalStateException("Communication completion owner differs");
            if(error==null&&(!e.networkDone||e.networkResponse==null))throw new IllegalStateException("Successful Feign attempt has no actual client completion");
        }catch(Throwable failure){MonitorSafety.fatal(failure);MonitorSafety.failed("communication-finish",failure);}finally{if(error==null)Transport.rpcExit(e.rpc);else Transport.rpcAbort(e.rpc);e.restore();}}}
        static Exchange active(){return ACTIVE.get().peek();}
        public static Object networkBegin(Object request,Object client)throws Exception{synchronized(PlannedServiceAgent.Recorder.class){Exchange e=active();if(e==null)return null;verify(client.getClass());
            if(e.networkRequest!=null||!e.requests.contains(request))throw new IllegalStateException("Unpaired/repeated physical client invocation");
            String parent="00-"+e.rpc.own.get("trace_id")+"-"+e.rpc.own.get("span_id")+"-"+e.rpc.own.get("trace_flags");if(!parent.equals(header(request,"traceparent")))throw new IllegalStateException("Actual client wire context differs");
            e.networkRequest=request;Map row=context(e);role(row,"client-send-request",id(request));row.put("client_class",client.getClass().getName().replace('.','/'));row.put("request_object",id(request));row.put("wire_traceparent",parent);row.put("wire_uri",invoke(request,"url"));emit("http-client-send",row);return e;
        }}
        public static void networkEnd(Object token,Object response,Throwable error)throws Exception{synchronized(PlannedServiceAgent.Recorder.class){if(!(token instanceof Exchange))return;Exchange e=(Exchange)token;if(e.networkDone)throw new IllegalStateException("Repeated client completion");e.networkDone=true;Map row=context(e);row.put("request_object",id(e.networkRequest));
            if(error==null){verify(response.getClass());if(invoke(response,"request")!=e.networkRequest)throw new IllegalStateException("Actual response belongs to another request");e.networkResponse=response;e.responses.put(response,response);role(row,"client-receive-response",id(response));row.put("response_object",id(response));emit("http-client-receive",row);}
            else{row.put("exception_object",id(error));emit("http-client-failure",row);}
        }}
        public static void derivedRequest(Object parent,Object child,String owner)throws Exception{synchronized(PlannedServiceAgent.Recorder.class){Exchange e=active();if(e==null)return;if(!e.requests.contains(parent))throw new IllegalStateException("Derived request has foreign parent");if(!Objects.equals(header(parent,"traceparent"),header(child,"traceparent")))throw new IllegalStateException("Derived request changed wire identity");e.requests.add(child);Map r=context(e);r.put("parent_request",id(parent));r.put("request_object",id(child));r.put("derivation_class",owner);emit("http-request-derived",r);}}
        public static void builder(Object parent,Object builder){synchronized(PlannedServiceAgent.Recorder.class){Exchange e=active();if(e!=null&&e.responses.containsKey(parent))e.builders.put(builder,parent);}}
        public static void built(Object builder,Object response)throws Exception{synchronized(PlannedServiceAgent.Recorder.class){Exchange e=active();if(e==null||!e.builders.containsKey(builder))return;Object parent=e.builders.remove(builder);if(!e.requests.contains(invoke(response,"request"))||invoke(response,"body")!=invoke(parent,"body"))throw new IllegalStateException("Response replacement has unpaired request/body");e.responses.put(response,e.responses.get(parent));Map r=context(e);r.put("parent_response",id(parent));r.put("response_object",id(response));r.put("request_object",id(invoke(response,"request")));r.put("network_response_object",id(e.networkResponse));r.put("body_object",id(invoke(response,"body")));r.put("parent_body_object",id(invoke(parent,"body")));emit("http-response-derived",r);}}
        public static void returned(Object token,Object response)throws Exception{synchronized(PlannedServiceAgent.Recorder.class){if(!(token instanceof Exchange)||((Exchange)token).closed)return;Exchange e=(Exchange)token;if(!e.responses.containsKey(response))throw new IllegalStateException("Client returned an unpaired response");}}
        static void role(Map r,String role,String object){r.put("communication_version",2);r.put("communication_role",role);r.put("message_instance",object);r.put("communication_message",r.get("message")+(role.endsWith("request")?"|request":"|response"));}
        static Object servletRequest(Object message)throws Exception{
            Object direct=SERVER_INPUTS.get(message);if(direct!=null)return direct;
            if(message!=null&&message.getClass().getName().equals("org.springframework.http.server.ServletServerHttpRequest")){verify(message.getClass());return invoke(message,"getServletRequest");}return null;
        }
        public static void serverInput(Object wrapper,Object original)throws Exception{synchronized(PlannedServiceAgent.Recorder.class){Object req=servletRequest(original);if(req!=null){SERVER_INPUTS.put(wrapper,req);Map r=new LinkedHashMap(Transport.incomingContext().fields());r.put("carrier_object",id(wrapper));r.put("parent_carrier",id(original));r.put("request_object",id(req));emit("http-server-input",r);}}}
        static Map codec(Object message,boolean read)throws Exception{
            Map r;Object original=message;List wrappers=new ArrayList();
            while(read&&message!=null&&message.getClass().getName().equals("org.springframework.web.client.MessageBodyClientHttpResponseWrapper")){
                if(wrappers.size()>=4)throw new IllegalStateException("Cyclic/deep response carrier");verify(message.getClass());Field f=message.getClass().getDeclaredField("response");f.setAccessible(true);Object delegate=f.get(message);Map edge=new LinkedHashMap();edge.put("wrapper",id(message));edge.put("delegate",id(delegate));edge.put("class",message.getClass().getName().replace('.','/'));edge.put("class_sha256",ExecutionKernelHooks.classHash(message.getClass()));wrappers.add(edge);message=delegate;
            }
            if(read&&message!=null&&message.getClass().getName().equals(ADAPTER)){
                verify(message.getClass());
                Exchange e=active();if(e==null)throw new IllegalStateException("Feign decoder has no actual attempt");Field field=message.getClass().getDeclaredField("response");field.setAccessible(true);Object response=field.get(message);
                if(!e.responses.containsKey(response)||!e.requests.contains(invoke(response,"request")))throw new IllegalStateException("Decoder belongs to another response");
                r=context(e);role(r,"client-receive-response",id(e.responses.get(response)));r.put("response_object",id(response));r.put("network_response_object",id(e.responses.get(response)));r.put("request_object",id(invoke(response,"request")));r.put("direction","response");
            }else if(read&&servletRequest(message)!=null){Object req=servletRequest(message);if(req!=Transport.servlet())throw new IllegalStateException("Request decoder has foreign servlet request");r=new LinkedHashMap(Transport.incomingContext().fields());r.put("uri",Transport.serverUri());role(r,"server-receive-request",id(req));r.put("request_object",id(req));r.put("direction","request");
            }else if(!read&&message!=null&&message.getClass().getName().equals("org.springframework.http.server.ServletServerHttpResponse")){
                verify(message.getClass());W3CTraceContext c=Transport.incomingContext();if(c==null)return unbound(message,read);r=new LinkedHashMap(c.fields());r.put("uri",Transport.serverUri());Object response=invoke(message,"getServletResponse");role(r,"server-send-response",id(response));r.put("response_object",id(response));r.put("direction","response");
            }else return unbound(message,read);
            r.put("carrier_object",id(original));r.put("carrier_chain",wrappers);r.put("codec_adapter_object",id(message));r.put("codec_adapter_class",message.getClass().getName().replace('.','/'));r.put("codec_adapter_sha256",ExecutionKernelHooks.classHash(message.getClass()));return r;
        }
        static Map unbound(Object message,boolean read)throws Exception{Map r=new LinkedHashMap();W3CTraceContext parent=Transport.current();r.put("parent_message",parent==null?null:parent.message());r.put("communication_version",2);r.put("unbound",true);r.put("phase",read?"read":"write");r.put("carrier_object",id(message));r.put("carrier_class",message==null?null:message.getClass().getName());r.put("reason","No supported actual message/carrier relation; never inherit inbound identity as a codec message");return r;}
        static byte[] transform(final ClassLoader loader,String owner,byte[] bytes)throws Exception{
            if(!PlannedServiceAgent.Recorder.hash(bytes).equals(((Map)config().get("class_sha256")).get(owner)))throw new IllegalStateException("Communication implementation differs: "+owner);
            ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);boolean changed=false;
            for(MethodNode m:c.methods){AbstractInsnNode[] old=m.instructions.toArray();boolean sync=owner.equals(SYNC)&&m.name.equals("executeAndDecode"),network=(owner.equals(DEFAULT)||owner.equals("feign/okhttp/OkHttpClient"))&&m.name.equals("execute")&&m.desc.equals("(Lfeign/Request;Lfeign/Request$Options;)Lfeign/Response;");
                if(sync||network){int token=m.maxLocals++,error=m.maxLocals++;LabelNode begin=new LabelNode(),end=new LabelNode(),handler=new LabelNode();
                    if(network){InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,1));h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKESTATIC,H,"networkBegin","(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,token));h.add(begin);m.instructions.insert(h);}
                    for(AbstractInsnNode n:old){
                        if(sync&&n instanceof MethodInsnNode){MethodInsnNode call=(MethodInsnNode)n;
                            if(call.name.equals("targetRequest")&&call.owner.equals(SYNC)){int original=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ASTORE,original));h.add(new VarInsnNode(ALOAD,original));h.add(new MethodInsnNode(INVOKESTATIC,H,"begin","(Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,token));h.add(begin);h.add(new VarInsnNode(ALOAD,token));h.add(new VarInsnNode(ALOAD,original));h.add(new MethodInsnNode(INVOKESTATIC,H,"wireRequest","(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new TypeInsnNode(CHECKCAST,"feign/Request"));m.instructions.insert(n,h);}
                            if(call.owner.equals("feign/Client")&&call.name.equals("execute")){InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,token));h.add(new InsnNode(SWAP));h.add(new MethodInsnNode(INVOKESTATIC,H,"returned","(Ljava/lang/Object;Ljava/lang/Object;)V",false));m.instructions.insert(n,h);}
                        }
                        if(n.getOpcode()==ARETURN){InsnList h=new InsnList();if(network){h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,token));h.add(new InsnNode(SWAP));h.add(new InsnNode(ACONST_NULL));h.add(new MethodInsnNode(INVOKESTATIC,H,"networkEnd","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Throwable;)V",false));}else{h.add(new VarInsnNode(ALOAD,token));h.add(new InsnNode(ACONST_NULL));h.add(new MethodInsnNode(INVOKESTATIC,H,"finish","(Ljava/lang/Object;Ljava/lang/Throwable;)V",false));}m.instructions.insertBefore(n,h);}
                    }
                    m.instructions.add(end);m.instructions.add(handler);m.instructions.add(new VarInsnNode(ASTORE,error));m.instructions.add(new VarInsnNode(ALOAD,token));if(network)m.instructions.add(new InsnNode(ACONST_NULL));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new MethodInsnNode(INVOKESTATIC,H,network?"networkEnd":"finish",network?"(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Throwable;)V":"(Ljava/lang/Object;Ljava/lang/Throwable;)V",false));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(begin,end,handler,"java/lang/Throwable"));changed=true;
                }else for(AbstractInsnNode n:old)if(n.getOpcode()==ARETURN||n.getOpcode()==RETURN){String hook=null;InsnList h=new InsnList();
                    if((owner.equals(LB)||owner.equals("org/springframework/cloud/openfeign/loadbalancer/RetryableFeignBlockingLoadBalancerClient"))&&m.name.equals("buildRequest")&&m.desc.equals("(Lfeign/Request;Ljava/lang/String;)Lfeign/Request;")){hook="derivedRequest";h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,1));h.add(new InsnNode(SWAP));}
                    if(owner.equals("feign/Response")&&m.name.equals("toBuilder")){hook="builder";h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,0));h.add(new InsnNode(SWAP));}
                    if(owner.equals("feign/Response$Builder")&&m.name.equals("build")){hook="built";h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,0));h.add(new InsnNode(SWAP));}
                    if(owner.endsWith("$EmptyBodyCheckingHttpInputMessage")&&m.name.equals("<init>")){hook="serverInput";h.add(new VarInsnNode(ALOAD,0));h.add(new VarInsnNode(ALOAD,1));}
                    if(hook!=null){if(hook.equals("derivedRequest"))h.add(new LdcInsnNode(owner));h.add(new MethodInsnNode(INVOKESTATIC,H,hook,hook.equals("derivedRequest")?"(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/String;)V":"(Ljava/lang/Object;Ljava/lang/Object;)V",false));m.instructions.insertBefore(n,h);changed=true;}
                }
            }
            if(!changed)return null;MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};c.accept(w);Map fact=new LinkedHashMap();fact.put("class",owner);fact.put("class_sha256",PlannedServiceAgent.Recorder.hash(bytes));emit("communication-framework",fact);return w.toByteArray();
        }
    }
/** Actual zero-advice Spring dispatch facts; never a general proxy purity claim. */
public static final class DirectDispatchHooks implements Opcodes {
    static final String OWNER="org/springframework/aop/framework/CglibAopProxy$DynamicAdvisedInterceptor";
    static Map config(){return ExecutionKernelHooks.enabled()?(Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("direct_dispatch_contract"):null;}
    static byte[] transform(final ClassLoader loader,String owner,byte[] bytes)throws Exception{
        if(!owner.equals(OWNER)||config()==null)return null;
        if(!PlannedServiceAgent.Recorder.hash(bytes).equals(((Map)config().get("class_sha256")).get(owner)))throw new IllegalStateException("Direct dispatch implementation differs");
        ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);int count=0;
        for(MethodNode m:c.methods)if(m.name.equals("intercept")&&m.desc.equals("(Ljava/lang/Object;Ljava/lang/reflect/Method;[Ljava/lang/Object;Lorg/springframework/cglib/proxy/MethodProxy;)Ljava/lang/Object;")){
            for(AbstractInsnNode n:m.instructions.toArray())if(n instanceof MethodInsnNode){MethodInsnNode call=(MethodInsnNode)n;
                if(call.owner.equals("org/springframework/aop/framework/AdvisedSupport")&&call.name.equals("getInterceptorsAndDynamicInterceptionAdvice")&&call.desc.equals("(Ljava/lang/reflect/Method;Ljava/lang/Class;)Ljava/util/List;")){
                    // Exact pinned locals, actual chain from the original call.
                    // Leave the same list on the original operand stack.
                    int chain=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ASTORE,chain));
                    for(int slot:new int[]{1,2,8,7,chain,3})h.add(new VarInsnNode(ALOAD,slot));
                    h.add(new MethodInsnNode(INVOKESTATIC,"SpringTransportAgent$DirectDispatchHooks","observe","(Ljava/lang/Object;Ljava/lang/reflect/Method;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;[Ljava/lang/Object;)V",false));h.add(new VarInsnNode(ALOAD,chain));m.instructions.insert(n,h);count++;
                }
            }
        }
        if(count!=1)throw new IllegalStateException("Direct dispatch fast path shape differs");
        MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};c.accept(w);Map witnessed=PlannedServiceAgent.Recorder.row();witnessed.put("class",owner);witnessed.put("class_sha256",PlannedServiceAgent.Recorder.hash(bytes));PlannedServiceAgent.Recorder.emit("direct-dispatch-framework",witnessed);return w.toByteArray();
    }
    public static void observe(Object proxy,Method method,Object targetSource,Object target,Object chain,Object[] args)throws Exception{synchronized(PlannedServiceAgent.Recorder.class){
        if(config()==null||!MonitorSafety.allowed()||CollectionServiceHooks.CALLS.get().isEmpty())return;
        Map call=CollectionServiceHooks.CALLS.get().peek();String suffix="."+method.getName()+org.objectweb.asm.Type.getMethodDescriptor(method);
        Map diagnostic=PlannedServiceAgent.Recorder.row();diagnostic.put("call_id",call.get("call_id"));diagnostic.put("same_proxy",call.get("_receiver_ref")==proxy);diagnostic.put("same_method",((String)call.get("callee")).endsWith(suffix));diagnostic.put("target_source_type",targetSource==null?null:targetSource.getClass().getName());diagnostic.put("chain_type",chain==null?null:chain.getClass().getName());boolean admittedChain=chain!=null&&Arrays.asList("java.util.ArrayList","java.util.Collections$EmptyList").contains(chain.getClass().getName());diagnostic.put("chain_empty",admittedChain&&((List)chain).isEmpty());if(admittedChain){List names=new ArrayList();for(Object interceptor:(List)chain)names.add(interceptor==null?null:interceptor.getClass().getName());diagnostic.put("chain_types",names);}diagnostic.put("same_args_count",args.length==((Object[])call.get("_args_ref")).length);PlannedServiceAgent.Recorder.emit("direct-dispatch-check",diagnostic);
        if(call.get("_receiver_ref")!=proxy||!((String)call.get("callee")).endsWith(suffix))return;
        if(method.isVarArgs()||target==null||targetSource==null||!targetSource.getClass().getName().equals("org.springframework.aop.target.SingletonTargetSource")||chain==null||!Arrays.asList("java.util.ArrayList","java.util.Collections$EmptyList").contains(chain.getClass().getName()))return;
        List<String> transparent=new ArrayList<>();boolean empty=((List)chain).isEmpty();if(!empty){
            if(((List)chain).size()!=1||config().get("transparent_interceptors")==null){BeforeAdviceHooks.prepare(proxy,method,targetSource,target,chain,args,call);return;}Object advice=((List)chain).get(0);String name=advice.getClass().getName().replace('.','/');
            if(!((List)config().get("transparent_interceptors")).equals(Arrays.asList(name)))return;
            Field singleton=advice.getClass().getDeclaredField("INSTANCE");if(singleton.get(null)!=advice)return;transparent.add(name);
        }
        Field f=targetSource.getClass().getDeclaredField("target");f.setAccessible(true);if(f.get(targetSource)!=target)return;
        Object[] original=(Object[])call.get("_args_ref");if(args.length!=original.length)return;Class<?>[] parameterTypes=method.getParameterTypes();for(int i=0;i<args.length;i++)if(parameterTypes[i].isPrimitive()?args[i]==null||original[i]==null||args[i].getClass()!=original[i].getClass()||!args[i].equals(original[i]):args[i]!=original[i])return;
        Map pins=new TreeMap();for(Object raw:((Map)config().get("class_sha256")).keySet()){String name=(String)raw;pins.put(name,ExecutionKernelHooks.classHash(Class.forName(name.replace('/','.'),false,target.getClass().getClassLoader())));}
        if(!pins.equals(config().get("class_sha256")))throw new IllegalStateException("Direct dispatch framework class differs");
        Map r=PlannedServiceAgent.Recorder.row();r.put("call_id",call.get("call_id"));r.put("pc",call.get("pc"));r.put("callee",call.get("callee"));r.put("proxy",PlannedServiceAgent.Recorder.id(proxy));r.put("target",PlannedServiceAgent.Recorder.id(target));r.put("target_type",target.getClass().getName().replace('.','/'));r.put("target_sha256",ExecutionKernelHooks.classHash(target.getClass()));r.put("class_sha256",pins);r.put("empty_chain",empty);r.put("transparent_interceptors",transparent);r.put("static_target",true);
        List values=new ArrayList();for(Object arg:args)values.add(PlannedServiceAgent.Recorder.value(arg));r.put("args",values);PlannedServiceAgent.Recorder.emit("execution-direct-dispatch",r);
    }}
}

    public static void premain(String args,Instrumentation i)throws Exception{PlannedServiceAgent.premain(args,i);Transport.start();i.addTransformer(new SpringTransportAgent());}
    public byte[] transform(final ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes){
        try{JsonTreeObservationHooks.loaded(loader,owner,bytes);}catch(Throwable failure){MonitorSafety.fatal(failure);PlannedServiceAgent.Recorder.problem("json-tree-class:"+owner+":"+failure);}
        try{byte[] scoped=RequestScopeHooks.transform(loader,owner,bytes);if(scoped!=null)return scoped;}catch(Throwable failure){MonitorSafety.fatal(failure);PlannedServiceAgent.Recorder.problem("query-scope-transform:"+owner+":"+failure);return null;}
        byte[] base=transformBase(loader,owner,prior,domain,bytes);
        if(SourceLocalityInstrumentation.owns(owner))try{return SourceLocalityInstrumentation.transform(loader,owner,bytes,base==null?bytes:base);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("locality-transform:"+owner+":"+e);return base;}
        if(SqlResultLocalityHooks.owns(owner))try{return SqlResultLocalityInstrumentation.transform(loader,owner,bytes,base==null?bytes:base);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("sql-locality-transform:"+owner+":"+e);return base;}
        return base;
    }
    byte[] transformBase(final ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes){
        try{byte[] literal=CommonsValueHooks.transform(loader,owner,bytes);if(literal!=null)return literal;}catch(Throwable failure){MonitorSafety.fatal(failure);PlannedServiceAgent.Recorder.problem("commons-literal-transform:"+owner+":"+failure);return null;}
        try{byte[] before=BeforeAdviceHooks.transform(loader,owner,bytes);if(before!=null)return before;}catch(Throwable failure){MonitorSafety.fatal(failure);PlannedServiceAgent.Recorder.problem("before-dispatch-transform:"+owner+":"+failure);return null;}
        if(Communication.owns(owner)){
            try{return Communication.transform(loader,owner,bytes);}catch(Throwable failure){PlannedServiceAgent.Recorder.problem("communication-transform:"+owner+":"+failure);return null;}
        }
        if(DirectDispatchHooks.config()!=null&&owner.equals(DirectDispatchHooks.OWNER)){
            try{return DirectDispatchHooks.transform(loader,owner,bytes);}catch(Throwable failure){PlannedServiceAgent.Recorder.problem("direct-dispatch-transform:"+failure);return null;}
        }
        if(FeignEffectHooks.config()!=null&&FeignProtocolInstrumentation.owns(owner)){
            try{return FeignProtocolInstrumentation.transform(loader,owner,bytes);}catch(Throwable failure){PlannedServiceAgent.Recorder.problem("feign-transform:"+owner+":"+failure);return null;}
        }
        if(TemporalDateHooks.effects()!=null&&"document-3.6".equals(TemporalDateHooks.effects().get("codec_kind"))&&owner.equals("org/bson/codecs/DocumentCodec")){
            try{Map pins=(Map)TemporalDateHooks.effects().get("codec_class_sha256");if(!PlannedServiceAgent.Recorder.hash(bytes).equals(pins.get(owner)))throw new IllegalStateException("Document codec hash differs");ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);for(MethodNode m:c.methods)if(m.name.equals("encode")&&m.desc.equals("(Lorg/bson/BsonWriter;Lorg/bson/Document;Lorg/bson/codecs/EncoderContext;)V")){AbstractInsnNode[] old=m.instructions.toArray();int token=m.maxLocals++,error=m.maxLocals++;LabelNode begin=new LabelNode(),end=new LabelNode(),handler=new LabelNode();InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,0));h.add(new VarInsnNode(ALOAD,2));h.add(new MethodInsnNode(INVOKESTATIC,"DocumentDateHooks","begin","(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,token));h.add(begin);m.instructions.insert(h);for(AbstractInsnNode n:old)if(n.getOpcode()==RETURN){InsnList done=new InsnList();done.add(new VarInsnNode(ALOAD,token));done.add(new InsnNode(ACONST_NULL));done.add(new MethodInsnNode(INVOKESTATIC,"DocumentDateHooks","end","(Ljava/lang/Object;Ljava/lang/Throwable;)V",false));m.instructions.insertBefore(n,done);}m.instructions.add(end);m.instructions.add(handler);m.instructions.add(new VarInsnNode(ASTORE,error));m.instructions.add(new VarInsnNode(ALOAD,token));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new MethodInsnNode(INVOKESTATIC,"DocumentDateHooks","end","(Ljava/lang/Object;Ljava/lang/Throwable;)V",false));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(begin,end,handler,"java/lang/Throwable"));}MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};c.accept(w);return w.toByteArray();}catch(Throwable failure){PlannedServiceAgent.Recorder.problem("document-date-transform:"+failure);return null;}
        }
        if(TemporalDateHooks.effects()!=null&&!"document-3.6".equals(TemporalDateHooks.effects().get("codec_kind"))&&owner.equals("com/mongodb/CompoundDBObjectCodec")){
            try{Map pins=(Map)TemporalDateHooks.effects().get("codec_class_sha256");if(!PlannedServiceAgent.Recorder.hash(bytes).equals(pins.get(owner)))throw new IllegalStateException("Date encoder hash differs");ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);for(MethodNode m:c.methods)if(m.name.equals("encode")&&m.desc.contains("Lcom/mongodb/DBObject;")){InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKESTATIC,"SaveEffectHooks","codec","(Ljava/lang/Object;)V",false));m.instructions.insert(h);}MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};c.accept(w);return w.toByteArray();}catch(Throwable e){PlannedServiceAgent.Recorder.problem("date-codec-transform:"+e);return null;}
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
                if(changed){MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};c.accept(w);return w.toByteArray();}return null;
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
                int originalInput=-1;
                if(read){originalInput=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,2));h.add(new VarInsnNode(ASTORE,originalInput));h.add(new VarInsnNode(ALOAD,2));h.add(new MethodInsnNode(INVOKESTATIC,"SourceEvidenceHooks","input","(Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new TypeInsnNode(CHECKCAST,"org/springframework/http/HttpInputMessage"));h.add(new VarInsnNode(ASTORE,2));h.add(start);m.instructions.insert(h);}
                int rpcToken=-1;
                if(rpc){rpcToken=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,1));h.add(new VarInsnNode(ALOAD,2));h.add(new MethodInsnNode(INVOKESTATIC,R,"rpcEnter","(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,rpcToken));h.add(start);m.instructions.insert(h);}
                int token=-1;
                if(write){token=m.maxLocals++;InsnList h=new InsnList();if(FeignEffectHooks.config()!=null){h.add(new VarInsnNode(ALOAD,0));h.add(new VarInsnNode(ALOAD,1));h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKEVIRTUAL,owner,"getObjectMapper","()Lcom/fasterxml/jackson/databind/ObjectMapper;",false));h.add(new MethodInsnNode(INVOKESTATIC,"FeignEffectHooks","converter","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V",false));}h.add(new VarInsnNode(ALOAD,1));h.add(new VarInsnNode(ALOAD,typedWrite?3:2));h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKEVIRTUAL,owner,"getObjectMapper","()Lcom/fasterxml/jackson/databind/ObjectMapper;",false));h.add(new MethodInsnNode(INVOKESTATIC,R,"writeStartWithMapper","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,token));h.add(start);m.instructions.insert(h);}
                if(workerCall)for(AbstractInsnNode n:original)if(n instanceof MethodInsnNode){MethodInsnNode call=(MethodInsnNode)n;
                    String hook=call.owner.equals("org/aopalliance/intercept/MethodInvocation")&&call.name.equals("proceed")?"inner":call.owner.equals("java/util/concurrent/Future")&&call.name.equals("get")?"unwrapped":null;
                    if(hook!=null){InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new MethodInsnNode(INVOKESTATIC,"AsyncTaskHooks",hook,"(Ljava/lang/Object;)V",false));m.instructions.insert(n,h);}
                }
                for(AbstractInsnNode n:original)if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN){InsnList h=new InsnList();
                    if(async&&protocol){h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,1));h.add(new InsnNode(SWAP));h.add(new MethodInsnNode(INVOKESTATIC,"AsyncTaskHooks","submitted","(Ljava/util/concurrent/Callable;Ljava/lang/Object;)V",false));}
                    if(request){h.add(new InsnNode(DUP));h.add(new MethodInsnNode(INVOKESTATIC,R,"request","(Ljava/lang/Object;)V",false));}
                    if(read){h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,2));h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKEVIRTUAL,owner,"getObjectMapper","()Lcom/fasterxml/jackson/databind/ObjectMapper;",false));h.add(new MethodInsnNode(INVOKESTATIC,"SourceEvidenceHooks","read","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V",false));h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKEVIRTUAL,owner,"getObjectMapper","()Lcom/fasterxml/jackson/databind/ObjectMapper;",false));h.add(new VarInsnNode(ALOAD,1));h.add(new MethodInsnNode(INVOKESTATIC,R,"decoder","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V",false));h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,originalInput));h.add(new MethodInsnNode(INVOKESTATIC,R,"read","(Ljava/lang/Object;Ljava/lang/Object;)V",false));}
                    if(write){h.add(new VarInsnNode(ALOAD,token));h.add(new VarInsnNode(ALOAD,1));h.add(new MethodInsnNode(INVOKESTATIC,R,"writeEnd","(Ljava/lang/Object;Ljava/lang/Object;)V",false));}
                    if(rpc){h.add(new VarInsnNode(ALOAD,rpcToken));h.add(new MethodInsnNode(INVOKESTATIC,R,"rpcExit","(Ljava/lang/Object;)V",false));}m.instructions.insertBefore(n,h);
                }
                if(async&&protocol){m.instructions.add(end);m.instructions.add(handler);int error=m.maxLocals++;m.instructions.add(new VarInsnNode(ASTORE,error));m.instructions.add(new VarInsnNode(ALOAD,1));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new MethodInsnNode(INVOKESTATIC,"AsyncTaskHooks","rejected","(Ljava/util/concurrent/Callable;Ljava/lang/Throwable;)V",false));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));}
                if(rpc||write||read){m.instructions.add(end);m.instructions.add(handler);int error=m.maxLocals++;m.instructions.add(new VarInsnNode(ASTORE,error));if(rpc){m.instructions.add(new VarInsnNode(ALOAD,rpcToken));m.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"rpcAbort","(Ljava/lang/Object;)V",false));}else if(read){m.instructions.add(new VarInsnNode(ALOAD,2));m.instructions.add(new MethodInsnNode(INVOKESTATIC,"SourceEvidenceHooks","abort","(Ljava/lang/Object;)V",false));}else{m.instructions.add(new VarInsnNode(ALOAD,token));m.instructions.add(new MethodInsnNode(INVOKESTATIC,R,"writeAbort","(Ljava/lang/Object;)V",false));}m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));}changed=true;
            }
            if(!changed)throw new IllegalStateException("No supported framework methods: "+owner);
            MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};c.accept(w);Transport.instrumented(owner);return w.toByteArray();
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
            W3CTraceContext c=W3CTraceContext.server(parent,state);api(req,"javax.servlet.http.HttpServletRequest","setAttribute",new Class[]{String.class,Object.class},"tf.w3c.context",c);Map<String,Object> audit=c.fields();audit.put("wire_traceparent",parent);audit.put("wire_tracestate",state);audit.put("uri",serverUri());if(Communication.enabled()){Communication.role(audit,"server-receive-request",PlannedServiceAgent.Recorder.id(req));audit.put("request_object",PlannedServiceAgent.Recorder.id(req));}emit("http-server-context",audit);return c;
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
        public static Object rpcEnter(Object uri,Object method){return rpcEnterKind(uri,method,"rest-template");}
        static Object rpcEnterKind(Object uri,Object method,String kind){
            RpcScope token=new RpcScope();try{
                W3CTraceContext parent=current();W3CTraceContext c=W3CTraceContext.client(parent);Map<String,Object> r=c.fields();r.put("uri",String.valueOf(uri));r.put("method",String.valueOf(method));r.put("parent_message",parent==null?null:parent.message());if(Communication.enabled()){r.put("communication_version",2);synchronized(PlannedServiceAgent.Recorder.class){r.put("rpc_call_id","rpc-"+(++Communication.calls));}r.put("client_kind",kind);}token.own=r;SPANS.get().push(c);RPC.get().push(r);MonitorSafety.fault("rpc-enter","rpc");emit("http-rpc-enter",new LinkedHashMap<>(r));return token;
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
        static boolean primitive(Object o){return o==null||o instanceof String||o instanceof Number||o instanceof Boolean||ScalarProjectionHooks.enumeration(o)||TemporalDateHooks.date(o)||UuidProjectionHooks.uuid(o);}
        static final ThreadLocal<Boolean> TARGET_MAPS=new ThreadLocal<>();
        static List<Object> snapshot(Object root)throws Exception{return snapshot(root,false);}
        static List<Object> snapshot(Object root,boolean target)throws Exception{Boolean prior=TARGET_MAPS.get();TARGET_MAPS.set(target);try{List<Object> r=new ArrayList<>();walk(root,"",r,new IdentityHashMap<>(),0,null);return r;}finally{if(prior==null)TARGET_MAPS.remove();else TARGET_MAPS.set(prior);}}
        // Readonly output observation is independent of query certification.
        // Handler outputs have no binding-return but can use the same finite
        // wrapper representation. Request/source snapshots remain ineligible.
        static boolean outputSnapshotScope(Map context){return "response".equals(context.get("direction"))&&PlannedServiceAgent.plan.get("map_wrapper_observation")!=null;}
        static List<Object> conversionSnapshot(Object root)throws Exception{List<Object> r=new ArrayList<>();walk(root,"",r,new IdentityHashMap<>(),0,"@conversion");return r;}
        static String escape(String s){return s.replace("~","~0").replace("/","~1");}
        static void element(Object container,String field,Object value,String path,String anchor,List<Object> result){Map<String,Object> v=new LinkedHashMap<>();v.put("path",path);synchronized(PlannedServiceAgent.Recorder.class){v.put("owner",PlannedServiceAgent.Recorder.id(container));v.put("field",field);v.put("version",CollectionServiceHooks.epoch(container));v.put("observed",PlannedServiceAgent.Recorder.value(value));}v.put("descriptor","Ljava/lang/Object;");v.put("schema_field",anchor);result.add(v);}
        static void walk(Object o,String path,List<Object> result,IdentityHashMap<Object,Boolean> active,int depth,String anchor)throws Exception{
            if(o==null||primitive(o))return;if(depth>12||result.size()>10000)throw new IllegalStateException("JSON observation bound");if(active.put(o,true)!=null)throw new IllegalStateException("Cyclic JSON object");
            try{if(o instanceof Collection){if(Boolean.TRUE.equals(TARGET_MAPS.get())&&!Arrays.asList("java.util.ArrayList","java.util.Arrays$ArrayList","java.util.Collections$SingletonList","java.util.Collections$EmptyList").contains(o.getClass().getName()))throw new IllegalStateException("Unmodeled target collection");int i=0;for(Object item:(Collection<?>)o){String sub=path+"/"+i;if(Boolean.TRUE.equals(PlannedServiceAgent.plan.get("collection_elements"))&&o instanceof List&&anchor!=null&&primitive(item))element(o,"@list:"+i,item,sub,anchor,result);else walk(item,sub,result,active,depth+1,anchor);i++;}return;}
                if(o instanceof Map&&Boolean.TRUE.equals(PlannedServiceAgent.plan.get("collection_elements"))){List<Map> proofs=new ArrayList<>();ResponseBindingHooks.mapWrapper(o,Boolean.TRUE.equals(TARGET_MAPS.get()),proofs);List<Map.Entry> entries=new ArrayList<>();if(o.getClass()!=HashMap.class&&o.getClass()!=LinkedHashMap.class)entries=ResponseBindingHooks.wrapperEntries(o,proofs);else for(Object k:((Map)o).keySet()){if(!(k instanceof String))throw new IllegalStateException("Only String map keys admitted");entries.add(new AbstractMap.SimpleImmutableEntry(k,((Map)o).get(k)));}for(Map.Entry pair:entries){Object k=pair.getKey(),item=pair.getValue();String sub=path+"/"+escape((String)k);if(anchor!=null&&primitive(item))element(o,"@map:"+k,item,sub,anchor,result);else walk(item,sub,result,active,depth+1,anchor);}return;}
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
        public static Object writeStartWithMapper(Object body,Object message,Object mapper){try{if(RequestScopeHooks.config()!=null){Map context=Communication.enabled()?Communication.codec(message,false):context();if(RequestScopeHooks.exclude(context,message))return context;}BusinessJackson.observe(mapper);ResponseBindingHooks.verifySerialization(body,mapper);Object token=writeStart(body,message);if(token!=null&&RequestEntityHooks.config()!=null){Map r=(Map)token,policy=queryTransportPolicy(r);if(policy==null||!Boolean.TRUE.equals(policy.get("request_proofs_outbound_only")))r.put("request_serialization",RequestEntityHooks.serialization(body,mapper));}return token;}catch(Throwable e){PlannedServiceAgent.Recorder.problem("binding-serializer:"+e);return null;}}
        public static Object writeStart(Object body,Object message){try{Map<String,Object> r=Communication.enabled()?Communication.codec(message,false):context();if(r.get("message")==null&&!Boolean.TRUE.equals(r.get("unbound")))return null;r.put("fields",snapshot(body,outputSnapshotScope(r)));r.put("phase","write");return r;}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-write-start:"+e);return null;}}
        public static void writeEnd(Object token,Object body){if(token==null)return;try{Map<String,Object> r=(Map)token;if(r.containsKey("query_output_scope")){emit("query-scope-output-excluded-end",r);return;}if(!r.get("fields").equals(snapshot(body,outputSnapshotScope(r))))throw new IllegalStateException("DTO changed during serialization");Map policy=queryTransportPolicy(r);if(projectQueryFields(policy))r.put("fields",queryResponseFields((List)r.get("fields"),(String)policy.get("response_path")));emit(Boolean.TRUE.equals(r.get("unbound"))?"http-json-unbound":"http-json",r);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-write-end:"+e);}}
        public static void writeAbort(Object token){if(token!=null)emit(((Map)token).containsKey("query_output_scope")?"query-scope-output-excluded-abort":"http-json-abort",(Map)token);}
        static void received(Object o,IdentityHashMap<Object,Boolean> seen)throws Exception{if(o==null||primitive(o)||seen.put(o,true)!=null)return;if(o instanceof List){CollectionServiceHooks.received(o);for(Object v:(List)o)received(v,seen);}else if(o instanceof Map){ResponseBindingHooks.mapWrapper(o,false,new ArrayList<Map>());CollectionServiceHooks.received(o);for(Object v:((Map)o).values())received(v,seen);}else{List<Map<String,Object>> props=schema.get(o.getClass().getName().replace('.','/'));if(props!=null)for(Map p:props){String name=(String)p.get("field");Field f=o.getClass().getDeclaredField(name.substring(name.lastIndexOf('.')+1));f.setAccessible(true);received(f.get(o),seen);}}}
        static final ThreadLocal<Map> DECODER=new ThreadLocal<Map>();
        public static void decoder(Object body,Object mapper,Object type){synchronized(PlannedServiceAgent.Recorder.class){try{BusinessJackson.observe(mapper);Map r=new LinkedHashMap();RequestEntityHooks.decoded(body,mapper,type,r);DECODER.set(r);}catch(Throwable e){DECODER.remove();PlannedServiceAgent.Recorder.problem("request-decoder:"+e);}}}
        public static void read(Object body,Object message){try{Map<String,Object> r=new LinkedHashMap<>();if(Communication.enabled())r.putAll(Communication.codec(message,true));else if(!RPC.get().isEmpty()){r.putAll(RPC.get().peek());r.put("direction","response");}else{W3CTraceContext c=incomingContext();if(c==null)return;r.putAll(c.fields());r.put("direction","request");r.put("uri",serverUri());}if(r.get("message")==null&&!Boolean.TRUE.equals(r.get("unbound")))return;r.put("phase","read");Map decoder=DECODER.get();DECODER.remove();if(decoder!=null)r.putAll(decoder);if(FrameworkCallHooks.config()!=null||RequestEntityHooks.config()!=null){r.put("decoded_body",PlannedServiceAgent.Recorder.value(body));r.put("decoded_type",body==null?null:body.getClass().getName());}List<Object> projected=snapshot(body);if(decoder!=null&&decoder.get("resource_decoder")!=null){Map d=(Map)decoder.get("resource_decoder");if(Boolean.TRUE.equals(d.get("valid"))){projected=new ArrayList<>();for(Object raw:(List)d.get("fields")){Map field=(Map)raw;String path=(String)field.get("path");if(((List)d.get("source_properties")).contains(path.substring(1)))projected.add(raw);}}}r.put("fields",projected);if(Boolean.TRUE.equals(PlannedServiceAgent.plan.get("collection_elements")))received(body,new IdentityHashMap<>());emit(Boolean.TRUE.equals(r.get("unbound"))?"http-json-unbound":"http-json",r);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("json-read:"+e);}}
        public static void instrumented(String cls){Map<String,Object> r=new LinkedHashMap<>();r.put("class",cls);emit("http-framework",r);}
    }
}
