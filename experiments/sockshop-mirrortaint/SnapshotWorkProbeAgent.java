import java.lang.instrument.*;
import java.security.ProtectionDomain;
import java.nio.file.*;
import java.util.concurrent.atomic.AtomicLongArray;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
/** Diagnostic only: probe both observer implementations, never business classes. */
public class SnapshotWorkProbeAgent implements Opcodes {
 static final AtomicLongArray COUNTS=new AtomicLongArray(4);
 public static void hit(int slot){COUNTS.incrementAndGet(slot);}
 public static void premain(String path,Instrumentation instrumentation){Runtime.getRuntime().addShutdownHook(new Thread(()->{try{Files.write(Paths.get(path),("{\"raw_materializations\":"+COUNTS.get(0)+",\"declared_field_lookups\":"+COUNTS.get(1)+",\"reflective_gets\":"+COUNTS.get(2)+",\"verification_passes\":"+COUNTS.get(3)+"}\n").getBytes("UTF-8"));}catch(Exception e){throw new IllegalStateException(e);}}));instrumentation.addTransformer(new ClassFileTransformer(){public byte[] transform(ClassLoader loader,String name,Class<?> prior,ProtectionDomain domain,byte[] bytes){if(!(name.startsWith("JsonTreeObservationHooks")||name.equals("ResponseBindingHooks")))return null;ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,0);for(MethodNode m:c.methods){if(name.equals("JsonTreeObservationHooks")&&(m.name.equals("elements")||m.name.equals("entries")))m.instructions.insert(mark(0));if(name.endsWith("$Snapshot")&&m.name.equals("verify"))m.instructions.insert(mark(3));for(AbstractInsnNode n:m.instructions.toArray())if(n instanceof MethodInsnNode){MethodInsnNode x=(MethodInsnNode)n;if(x.owner.equals("java/lang/Class")&&x.name.equals("getDeclaredField"))m.instructions.insertBefore(n,mark(1));if(x.owner.equals("java/lang/reflect/Field")&&x.name.equals("get"))m.instructions.insertBefore(n,mark(2));}}ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS);c.accept(w);return w.toByteArray();}});}
 static InsnList mark(int slot){InsnList h=new InsnList();h.add(new LdcInsnNode(slot));h.add(new MethodInsnNode(INVOKESTATIC,"SnapshotWorkProbeAgent","hit","(I)V",false));return h;}
}
