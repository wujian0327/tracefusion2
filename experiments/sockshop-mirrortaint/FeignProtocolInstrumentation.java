import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
/** Hooks actual command/worker/join/encoder/serializer boundaries, not business bodies. */
public final class FeignProtocolInstrumentation implements Opcodes {
 static final String H="FeignEffectHooks";
 static boolean owns(String c){return Arrays.asList("feign/hystrix/HystrixInvocationHandler$1","com/netflix/hystrix/HystrixCommand","org/springframework/cloud/openfeign/support/SpringEncoder","com/fasterxml/jackson/databind/ser/std/BeanSerializerBase").contains(c);}
 static void hook(InsnList out,String name,String desc){out.add(new MethodInsnNode(INVOKESTATIC,H,name,desc,false));}
 static byte[] transform(ClassLoader loader,String owner,byte[] bytes)throws Exception{
  if(!PlannedServiceAgent.Recorder.hash(bytes).equals(((Map)FeignEffectHooks.config().get("class_sha256")).get(owner)))throw new IllegalStateException("Feign protocol class pin differs");ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.EXPAND_FRAMES);
  for(MethodNode m:c.methods){AbstractInsnNode[] original=m.instructions.toArray();
   if(owner.equals("feign/hystrix/HystrixInvocationHandler$1")&&m.name.equals("<init>")){for(AbstractInsnNode n:original)if(n.getOpcode()==RETURN){InsnList x=new InsnList();x.add(new VarInsnNode(ALOAD,0));hook(x,"command","(Ljava/lang/Object;)V");m.instructions.insertBefore(n,x);}continue;}
   if(owner.endsWith("/BeanSerializerBase")&&m.name.equals("serializeWithType")){InsnList x=new InsnList();x.add(new VarInsnNode(ALOAD,1));hook(x,"polymorphic","(Ljava/lang/Object;)V");m.instructions.insert(x);continue;}
   String start=null,end=null;InsnList before=new InsnList();
   if(owner.equals("feign/hystrix/HystrixInvocationHandler$1")&&m.name.equals("run")&&m.desc.equals("()Ljava/lang/Object;")){start="worker";end="workerEnd";before.add(new VarInsnNode(ALOAD,0));hook(before,start,"(Ljava/lang/Object;)Ljava/lang/Object;");}
   if(owner.endsWith("/HystrixCommand")&&m.name.equals("execute")&&m.desc.equals("()Ljava/lang/Object;")){start="join";end="joinEnd";before.add(new VarInsnNode(ALOAD,0));hook(before,start,"(Ljava/lang/Object;)Ljava/lang/Object;");
    for(AbstractInsnNode n:original)if(n instanceof MethodInsnNode&&((MethodInsnNode)n).owner.equals("java/util/concurrent/Future")&&((MethodInsnNode)n).name.equals("get")){InsnList x=new InsnList();x.add(new InsnNode(DUP));x.add(new VarInsnNode(ALOAD,0));x.add(new InsnNode(SWAP));hook(x,"future","(Ljava/lang/Object;Ljava/lang/Object;)V");m.instructions.insertBefore(n,x);}
   }
   if(owner.endsWith("/SpringEncoder")&&m.name.equals("encode")&&m.desc.equals("(Ljava/lang/Object;Ljava/lang/reflect/Type;Lfeign/RequestTemplate;)V")){start="encoder";end="encoderEnd";before.add(new VarInsnNode(ALOAD,0));before.add(new VarInsnNode(ALOAD,1));before.add(new VarInsnNode(ALOAD,2));hook(before,start,"(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;");}
   if(owner.endsWith("/BeanSerializerBase")&&Arrays.asList("serializeFields","serializeFieldsFiltered").contains(m.name)&&m.desc.equals("(Ljava/lang/Object;Lcom/fasterxml/jackson/core/JsonGenerator;Lcom/fasterxml/jackson/databind/SerializerProvider;)V")){start="serialization";end="serializationEnd";before.add(new VarInsnNode(ALOAD,0));before.add(new VarInsnNode(ALOAD,1));before.add(new VarInsnNode(ALOAD,3));before.add(new VarInsnNode(ALOAD,2));hook(before,start,"(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;");}
   if(start==null)continue;int token=m.maxLocals++,error=m.maxLocals++;before.add(new VarInsnNode(ASTORE,token));LabelNode begin=new LabelNode(),finish=new LabelNode(),handler=new LabelNode();before.add(begin);m.instructions.insert(before);
   for(AbstractInsnNode n:original)if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN){InsnList x=new InsnList();x.add(new VarInsnNode(ALOAD,token));x.add(new InsnNode(ACONST_NULL));hook(x,end,"(Ljava/lang/Object;Ljava/lang/Throwable;)V");m.instructions.insertBefore(n,x);}
   m.instructions.add(finish);m.instructions.add(handler);m.instructions.add(new VarInsnNode(ASTORE,error));m.instructions.add(new VarInsnNode(ALOAD,token));m.instructions.add(new VarInsnNode(ALOAD,error));hook(m.instructions,end,"(Ljava/lang/Object;Ljava/lang/Throwable;)V");m.instructions.add(new VarInsnNode(ALOAD,error));m.instructions.add(new InsnNode(ATHROW));m.tryCatchBlocks.add(new TryCatchBlockNode(begin,finish,handler,"java/lang/Throwable"));
  }
  MonitorSafety.instrument(c);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};c.accept(w);Map r=PlannedServiceAgent.Recorder.row();r.put("class",owner);r.put("class_sha256",PlannedServiceAgent.Recorder.hash(bytes));PlannedServiceAgent.Recorder.emit("feign-framework",r);return w.toByteArray();
 }
}
