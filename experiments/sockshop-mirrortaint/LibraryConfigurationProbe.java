import java.lang.instrument.*;
import java.security.ProtectionDomain;
import java.lang.reflect.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
/** Opt-in diagnostic agent: configuration TYPES, no source/dependency answers. */
public class LibraryConfigurationProbe implements Opcodes {
 static String output;static final Set<String> FOLLOW=new HashSet<>(Arrays.asList("h","advised","targetSource","target","dispatch","methodHandlers","metadata","buildTemplateFromArgs","encoder","delegate","factory","client","requestInterceptors","bodyIndex","returnType","indexToExpander","fallback","fallbackFactory","mongoOperations","converter","conversions","mappingContext","entityInformation","entityMetadata","propertyAccessorFactory","persistentEntities","persistentEntityCache","accessorFactory"));
 public static void premain(String entry,Instrumentation i){output=System.getProperty("library.probe.output");final int at=entry.indexOf('.');final String owner=entry.substring(0,at),method=entry.substring(at+1);i.addTransformer(new ClassFileTransformer(){public byte[] transform(ClassLoader l,String n,Class<?> c,ProtectionDomain d,byte[] b){if(!owner.equals(n))return null;try{ClassNode node=new ClassNode(ASM9);new ClassReader(b).accept(node,0);for(MethodNode m:node.methods)if((m.name+m.desc).equals(method)){InsnList before=new InsnList();before.add(new VarInsnNode(ALOAD,0));before.add(new MethodInsnNode(INVOKESTATIC,"LibraryConfigurationProbe","dump","(Ljava/lang/Object;)V",false));m.instructions.insert(before);for(AbstractInsnNode ins:m.instructions.toArray())if(ins.getOpcode()==ARETURN){InsnList after=new InsnList();after.add(new VarInsnNode(ALOAD,0));after.add(new MethodInsnNode(INVOKESTATIC,"LibraryConfigurationProbe","dump","(Ljava/lang/Object;)V",false));m.instructions.insertBefore(ins,after);}}ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS);node.accept(w);return w.toByteArray();}catch(Throwable failure){throw new IllegalStateException(failure);}}});}
 static void walk(Object o,String path,int depth,IdentityHashMap<Object,Boolean> seen,List<String> lines)throws Exception{
  if(o==null){lines.add(path+" null");return;}Class<?> c=o.getClass();lines.add(path+" "+c.getName());if(depth>8||seen.size()>500||seen.put(o,true)!=null)return;
  if(o instanceof Class){lines.add(path+".class "+((Class)o).getName());return;}if(o instanceof Number){lines.add(path+".number "+o);return;}if(c.isEnum()){lines.add(path+".enum "+((Enum)o).name());return;}if(o instanceof String||c.getName().startsWith("java.lang.reflect.Method"))return;
  if(Proxy.isProxyClass(c)){walk(Proxy.getInvocationHandler(o),path+".handler",depth+1,seen,lines);return;}
  if(o instanceof Map){int j=0;for(Object v:((Map)o).values()){if(j==6)break;walk(v,path+".value"+(j++),depth+1,seen,lines);}return;}
  if(o instanceof Iterable){int j=0;for(Object v:(Iterable)o){if(j==6)break;walk(v,path+".item"+(j++),depth+1,seen,lines);}return;}
  for(Class<?> k=c;k!=null&&!k.getName().startsWith("java.");k=k.getSuperclass())for(Field f:k.getDeclaredFields())if(!Modifier.isStatic(f.getModifiers())&&(depth==0||PlannedServiceAgent.hashes.containsKey(c.getName().replace('.','/'))||FOLLOW.contains(f.getName()))){f.setAccessible(true);walk(f.get(o),path+"."+f.getName(),depth+1,seen,lines);}
 }
 public static synchronized void dump(Object receiver){try{List<String> lines=new ArrayList<>();walk(receiver,"root",0,new IdentityHashMap<>(),lines);lines.add("END");Files.write(Paths.get(output),(String.join("\n",lines)+"\n").getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE,StandardOpenOption.APPEND);}catch(Throwable failure){try{Files.write(Paths.get(output),("PROBE_FAILURE "+failure.getClass().getName()+"\n").getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE,StandardOpenOption.APPEND);}catch(Exception ignored){}}}
}
