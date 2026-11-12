import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
/** Observation-only invocations. Never an interpreted application Frame. */
public final class SourceObservationHooks implements Opcodes {
 static final String H="SourceObservationHooks";static long frames,calls;
 static final ThreadLocal<Deque<Context>> CONTEXTS=ThreadLocal.withInitial(ArrayDeque::new);
 static final ThreadLocal<Deque<Call>> CALLS=ThreadLocal.withInitial(ArrayDeque::new);
 static class Context {String id,method,parent;boolean closed;int before;}
 static class Call {String id,callee,site;Context context;boolean closed;Object receiver;Object[] args;}
 static Map config(){return (Map)PlannedServiceAgent.plan.get("source_observation");}
 static Map row(Context c){Map r=PlannedServiceAgent.Recorder.row();r.put("observation_frame",c.id);r.put("caller_method",c.method);r.put("observation_only",true);return r;}
 static void emit(String kind,Map r){PlannedServiceAgent.Recorder.emit(kind,r);}
 public static Object context(String method){synchronized(PlannedServiceAgent.Recorder.class){
  if(PlannedServiceAgent.Recorder.STACK.get().isEmpty())return null;
  Context c=new Context();c.id="sf"+(++frames);c.method=method;c.before=CALLS.get().size();c.parent=CONTEXTS.get().isEmpty()?null:CONTEXTS.get().peek().id;
  CONTEXTS.get().push(c);MonitorSafety.onClose(()->abandon(c));Map r=row(c);r.put("parent_observation_frame",c.parent);r.put("caller_class_sha256",PlannedServiceAgent.hashes.get(method.substring(0,method.indexOf('.'))));emit("source-context-enter",r);return c;
 }}
 static void abandon(Context c){if(c.closed)return;c.closed=true;while(!CALLS.get().isEmpty()&&CALLS.get().peek().context==c)CALLS.get().pop();CONTEXTS.get().remove(c);}
 public static void endContext(Object token,Throwable error){synchronized(PlannedServiceAgent.Recorder.class){if(!(token instanceof Context))return;Context c=(Context)token;if(c.closed)return;
  if(CALLS.get().size()!=c.before){PlannedServiceAgent.Recorder.problem("Unclosed observation-only source invocation");abandon(c);return;}
  Map r=row(c);r.put("exception",PlannedServiceAgent.Recorder.id(error));emit("source-context-exit",r);abandon(c);
 }}
 public static Object begin(String site,String callee,Object receiver,Object[] args){synchronized(PlannedServiceAgent.Recorder.class){if(CONTEXTS.get().isEmpty())return null;Context c=CONTEXTS.get().peek();Map proof=(Map)((Map)config().get("sites")).get(site);
  if(proof==null||!c.method.equals(proof.get("caller"))||!callee.equals(proof.get("callee")))throw new IllegalStateException("Source observation site/context differs");
  Call v=new Call();v.id="sc"+(++calls);v.callee=callee;v.site=site;v.context=c;v.receiver=receiver;v.args=args;CALLS.get().push(v);
  Map r=row(c);r.put("source_call_id",v.id);r.put("callee",callee);r.put("site",site);r.put("pc",proof.get("pc"));r.put("receiver",PlannedServiceAgent.Recorder.id(receiver));r.put("receiver_class",receiver==null?null:receiver.getClass().getName());String descriptor=PlannedServiceAgent.Recorder.methodDescriptor(callee);r.put("method_descriptor",descriptor);r.put("args",PlannedServiceAgent.Recorder.methodArguments(args,descriptor));emit("source-call-enter",r);return v;
 }}
 public static void complete(Object token,Object result,Throwable error){synchronized(PlannedServiceAgent.Recorder.class){if(!(token instanceof Call))return;Call c=(Call)token;if(c.closed)return;if(CALLS.get().peek()!=c)throw new IllegalStateException("Source observation completion order differs");
  Map r=row(c.context);r.put("source_call_id",c.id);r.put("callee",c.callee);r.put("site",c.site);r.put("method_descriptor",PlannedServiceAgent.Recorder.methodDescriptor(c.callee));if(error==null)r.put("result",PlannedServiceAgent.Recorder.methodResult(result,PlannedServiceAgent.Recorder.methodDescriptor(c.callee)));r.put("exception",PlannedServiceAgent.Recorder.id(error));emit(error==null?"source-call-exit":"source-call-throw",r);c.closed=true;CALLS.get().pop();
 }}
 static boolean bind(Map r,String site,String callee){Call c=CALLS.get().peek();if(c==null||!c.site.equals(site)||!c.callee.equals(callee))return false;
  r.put("source_call_id",c.id);r.put("source_caller_method",c.context.method);r.put("source_pc",Integer.parseInt(site.substring(site.lastIndexOf('@')+1)));r.put("source_observation_frame",c.context.id);r.put("source_scope","observation-only-call");return true;
 }
 static boolean instrument(MethodNode m,String key,List<AbstractInsnNode> code){
  Map cfg=config();if(cfg==null||!((List)cfg.get("methods")).contains(key))return false;
  if(m.name.startsWith("<"))throw new IllegalStateException("Observation-only constructor unsupported");
  int context=m.maxLocals++;InsnList entry=new InsnList();entry.add(new LdcInsnNode(key));entry.add(new MethodInsnNode(INVOKESTATIC,H,"context","(Ljava/lang/String;)Ljava/lang/Object;",false));entry.add(new VarInsnNode(ASTORE,context));LabelNode bodyStart=new LabelNode();entry.add(bodyStart);m.instructions.insert(entry);
  for(AbstractInsnNode n:code){if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN){InsnList done=new InsnList();done.add(new VarInsnNode(ALOAD,context));done.add(new InsnNode(ACONST_NULL));done.add(new MethodInsnNode(INVOKESTATIC,H,"endContext","(Ljava/lang/Object;Ljava/lang/Throwable;)V",false));m.instructions.insertBefore(n,done);}
   if(!(n instanceof MethodInsnNode))continue;MethodInsnNode call=(MethodInsnNode)n;String site=key+"@"+code.indexOf(n);if(!((Map)cfg.get("sites")).containsKey(site))continue;
   Type[] ts=Type.getArgumentTypes(call.desc);Type ret=Type.getReturnType(call.desc);int[] slots=new int[ts.length];InsnList before=new InsnList(),after=new InsnList();
   for(int j=ts.length-1;j>=0;j--){slots[j]=m.maxLocals;m.maxLocals+=ts[j].getSize();before.add(new VarInsnNode(ts[j].getOpcode(ISTORE),slots[j]));}
   int recv=-1;if(call.getOpcode()!=INVOKESTATIC){recv=m.maxLocals++;before.add(new VarInsnNode(ASTORE,recv));}
   before.add(new LdcInsnNode(site));ResponseBindingHooks.arguments(before,call.owner+"."+call.name+call.desc,recv,ts,slots);before.add(new MethodInsnNode(INVOKESTATIC,H,"begin","(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;",false));int token=m.maxLocals++;before.add(new VarInsnNode(ASTORE,token));
   if(recv>=0)before.add(new VarInsnNode(ALOAD,recv));for(int j=0;j<ts.length;j++)before.add(new VarInsnNode(ts[j].getOpcode(ILOAD),slots[j]));
   LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode(),done=new LabelNode();before.add(start);after.add(end);int result=m.maxLocals;m.maxLocals+=Math.max(1,ret.getSize());if(ret.getSort()!=Type.VOID)after.add(new VarInsnNode(ret.getOpcode(ISTORE),result));after.add(new VarInsnNode(ALOAD,token));
   if(ret.getSort()==Type.VOID)after.add(new InsnNode(ACONST_NULL));else{after.add(new VarInsnNode(ret.getOpcode(ILOAD),result));PlannedServiceAgent.box(after,ret);}after.add(new InsnNode(ACONST_NULL));after.add(new MethodInsnNode(INVOKESTATIC,H,"complete","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Throwable;)V",false));if(ret.getSort()!=Type.VOID)after.add(new VarInsnNode(ret.getOpcode(ILOAD),result));after.add(new JumpInsnNode(GOTO,done));after.add(handler);int err=m.maxLocals++;after.add(new VarInsnNode(ASTORE,err));after.add(new VarInsnNode(ALOAD,token));after.add(new InsnNode(ACONST_NULL));after.add(new VarInsnNode(ALOAD,err));after.add(new MethodInsnNode(INVOKESTATIC,H,"complete","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Throwable;)V",false));after.add(new VarInsnNode(ALOAD,err));after.add(new InsnNode(ATHROW));after.add(done);m.tryCatchBlocks.add(0,new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));m.instructions.insertBefore(n,before);m.instructions.insert(n,after);
  }
  LabelNode bodyEnd=new LabelNode(),handler=new LabelNode();m.instructions.add(bodyEnd);m.instructions.add(handler);int error=m.maxLocals++;m.instructions.add(new VarInsnNode(ASTORE,error));m.instructions.add(new VarInsnNode(ALOAD,context));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new MethodInsnNode(INVOKESTATIC,H,"endContext","(Ljava/lang/Object;Ljava/lang/Throwable;)V",false));m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(bodyStart,bodyEnd,handler,"java/lang/Throwable"));return true;
 }
}
