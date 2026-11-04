import java.lang.reflect.*;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Synchronous MVC ownership witnesses. Never invokes an application getter. */
public final class RequestScopeHooks implements Opcodes {
 static final String INVOKER="org/springframework/web/servlet/mvc/method/annotation/ServletInvocableHandlerMethod";
 static final String HANDLER="org/springframework/web/method/HandlerMethod", ATTR="org/springframework/web/context/request/ServletRequestAttributes";
 static final String ASYNC="org/springframework/web/context/request/async/StandardServletAsyncWebRequest";
 static final ThreadLocal<Deque<Scope>> ACTIVE=ThreadLocal.withInitial(ArrayDeque::new);
 static final Map<ClassLoader,Set<String>> CHECKED=Collections.synchronizedMap(new IdentityHashMap<>());
 static final Set<String> TARGET_HANDLERS=new HashSet<>();static final Set<String> ROOTS=new HashSet<>();static long serial;static boolean covered;
 static Map config(){return PlannedServiceAgent.plan==null?null:(Map)PlannedServiceAgent.plan.get("query_request_scope");}
 static Map pins(){return(Map)((Map)((List)((Map)config().get("framework")).get("profiles")).get(0)).get("class_sha256");}
 static void emit(String kind,Map row){PlannedServiceAgent.Recorder.emit(kind,row);}
 static String id(Object value){return PlannedServiceAgent.Recorder.id(value);}
 static void fail(String phase,Throwable error){MonitorSafety.fatal(error);PlannedServiceAgent.Recorder.problem("query-scope-"+phase+":"+error);}
 static Class<?> checked(Class<?> type,String expected)throws Exception{
  for(Class<?> c=type;c!=null;c=c.getSuperclass())if(c.getName().replace('.','/').equals(expected)){
   Set<String> group=CHECKED.get(c.getClassLoader());if(group==null||!group.contains(expected))throw new IllegalStateException("Unverified MVC class/loader: "+expected);return c;
  }throw new IllegalStateException("MVC class hierarchy differs");
 }
 static Object field(Object object,String owner,String name)throws Exception{Field f=checked(object.getClass(),owner).getDeclaredField(name);f.setAccessible(true);return f.get(object);}
 static class Scope {Deque<Scope> before;Map context;Object request,response,web;String handler,loader;long token;boolean closed,excluded;}
 static boolean synchronous(Scope s)throws Exception{if(s.web.getClass().getName().replace('.','/').equals(ASYNC)){
  Object state=field(s.web,ASYNC,"state");checked(state.getClass(),ASYNC+"$State");checked(s.response.getClass(),ASYNC+"$LifecycleHttpServletResponse");
  return field(s.web,ASYNC,"asyncContext")==null&&((Enum)state).name().equals("NEW");
 }return false;}
 static void coverage(String owner){if(config()==null||!owner.equals(config().get("entry_class")))return;
  if(!PlannedServiceAgent.frames.contains(config().get("entry")))throw new IllegalStateException("Query root entry is not instrumented");
  covered=true;Map r=new LinkedHashMap();r.put("entry",config().get("entry"));r.put("class",owner);r.put("class_sha256",PlannedServiceAgent.hashes.get(owner));emit("query-scope-coverage",r);
 }
 public static Object begin(Object handler,Object web){synchronized(PlannedServiceAgent.Recorder.class){Scope s=new Scope();s.before=new ArrayDeque<>(ACTIVE.get());try{
  if(!handler.getClass().getName().replace('.','/').equals(INVOKER)||!web.getClass().getName().equals(ASYNC.replace('/','.'))){s.closed=true;return s;}
  checked(handler.getClass(),INVOKER);checked(handler.getClass(),"org/springframework/web/method/support/InvocableHandlerMethod");checked(web.getClass(),"org/springframework/web/context/request/ServletWebRequest");
  Method method=(Method)field(handler,HANDLER,"method"),bridged=(Method)field(handler,HANDLER,"bridgedMethod");Object bean=field(handler,HANDLER,"bean");
  if(!method.equals(bridged)||bean instanceof String)throw new IllegalStateException("Unresolved/bridged MVC handler");
  s.web=web;s.request=field(web,ATTR,"request");s.response=field(web,ATTR,"response");
  if(s.request==null||s.response==null||s.request!=SpringTransportAgent.Transport.servlet())throw new IllegalStateException("MVC request context differs");
  W3CTraceContext c=SpringTransportAgent.Transport.incomingContext();if(c==null)throw new IllegalStateException("MVC message absent");s.context=new LinkedHashMap(c.fields());s.context.put("uri",SpringTransportAgent.Transport.serverUri());
  String declaring=method.getDeclaringClass().getName().replace('.','/');s.handler=declaring+"."+method.getName()+org.objectweb.asm.Type.getMethodDescriptor(method);
  if(!((Map)config().get("handlers")).containsKey(s.handler)||!PlannedServiceAgent.Recorder.CHECKED_CLASSES.contains(declaring)){s.closed=true;return s;}
  if(handler.getClass().getClassLoader()!=web.getClass().getClassLoader())throw new IllegalStateException("Split MVC framework loaders unsupported");s.loader=id(handler.getClass().getClassLoader());s.token=++serial;
  ACTIVE.get().push(s);if(s.handler.equals(config().get("entry")))TARGET_HANDLERS.add((String)s.context.get("message"));
  Map r=record(s);r.put("handler_object",id(handler));r.put("bean_object",id(bean));emit("query-scope-dispatch-enter",r);return s;
 }catch(Throwable e){s.closed=true;ACTIVE.get().clear();ACTIVE.get().addAll(s.before);fail("begin",e);return s;}}}
 static Map record(Scope s)throws Exception{Map r=new LinkedHashMap(s.context);r.put("dispatch_id",s.token);r.put("handler_method",s.handler);r.put("handler_class_sha256",((Map)config().get("handlers")).get(s.handler));r.put("framework_loader",s.loader);r.put("web_type",s.web.getClass().getName().replace('.','/'));r.put("synchronous",synchronous(s));r.put("request_object",id(s.request));r.put("response_object",id(s.response));return r;}
 public static void end(Object token,Throwable error){synchronized(PlannedServiceAgent.Recorder.class){if(!(token instanceof Scope))return;Scope s=(Scope)token;if(s.closed)return;s.closed=true;try{
  if(ACTIVE.get().peek()!=s)throw new IllegalStateException("MVC completion owner differs");if(s.excluded&&!synchronous(s))throw new IllegalStateException("Excluded response became asynchronous");Map r=record(s);r.put("exception_object",id(error));emit("query-scope-dispatch-exit",r);
 }catch(Throwable e){fail("end",e);}finally{ACTIVE.get().clear();ACTIVE.get().addAll(s.before);}}}
 static void root(String method,String frame)throws Exception{if(config()==null||!method.equals(config().get("entry")))return;
  W3CTraceContext c=SpringTransportAgent.Transport.incomingContext();if(c==null)throw new IllegalStateException("Query root has no servlet message");ROOTS.add(c.message());
  Map r=new LinkedHashMap(c.fields());r.put("entry",method);r.put("root_frame",frame);Scope s=ACTIVE.get().peek();r.put("dispatch_id",s==null?null:s.token);emit("query-scope-root",r);
 }
 static boolean exclude(Map context,Object carrier)throws Exception{if(config()==null||!"response".equals(context.get("direction")))return false;
  Scope s=ACTIVE.get().peek();if(s==null||s.closed||!covered||PlannedServiceAgent.Recorder.captureInvalid||!SpringTransportAgent.Transport.RPC.get().isEmpty())return false;
  if(!Objects.equals(s.context.get("message"),context.get("message")))throw new IllegalStateException("MVC output message differs");
  if(carrier==null||!carrier.getClass().getName().equals("org.springframework.http.server.ServletServerHttpResponse")||!id(carrier.getClass().getClassLoader()).equals(s.loader))return false;
  if(field(carrier,"org/springframework/http/server/ServletServerHttpResponse","servletResponse")!=s.response||SpringTransportAgent.Transport.servlet()!=s.request)throw new IllegalStateException("MVC output carrier differs");
  String message=(String)context.get("message");if(!synchronous(s)||s.context.get("parent_span_id")!=null||ROOTS.contains(message))return false;
  if(TARGET_HANDLERS.contains(message))return false;
  s.excluded=true;context.putAll(record(s));context.put("query_output_scope","independent-unparented-handler");context.put("carrier_object",id(carrier));emit("query-scope-output-excluded",new LinkedHashMap(context));return true;
 }
 static byte[] transform(ClassLoader loader,String owner,byte[] bytes)throws Exception{if(config()==null||!pins().containsKey(owner))return null;
  if(!PlannedServiceAgent.Recorder.hash(bytes).equals(pins().get(owner)))throw new IllegalStateException("MVC implementation hash differs: "+owner);
  synchronized(PlannedServiceAgent.Recorder.class){CHECKED.computeIfAbsent(loader,k->new HashSet<>()).add(owner);Map r=new LinkedHashMap();r.put("class",owner);r.put("class_sha256",pins().get(owner));r.put("loader",id(loader));emit("query-scope-framework",r);}
  if(!owner.equals(INVOKER))return null;ClassNode cls=new ClassNode(ASM9);new ClassReader(bytes).accept(cls,ClassReader.EXPAND_FRAMES);int found=0;
  for(MethodNode m:cls.methods)if((m.name+m.desc).equals(((Map)config().get("framework")).get("method"))){found++;
   AbstractInsnNode[] original=m.instructions.toArray();int token=m.maxLocals++,error=m.maxLocals++;LabelNode start=new LabelNode(),end=new LabelNode(),caught=new LabelNode();
   InsnList entry=new InsnList();entry.add(new VarInsnNode(ALOAD,0));entry.add(new VarInsnNode(ALOAD,1));entry.add(new MethodInsnNode(INVOKESTATIC,"RequestScopeHooks","begin","(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",false));entry.add(new VarInsnNode(ASTORE,token));entry.add(start);m.instructions.insert(entry);
   for(AbstractInsnNode n:original)if(n.getOpcode()==RETURN){InsnList done=new InsnList();done.add(new VarInsnNode(ALOAD,token));done.add(new InsnNode(ACONST_NULL));done.add(new MethodInsnNode(INVOKESTATIC,"RequestScopeHooks","end","(Ljava/lang/Object;Ljava/lang/Throwable;)V",false));m.instructions.insertBefore(n,done);}
   m.instructions.add(end);m.instructions.add(caught);m.instructions.add(new VarInsnNode(ASTORE,error));m.instructions.add(new VarInsnNode(ALOAD,token));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new MethodInsnNode(INVOKESTATIC,"RequestScopeHooks","end","(Ljava/lang/Object;Ljava/lang/Throwable;)V",false));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,caught,"java/lang/Throwable"));
  }if(found!=1)throw new IllegalStateException("MVC invokeAndHandle site differs");
  ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};cls.accept(w);return w.toByteArray();
 }
}
