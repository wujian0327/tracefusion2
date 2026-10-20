import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Additional concrete evidence only. No provenance or expected-source code. */
public final class ExecutionKernelHooks implements Opcodes {
    static final String R="ExecutionKernelHooks";
    static boolean runtimeEmitted;
    static final String[] PINNED={"java/util/ArrayList","java/util/ArrayList$Itr","java/util/Arrays$ArrayList","java/util/Iterator"};
    static boolean enabled(){return "execution-dependency".equals(PlannedServiceAgent.plan.get("profile"));}
    static boolean method(String key){return enabled()&&(((Map)PlannedServiceAgent.plan.get("execution_kernel")).containsKey("methods")?((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("methods")).containsKey(key):key.equals(PlannedServiceAgent.plan.get("entry")));}
    static boolean instrument(MethodNode method,String key,List<AbstractInsnNode> code){
        if(!method(key))return false;
        boolean changed=false;
        for(int pc=0;pc<code.size();pc++){
            AbstractInsnNode n=code.get(pc);if(!(n instanceof MethodInsnNode))continue;
            MethodInsnNode call=(MethodInsnNode)n;if(!call.name.equals("<init>"))continue;
            Type[] types=Type.getArgumentTypes(call.desc);int[] slots=new int[types.length];InsnList before=new InsnList(),after=new InsnList();
            for(int j=types.length-1;j>=0;j--){slots[j]=method.maxLocals;method.maxLocals+=types[j].getSize();before.add(new VarInsnNode(types[j].getOpcode(ISTORE),slots[j]));}
            int receiver=method.maxLocals++;before.add(new VarInsnNode(ASTORE,receiver));before.add(new VarInsnNode(ALOAD,receiver));
            for(int j=0;j<types.length;j++)before.add(new VarInsnNode(types[j].getOpcode(ILOAD),slots[j]));
            // Uninitialized receiver is never passed to a hook. JVM initializes
            // its local alias only after successful original invokespecial.
            after.add(new LdcInsnNode(key));after.add(new LdcInsnNode(pc));after.add(new VarInsnNode(ALOAD,receiver));after.add(new LdcInsnNode(types.length));after.add(new TypeInsnNode(ANEWARRAY,"java/lang/Object"));
            for(int j=0;j<types.length;j++){after.add(new InsnNode(DUP));after.add(new LdcInsnNode(j));after.add(new VarInsnNode(types[j].getOpcode(ILOAD),slots[j]));PlannedServiceAgent.box(after,types[j]);after.add(new InsnNode(AASTORE));}
            after.add(new MethodInsnNode(INVOKESTATIC,R,"constructedAt","(Ljava/lang/String;ILjava/lang/Object;[Ljava/lang/Object;)V",false));
            method.instructions.insertBefore(n,before);method.instructions.insert(n,after);changed=true;
        }return changed;
    }
    static Map<String,Object> runtime()throws Exception{
        Map<String,Object> r=new LinkedHashMap<>();r.put("java_runtime_version",System.getProperty("java.runtime.version"));Map<String,String> hashes=new TreeMap<>();
        for(String name:PINNED)hashes.put(name,JdkContractProbe.hash(name));r.put("class_sha256",hashes);return r;
    }
    static void enter()throws Exception{if(!runtimeEmitted){PlannedServiceAgent.Recorder.emit("execution-runtime",runtime());runtimeEmitted=true;}}
    public static void constructed(int pc,Object receiver,Object[] args){synchronized(PlannedServiceAgent.Recorder.class){try{
        enter();
        Map<String,Object> r=PlannedServiceAgent.Recorder.row();r.put("pc",pc);r.put("receiver",PlannedServiceAgent.Recorder.value(receiver));r.put("receiver_type",receiver.getClass().getName());
        List<Object> values=new ArrayList<>();for(Object a:args)values.add(PlannedServiceAgent.Recorder.value(a));r.put("args",values);PlannedServiceAgent.Recorder.emit("execution-constructed",r);
    }catch(Throwable e){PlannedServiceAgent.Recorder.problem("execution-constructor:"+e);throw new IllegalStateException(e);}}}
    public static void constructedAt(String method,int pc,Object receiver,Object[] args){constructed(pc,receiver,args);}
    static void exceptional(String call,Throwable error){
        Deque<Map<String,Object>> pending=CollectionServiceHooks.CALLS.get();if(pending.isEmpty())return;
        Map<String,Object> top=pending.peek(),current=PlannedServiceAgent.Recorder.row();
        if(Objects.equals(top.get("frame"),current.get("frame"))&&Objects.equals(top.get("callee"),call)){
            pending.pop();current.put("pc",top.get("pc"));current.put("call_id",top.get("call_id"));current.put("exception_type",error.getClass().getName());current.put("exception",PlannedServiceAgent.Recorder.value(error));PlannedServiceAgent.Recorder.emit("collection-call-throw",current);
        }
    }
    public static void main(String[] args)throws Exception{System.out.println(new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(runtime()));}
}
