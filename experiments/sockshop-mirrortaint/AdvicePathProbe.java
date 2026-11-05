import java.lang.instrument.*;
import java.security.ProtectionDomain;
import java.lang.reflect.*;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
/** Separate diagnostic: original match result and original advice execution only. */
public class AdvicePathProbe implements Opcodes {
 static final String SELF="AdvicePathProbe";
 static final Set<String> OWNERS=new HashSet<>(Arrays.asList("org/springframework/aop/framework/ReflectiveMethodInvocation","org/springframework/aop/framework/adapter/MethodBeforeAdviceInterceptor","org/springframework/aop/aspectj/AspectJMethodBeforeAdvice"));
 public static void event(Object receiver,String stage){try{
  synchronized(PlannedServiceAgent.Recorder.class){Map row=PlannedServiceAgent.Recorder.row();row.put("stage",stage);row.put("invocation_object",PlannedServiceAgent.Recorder.id(receiver));row.put("runtime_class",receiver.getClass().getName());
   if(!CollectionServiceHooks.CALLS.get().isEmpty())row.put("call_id",CollectionServiceHooks.CALLS.get().peek().get("call_id"));
   for(Class<?> c=receiver.getClass();c!=null&&c.getName().startsWith("org.springframework.");c=c.getSuperclass())for(Field f:c.getDeclaredFields())if(f.getName().equals("aspectJAdviceMethod")){f.setAccessible(true);Method m=(Method)f.get(receiver);row.put("advice_method",m.getDeclaringClass().getName()+"."+m.getName()+org.objectweb.asm.Type.getMethodDescriptor(m));}
   PlannedServiceAgent.Recorder.emit("advice-path-diagnostic",row);
  }
 }catch(Throwable failure){MonitorSafety.fatal(failure);PlannedServiceAgent.Recorder.problem("advice-probe:"+failure.getClass().getName());}}
 public static void match(boolean result,Object receiver,String stage){event(receiver,stage+":"+result);}
 public static void premain(String args,Instrumentation instrumentation){instrumentation.addTransformer(new ClassFileTransformer(){
  public byte[] transform(final ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes){
   if(!OWNERS.contains(owner))return null;
   try{ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,0);
    for(MethodNode m:c.methods){boolean watched=owner.endsWith("MethodBeforeAdviceInterceptor")&&m.name.equals("invoke")||owner.endsWith("AspectJMethodBeforeAdvice")&&m.name.equals("before")||owner.endsWith("ReflectiveMethodInvocation")&&m.name.equals("invokeJoinpoint");
     AbstractInsnNode[] original=m.instructions.toArray();
     if(watched){InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,0));h.add(new LdcInsnNode(owner+"."+m.name+":enter"));h.add(new MethodInsnNode(INVOKESTATIC,SELF,"event","(Ljava/lang/Object;Ljava/lang/String;)V",false));m.instructions.insert(h);}
     for(AbstractInsnNode n:original){if(watched&&(n.getOpcode()==ARETURN||n.getOpcode()==RETURN)){InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,0));h.add(new LdcInsnNode(owner+"."+m.name+":return"));h.add(new MethodInsnNode(INVOKESTATIC,SELF,"event","(Ljava/lang/Object;Ljava/lang/String;)V",false));m.instructions.insertBefore(n,h);}
      if(owner.endsWith("ReflectiveMethodInvocation")&&m.name.equals("proceed")&&n instanceof MethodInsnNode){MethodInsnNode call=(MethodInsnNode)n;if(call.owner.equals("org/springframework/aop/MethodMatcher")&&call.name.equals("matches")&&call.desc.endsWith(")Z")){InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new VarInsnNode(ALOAD,0));h.add(new LdcInsnNode("dynamic-match"));h.add(new MethodInsnNode(INVOKESTATIC,SELF,"match","(ZLjava/lang/Object;Ljava/lang/String;)V",false));m.instructions.insert(n,h);}}
     }
    }ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS);c.accept(w);return w.toByteArray();
   }catch(Throwable e){MonitorSafety.fatal(e);PlannedServiceAgent.Recorder.problem("advice-probe-transform:"+owner+":"+e.getClass().getName());return null;}
  }
 });}
}
