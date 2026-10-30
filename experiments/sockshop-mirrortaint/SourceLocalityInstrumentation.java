import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
/** Observes the decode island and its actual return corridor, never the log chain. */
public final class SourceLocalityInstrumentation implements Opcodes {
 static final String H="SourceLocalityHooks";
 static boolean owns(String c){Map cfg=SourceLocalityHooks.config();return cfg!=null&&((Map)cfg.get("class_sha256")).containsKey(c);}
 static void call(InsnList x,String n,String d){x.add(new MethodInsnNode(INVOKESTATIC,H,n,d,false));}
 static byte[] transform(ClassLoader loader,String owner,byte[] original,byte[] transformed)throws Exception{
  SourceLocalityHooks.framework(owner,original);ClassNode c=new ClassNode(ASM9);new ClassReader(transformed).accept(c,ClassReader.EXPAND_FRAMES);boolean changed=false;
  for(MethodNode m:c.methods){if(m.name.startsWith("$tf2$monitor$"))continue;
   for(AbstractInsnNode n:m.instructions.toArray()){
    if(n instanceof MethodInsnNode){MethodInsnNode i=(MethodInsnNode)n;
     if(owner.endsWith("AbstractJackson2HttpMessageConverter")&&m.name.equals("readJavaType")&&i.owner.equals("com/fasterxml/jackson/databind/ObjectMapper")&&i.name.equals("readValue")&&i.desc.endsWith("Lcom/fasterxml/jackson/databind/JavaType;)Ljava/lang/Object;")){int type=m.maxLocals++,arg=m.maxLocals++;InsnList x=new InsnList();x.add(new VarInsnNode(ASTORE,type));x.add(new VarInsnNode(ASTORE,arg));x.add(new InsnNode(DUP));x.add(new VarInsnNode(ALOAD,type));call(x,"mapper","(Ljava/lang/Object;Ljava/lang/Object;)V");x.add(new VarInsnNode(ALOAD,arg));x.add(new VarInsnNode(ALOAD,type));m.instructions.insertBefore(n,x);InsnList after=new InsnList();after.add(new InsnNode(DUP));call(after,"decoded","(Ljava/lang/Object;)V");m.instructions.insert(n,after);changed=true;}
     if((owner.equals("com/fasterxml/jackson/databind/ObjectMapper")&&m.name.equals("_readMapAndClose")||owner.equals("com/fasterxml/jackson/databind/ObjectReader")&&m.name.equals("_bindAndClose"))&&i.name.equals("_findRootDeserializer")){InsnList x=new InsnList();x.add(new InsnNode(DUP));x.add(new VarInsnNode(ALOAD,1));call(x,"actualDecoder","(Ljava/lang/Object;Ljava/lang/Object;)V");m.instructions.insert(n,x);changed=true;}
     if(owner.endsWith("AbstractJackson2HttpMessageConverter")&&m.name.equals("readJavaType")&&i.owner.equals("com/fasterxml/jackson/databind/ObjectReader")&&i.name.equals("readValue")&&Type.getArgumentTypes(i.desc).length==1){int arg=m.maxLocals++;InsnList before=new InsnList();before.add(new VarInsnNode(ASTORE,arg));before.add(new InsnNode(DUP));call(before,"reader","(Ljava/lang/Object;)V");before.add(new VarInsnNode(ALOAD,arg));m.instructions.insertBefore(n,before);InsnList after=new InsnList();after.add(new InsnNode(DUP));call(after,"decoded","(Ljava/lang/Object;)V");m.instructions.insert(n,after);changed=true;}
     if(owner.equals("com/fasterxml/jackson/databind/deser/std/UntypedObjectDeserializer$Vanilla")&&i.getOpcode()==INVOKESPECIAL&&i.owner.equals("java/util/LinkedHashMap")&&i.name.equals("<init>")){InsnList x=new InsnList();x.add(new InsnNode(DUP));x.add(new LdcInsnNode("default-map"));call(x,"birth","(Ljava/lang/Object;Ljava/lang/String;)V");m.instructions.insert(n,x);changed=true;}
     if(owner.equals("org/springframework/cache/interceptor/CacheAspectSupport")&&i.name.equals("getCacheOperations")&&i.desc.endsWith("Ljava/util/Collection;")){InsnList x=new InsnList();x.add(new InsnNode(DUP));call(x,"cacheOperations","(Ljava/lang/Object;)V");m.instructions.insert(n,x);changed=true;}
    }
    if(owner.equals("feign/SynchronousMethodHandler")&&m.name.equals("invoke")&&n.getOpcode()==ARETURN){InsnList x=new InsnList();x.add(new InsnNode(DUP));call(x,"returned","(Ljava/lang/Object;)V");m.instructions.insertBefore(n,x);changed=true;}
   }
  }
  if(!changed)return transformed;
  // Existing transformers already guarded their hooks. Guard only our new
  // calls so earlier wrappers are not recursively wrapped a second time.
  List<MethodNode> guards=new ArrayList<>();int serial=0;
  for(MethodNode m:new ArrayList<MethodNode>(c.methods))if(!m.name.startsWith("$tf2$monitor$"))for(AbstractInsnNode n:m.instructions.toArray())if(n instanceof MethodInsnNode&&((MethodInsnNode)n).owner.equals(H)){
   MethodInsnNode i=(MethodInsnNode)n;String name="$tf2$locality$"+(serial++);guards.add(MonitorSafety.wrapper(name,i));i.owner=c.name;i.name=name;
  }c.methods.addAll(guards);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};c.accept(w);return w.toByteArray();
 }
}
