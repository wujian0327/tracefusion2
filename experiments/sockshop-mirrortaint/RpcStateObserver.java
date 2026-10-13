import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import com.shadow.taint.agent.runtime.TaintHeap;
import org.stack.taint.asm.*;

/** Diagnostic observer only. Does not initialize, copy, clear, or repair taint state. */
public final class RpcStateObserver {
    public static void premain(String options, Instrumentation instrumentation) {
        instrumentation.addTransformer(new ClassFileTransformer() {
            public byte[] transform(ClassLoader loader, String name, Class<?> type,
                                    ProtectionDomain domain, byte[] bytes) {
                if (!"org/springframework/web/client/RestTemplate".equals(name)) return null;
                try {
                    ClassReader reader = new ClassReader(bytes);
                    ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
                    reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
                        public MethodVisitor visitMethod(int access, String name, String desc,
                                                         String signature, String[] exceptions) {
                            MethodVisitor mv = super.visitMethod(access, name, desc, signature, exceptions);
                            if (!"exchange".equals(name)) return mv;
                            return new MethodVisitor(Opcodes.ASM9, mv) {
                                private void observe(String phase) {
                                    super.visitLdcInsn(phase);
                                    super.visitVarInsn(Opcodes.ALOAD, 1);
                                    super.visitMethodInsn(Opcodes.INVOKESTATIC, "RpcStateObserver", "observe",
                                                         "(Ljava/lang/String;Ljava/lang/Object;)V", false);
                                }
                                public void visitCode() {
                                    super.visitCode();
                                    observe("enter");
                                }
                                public void visitInsn(int opcode) {
                                    if (opcode == Opcodes.ARETURN) observe("exit");
                                    super.visitInsn(opcode);
                                }
                            };
                        }
                    }, 0);
                    System.err.println("TF2_RPC_OBSERVER installed RestTemplate.exchange");
                    return writer.toByteArray();
                } catch (Throwable error) {
                    System.err.println("TF2_RPC_OBSERVER transform-error " + error);
                    return null;
                }
            }
        });
    }

    public static void observe(String phase, Object request) {
        try {
            Object url = request.getClass().getMethod("getUrl").invoke(request);
            Object method = request.getClass().getMethod("getMethod").invoke(request);
            System.err.println("TF2_RPC_OBSERVER phase=" + phase + " thread="
                + Thread.currentThread().getName() + " available=" + TaintHeap.available()
                + " method=" + method + " url=" + url);
        } catch (Throwable error) {
            System.err.println("TF2_RPC_OBSERVER observation-error " + error);
        }
    }
}
