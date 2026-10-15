import java.lang.instrument.*;
import java.security.ProtectionDomain;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Disclosed optional suppression of the pinned core's agent-info channel only.
 * No propagation, native tag collection, runtime-error, or sink method changes.
 * Argument strings are still constructed by callers; not a minimum-cost claim.
 */
public final class QuietDiagnosticAgent implements ClassFileTransformer, Opcodes {
    public static void premain(String args, Instrumentation instrumentation) {
        instrumentation.addTransformer(new QuietDiagnosticAgent());
    }
    public byte[] transform(ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes) {
        if (!owner.equals("com/shadow/taint/agent/G/D")) return null;
        ClassNode cls=new ClassNode(ASM9);new ClassReader(bytes).accept(cls,0);
        Set<String> expected=new HashSet<>(Arrays.asList("A(Ljava/lang/String;)V","A(Ljava/lang/String;I)V","B(CI)V"));
        int count=0;
        for (MethodNode m:cls.methods) if (expected.contains(m.name+m.desc)) {
            m.instructions.clear();m.tryCatchBlocks.clear();
            if(m.localVariables!=null)m.localVariables.clear();
            m.instructions.add(new InsnNode(RETURN));m.maxStack=0;count++;
        }
        if(count!=3)throw new IllegalStateException("Pinned diagnostic signatures differ");
        ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS);cls.accept(w);
        System.err.println("TF2_MT_QUIET agent-info methods suppressed=3; errors, sink and native labels retained");
        return w.toByteArray();
    }
}
