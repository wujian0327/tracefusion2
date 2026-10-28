import java.util.*;
import java.nio.file.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Monitor-only invocation scopes. Never runs/catches a business invocation. */
public final class MonitorSafety implements Opcodes {
    static final ThreadLocal<Deque<Scope>> SCOPES=ThreadLocal.withInitial(ArrayDeque::new);
    static final class Slot {
        final ThreadLocal local;final Object original,copy;
        Slot(ThreadLocal x){local=x;original=x.get();copy=copy(original);}
        static Object copy(Object o){if(o instanceof Deque)return new ArrayDeque((Deque)o);if(o instanceof Map)return o instanceof IdentityHashMap?new IdentityHashMap((Map)o):new LinkedHashMap((Map)o);if(o instanceof long[])return ((long[])o).clone();return o;}
        void restore(){if(original instanceof Deque){Deque d=(Deque)original;d.clear();d.addAll((Deque)copy);local.set(original);}else if(original instanceof Map){Map m=(Map)original;m.clear();m.putAll((Map)copy);local.set(original);}else if(original instanceof long[]){System.arraycopy(copy,0,original,0,((long[])original).length);local.set(original);}else if(original==null)local.remove();else local.set(original);}
    }
    static final class Checkpoint {
        final List<Slot> slots=new ArrayList<>();
        Checkpoint(){
            add(PlannedServiceAgent.Recorder.STACK);add(PlannedServiceAgent.Recorder.PENDING);
            add(CollectionServiceHooks.CALLS);add(ReadEffectHooks.STACK);add(ReadEffectHooks.STREAMS);add(ReadEffectHooks.OPTIONALS);add(ReadEffectHooks.COUNTS);
            add(ExecutionKernelHooks.CONSTRUCTORS);add(SaveEffectHooks.ACTIVE);add(ConversionContractHooks.ACTIVE);add(AsyncTaskHooks.ACTIVE);
            add(SpringTransportAgent.Transport.RPC);add(SpringTransportAgent.Transport.SPANS);add(SpringTransportAgent.Transport.ASYNC);add(SpringTransportAgent.Transport.DECODER);
        }
        void add(ThreadLocal x){slots.add(new Slot(x));}
        void restore(){for(Slot s:slots)try{s.restore();}catch(Throwable e){failureMarker("state-restore",e);}}
    }
    static final class Scope {
        final String method;final Checkpoint before;final Set<String> returnMessages=new HashSet<>();
        PlannedServiceAgent.Recorder.Frame frame;boolean failed,closed;
        Scope(String key){method=key;before=new Checkpoint();failed=!allowed();}
        void rollback(){
            if(frame!=null){for(Iterator<Map.Entry<String,Set<String>>> i=PlannedServiceAgent.Recorder.ACTIVE.entrySet().iterator();i.hasNext();){Set<String> users=i.next().getValue();users.remove(frame.id);if(users.isEmpty())i.remove();}}
            for(String msg:returnMessages)ResponseBindingHooks.RETURN_MESSAGES.remove(msg);returnMessages.clear();before.restore();
        }
        void fail(String site,Throwable error){failed=true;failureMarker(site,error);rollback();}
        void close(){if(closed)return;closed=true;try{fault("cleanup",method);}catch(Throwable e){fatal(e);failed=true;failureMarker("cleanup",e);}finally{
            if(frame!=null){for(Iterator<Map.Entry<String,Set<String>>> i=PlannedServiceAgent.Recorder.ACTIVE.entrySet().iterator();i.hasNext();){Set<String> users=i.next().getValue();users.remove(frame.id);if(users.isEmpty())i.remove();}}
            if(failed){for(String m:returnMessages)ResponseBindingHooks.RETURN_MESSAGES.remove(m);}
            before.restore();if(frame!=null)PlannedServiceAgent.Recorder.PENDING.remove();Deque<Scope> stack=SCOPES.get();if(stack.peek()==this)stack.pop();else{failureMarker("scope-completion-order",new IllegalStateException("Wrong monitor scope"));stack.remove(this);}
        }}
    }
    static Scope open(String method){Scope s=new Scope(method);SCOPES.get().push(s);return s;}
    public static boolean allowed(){return SCOPES.get().isEmpty()||!SCOPES.get().peek().failed;}
    static void rememberReturn(String message){if(message!=null&&!SCOPES.get().isEmpty()&&!ResponseBindingHooks.RETURN_MESSAGES.contains(message))SCOPES.get().peek().returnMessages.add(message);}
    static void fatal(Throwable t){if(t instanceof ThreadDeath)throw(ThreadDeath)t;if(t instanceof VirtualMachineError)throw(VirtualMachineError)t;}
    public static void failed(String site,Throwable error){synchronized(PlannedServiceAgent.Recorder.class){fatal(error);Scope s=SCOPES.get().peek();if(s==null)failureMarker(site,error);else s.fail(site,error);}}
    static void failureMarker(String site,Throwable error){try{PlannedServiceAgent.Recorder.problem("monitor-failure:"+site+":"+error.getClass().getName());}catch(Throwable ignored){PlannedServiceAgent.Recorder.captureInvalid=true;}}
    static void fault(String point,String method){if(!Boolean.getBoolean("service.monitor.test.enabled"))return;String key=System.getProperty("service.monitor.test.fault"),filter=System.getProperty("service.monitor.test.method","");if(point.equals(key)&&method.contains(filter)){System.clearProperty("service.monitor.test.fault");throw new IllegalStateException("Injected monitor "+point);}}
    public static Map inspect(){synchronized(PlannedServiceAgent.Recorder.class){Map m=new LinkedHashMap();m.put("frames",PlannedServiceAgent.Recorder.STACK.get().size());m.put("scopes",SCOPES.get().size());m.put("calls",CollectionServiceHooks.CALLS.get().size());m.put("effects",ReadEffectHooks.STACK.get().size());m.put("constructors",ExecutionKernelHooks.CONSTRUCTORS.get().size());m.put("save",SaveEffectHooks.ACTIVE.get().size());m.put("conversions",ConversionContractHooks.ACTIVE.get().size());m.put("pending",PlannedServiceAgent.Recorder.PENDING.get());int active=0;for(Set<String>s:PlannedServiceAgent.Recorder.ACTIVE.values())active+=s.size();m.put("active",active);return m;}}
    // Only monitor-owned static calls injected by our transformers are wrapped.
    // The original business invocation (including its Throwable) stays outside.
    static final Set<String> OWNERS=new HashSet<>(Arrays.asList("PlannedServiceAgent$Recorder","CollectionServiceHooks","ExecutionKernelHooks","ResponseBindingHooks","ReadEffectHooks","ConversionContractHooks","SaveEffectHooks","TemporalDateHooks","UuidProjectionHooks","AsyncTaskHooks","FrameworkCallHooks","RequestEntityHooks","SourceEvidenceHooks","SpringTransportAgent$Transport"));
    static void instrument(ClassNode owner){
        Map<String,String> wrappers=new LinkedHashMap<>();List<MethodNode> generated=new ArrayList<>();
        for(MethodNode method:new ArrayList<MethodNode>(owner.methods))for(AbstractInsnNode node:method.instructions.toArray()){
            if(!(node instanceof MethodInsnNode))continue;MethodInsnNode call=(MethodInsnNode)node;if(call.getOpcode()!=INVOKESTATIC||!OWNERS.contains(call.owner))continue;
            String site=call.owner+"."+call.name+call.desc,name=wrappers.get(site);
            if(name==null){name="$tf2$monitor$"+wrappers.size();while(has(owner,name))name+="$";wrappers.put(site,name);MethodNode guard=wrapper(name,call);if((owner.access&ACC_INTERFACE)!=0)guard.access=(guard.access&~ACC_PRIVATE)|ACC_PUBLIC;generated.add(guard);}
            call.owner=owner.name;call.name=name;call.itf=(owner.access&ACC_INTERFACE)!=0;
        }owner.methods.addAll(generated);
    }
    static boolean has(ClassNode c,String name){for(MethodNode m:c.methods)if(m.name.equals(name))return true;return false;}
    static MethodNode wrapper(String name,MethodInsnNode original){
        MethodNode m=new MethodNode(ASM9,ACC_PRIVATE|ACC_STATIC|ACC_SYNTHETIC,name,original.desc,null,null);Type[] args=Type.getArgumentTypes(original.desc);Type ret=Type.getReturnType(original.desc);int slots=0;for(Type t:args)slots+=t.getSize();m.maxLocals=slots+1;
        LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode(),fallback=new LabelNode();InsnList x=m.instructions;x.add(start);
        boolean lifecycle=original.owner.equals("PlannedServiceAgent$Recorder")&&Arrays.asList("enter","exit","abort").contains(original.name)||original.owner.equals("SpringTransportAgent$Transport")&&Arrays.asList("rpcExit","rpcAbort").contains(original.name)||original.owner.equals("SourceEvidenceHooks")&&Arrays.asList("read","abort").contains(original.name);
        if(!lifecycle){x.add(new MethodInsnNode(INVOKESTATIC,"MonitorSafety","allowed","()Z",false));x.add(new JumpInsnNode(IFEQ,fallback));}
        int slot=0;for(Type t:args){x.add(new VarInsnNode(t.getOpcode(ILOAD),slot));slot+=t.getSize();}
        x.add(new MethodInsnNode(INVOKESTATIC,original.owner,original.name,original.desc,false));x.add(end);x.add(new InsnNode(ret.getOpcode(IRETURN)));x.add(handler);x.add(new VarInsnNode(ASTORE,slots));x.add(new LdcInsnNode(original.owner+"."+original.name));x.add(new VarInsnNode(ALOAD,slots));x.add(new MethodInsnNode(INVOKESTATIC,"MonitorSafety","failed","(Ljava/lang/String;Ljava/lang/Throwable;)V",false));x.add(fallback);
        // Identity fallback ONLY for explicitly wrapping an application argument.
        boolean identity=original.owner.equals("SourceEvidenceHooks")&&original.name.equals("input")||original.owner.equals("SpringTransportAgent$Transport")&&original.name.equals("wrap");
        if(identity)x.add(new VarInsnNode(ALOAD,0));else if(ret.getSort()==Type.OBJECT||ret.getSort()==Type.ARRAY)x.add(new InsnNode(ACONST_NULL));else if(ret.getSort()!=Type.VOID)x.add(new InsnNode(ret.getSort()==Type.LONG?LCONST_0:ret.getSort()==Type.DOUBLE?DCONST_0:ret.getSort()==Type.FLOAT?FCONST_0:ICONST_0));
        x.add(new InsnNode(ret.getOpcode(IRETURN)));m.tryCatchBlocks.add(new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));return m;
    }
}
