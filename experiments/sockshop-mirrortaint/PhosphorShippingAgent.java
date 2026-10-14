import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import edu.columbia.cs.psl.phosphor.org.objectweb.asm.*;

/** Disclosed source/observation adapter; Phosphor performs all tag propagation.
 * Load this agent before Phosphor so Phosphor instruments the injected calls.
 */
public final class PhosphorShippingAgent implements ClassFileTransformer, Opcodes {
    private static final String RECORDER = "PhosphorShippingAgent$Recorder";
    public static void premain(String args, Instrumentation instrumentation) throws Exception {
        System.out.println("PHOSPHOR_ADAPTER registering");
        // Keep the transformer and its visitors in one uninstrumented domain.
        // Recorder is deliberately loaded later and instrumented by Phosphor.
        Class.forName("PhosphorShippingAgent$1");
        Class.forName("PhosphorShippingAgent$1$1");
        instrumentation.addTransformer(new PhosphorShippingAgent());
        System.out.println("PHOSPHOR_ADAPTER registered");
    }

    // The instrumented Java8 ClassFileTransformer interface dispatches through
    // this array-tag signature (the same bridge provided by Phosphor's agent).
    // Without it the JVM silently ignores this uninstrumented companion agent.
    public edu.columbia.cs.psl.phosphor.struct.LazyByteArrayObjTags transform$$PHOSPHORTAGGED(
            ClassLoader loader, String name, Class<?> prior, ProtectionDomain domain,
            edu.columbia.cs.psl.phosphor.struct.LazyByteArrayObjTags tags, byte[] bytes) {
        return new edu.columbia.cs.psl.phosphor.struct.LazyByteArrayObjTags(
            transform(loader, name, prior, domain, bytes));
    }

    public byte[] transform(ClassLoader loader, String name, Class<?> prior,
                            ProtectionDomain domain, byte[] bytes) {
        if (!"works/weave/socks/shipping/controllers/ShippingController".equals(name)) return null;
        try {
            ClassReader reader = new ClassReader(bytes);
            ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
            reader.accept(new ClassVisitor(ASM5, writer) {
                public MethodVisitor visitMethod(int access, String method, String descriptor,
                                                  String signature, String[] exceptions) {
                    MethodVisitor next = super.visitMethod(access, method, descriptor, signature, exceptions);
                    if (!method.equals("postShipping") || !descriptor.equals(
                        "(Lworks/weave/socks/shipping/entities/Shipment;)Lworks/weave/socks/shipping/entities/Shipment;")) return next;
                    return new MethodVisitor(ASM5, next) {
                        public void visitCode() {
                            super.visitCode();
                            super.visitVarInsn(ALOAD, 1);
                            super.visitMethodInsn(INVOKESTATIC, RECORDER, "enter", "(Ljava/lang/Object;)V", false);
                        }
                        public void visitInsn(int opcode) {
                            if (opcode == ARETURN) {
                                super.visitInsn(DUP);
                                super.visitMethodInsn(INVOKESTATIC, RECORDER, "exit", "(Ljava/lang/Object;)V", false);
                            }
                            super.visitInsn(opcode);
                        }
                    };
                }
            }, 0);
            System.out.println("PHOSPHOR_ADAPTER controller-instrumented");
            return writer.toByteArray();
        } catch (Throwable error) {
            System.err.println("PHOSPHOR_ADAPTER_ERROR " + error);
            throw new IllegalStateException(error);
        }
    }

    public static final class Recorder {
        private static final java.util.concurrent.atomic.AtomicLong NEXT = new java.util.concurrent.atomic.AtomicLong();
        private static final ThreadLocal<Long> INVOCATION = new ThreadLocal<Long>();
        private static final String[] FIELDS = {"id", "name"};

        private static String quote(String value) {
            if (value == null) return "null";
            return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
        }

        private static Object field(Object shipment, String name) throws Exception {
            return shipment.getClass().getMethod(name.equals("id") ? "getId" : "getName").invoke(shipment);
        }

        private static String tags(Object value) {
            edu.columbia.cs.psl.phosphor.runtime.Taint<?> taint =
                edu.columbia.cs.psl.phosphor.runtime.MultiTainter.getTaint(value);
            java.util.Set<String> labels = new java.util.TreeSet<String>();
            if (taint != null) {
                if (taint.getLabel() != null) labels.add(taint.getLabel().toString());
                if (taint.getDependencies() != null) {
                    edu.columbia.cs.psl.phosphor.struct.LinkedList.Node<?> node = taint.getDependencies().getFirst();
                    while (node != null) {
                        if (node.entry != null) labels.add(node.entry.toString());
                        node = node.next;
                    }
                }
            }
            StringBuilder json = new StringBuilder("[");
            for (String label : labels) {
                if (json.length() > 1) json.append(',');
                json.append(quote(label));
            }
            return json.append(']').toString();
        }

        private static void emit(String phase, long invocation, String name, Object value, String label) {
            System.out.println("PHOSPHOR_BOUNDARY {\"phase\":" + quote(phase) + ",\"invocation\":" + invocation
                + ",\"field\":" + quote(name) + ",\"value\":" + quote(value == null ? null : value.toString())
                + ",\"configured_source_label\":" + quote(label) + ",\"tags\":" + tags(value) + "}");
        }

        public static void enter(Object shipment) {
            try {
                long invocation = NEXT.incrementAndGet();
                INVOCATION.set(invocation);
                for (String name : FIELDS) {
                    Object value = field(shipment, name);
                    String label = "shipping:" + invocation + ":" + name;
                    edu.columbia.cs.psl.phosphor.runtime.MultiTainter.taintedObject(value,
                        new edu.columbia.cs.psl.phosphor.runtime.Taint<String>(label));
                    emit("source", invocation, name, value, label);
                }
            } catch (Throwable error) {
                System.err.println("PHOSPHOR_ADAPTER_ERROR source " + error);
                throw new IllegalStateException(error);
            }
        }

        public static void exit(Object shipment) {
            try {
                Long invocation = INVOCATION.get();
                if (invocation == null) throw new IllegalStateException("Missing source invocation");
                // Only read native tags here; never set a target tag or use values to join labels.
                for (String name : FIELDS) emit("sink", invocation, name, field(shipment, name), null);
                INVOCATION.remove();
            } catch (Throwable error) {
                System.err.println("PHOSPHOR_ADAPTER_ERROR sink " + error);
                throw new IllegalStateException(error);
            }
        }
    }
}
