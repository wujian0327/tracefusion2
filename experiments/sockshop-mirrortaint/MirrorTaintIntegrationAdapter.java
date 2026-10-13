import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import org.stack.taint.asm.*;
import org.stack.taint.asm.tree.*;
import javassist.*;

/** Pinned-JAR integration repair, independently named; does not synthesize result labels. */
public final class MirrorTaintIntegrationAdapter implements ClassFileTransformer {
    private final String mode;
    private final String prefix;

    private MirrorTaintIntegrationAdapter(String mode) {
        this.mode = mode;
        this.prefix = System.getProperty("taint.app", "works.weave.socks").replace('.', '/') + "/";
    }

    public static void premain(String mode, Instrumentation instrumentation) {
        if (!"fields".equals(mode) && !"strings".equals(mode) && !"sources".equals(mode)
            && !"threads".equals(mode) && !"logging".equals(mode) && !"streams".equals(mode) && !"returns".equals(mode))
            throw new IllegalArgumentException("Unsupported adapter mode");
        if ("strings".equals(mode)) {
            try {
                // Initialize the pinned agent's lambda-based configuration before either agent
                // registers class-load callbacks, avoiding bootstrap class circularity on JDK 8.
                Class.forName("com.shadow.taint.agent.A.B");
                Class.forName("javassist.ClassPool");
                Class.forName("com.shadow.taint.agent.K.F");
                Class.forName("com.shadow.taint.agent.K.G");
            } catch (ClassNotFoundException error) { throw new IllegalStateException(error); }
        }
        instrumentation.addTransformer(new MirrorTaintIntegrationAdapter(mode));
        System.err.println("TF2_MT_ADAPTER enabled=" + mode);
    }

    public byte[] transform(ClassLoader loader, String name, Class<?> type,
                            ProtectionDomain domain, byte[] bytes) {
        if (name == null) return null;
        if ("sources".equals(mode)) {
            if (!name.equals("com/shadow/taint/agent/runtime/TaintTagger")) return null;
        } else if ("threads".equals(mode)) {
            if (!name.equals("org/springframework/aop/interceptor/AsyncExecutionAspectSupport")) return null;
        } else if ("logging".equals(mode)) {
            if (!name.equals("com/shadow/taint/agent/runtime/TaintCollector")) return null;
        } else if (!name.startsWith(prefix)) return null;
        try {
            if ("sources".equals(mode)) return prepareSourceBoundary(bytes);
            if ("threads".equals(mode)) return adaptSpringSubmit(bytes);
            if ("logging".equals(mode)) return boundCollector(bytes);
            if ("streams".equals(mode)) return applyStreamRule(loader, name, bytes);
            if ("returns".equals(mode)) return captureMapperReturns(bytes);
            return "fields".equals(mode) ? repairReceivers(name, bytes) : applyStringRules(loader, name, bytes);
        } catch (Throwable error) {
            System.err.println("TF2_MT_ADAPTER error mode=" + mode + " class=" + name + " cause=" + error);
            // Record failure; runner must reject this run. JVM may continue with original bytecode.
            return null;
        }
    }

    private static byte[] applyStreamRule(ClassLoader loader, String name, byte[] bytes) throws Exception {
        ClassPool pool = new ClassPool(true);
        pool.appendClassPath(new LoaderClassPath(loader));
        CtClass cls = pool.makeClass(new java.io.ByteArrayInputStream(bytes));
        try {
            for (CtBehavior method : cls.getDeclaredBehaviors()) {
                if (Modifier.isAbstract(method.getModifiers()) || Modifier.isNative(method.getModifiers())) continue;
                method.instrument(new javassist.expr.ExprEditor() {
                    public void edit(javassist.expr.MethodCall call) throws CannotCompileException {
                        if (call.getClassName().equals("java.util.stream.DoubleStream") && call.getMethodName().equals("sum")
                            && call.getSignature().equals("()D"))
                            call.replace("{$_ = MirrorTaintStreamAdapter.sum($0);}");
                    }
                });
            }
            return cls.toBytecode();
        } finally { cls.detach(); }
    }

    private static byte[] captureMapperReturns(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassNode cls = new ClassNode(Opcodes.ASM9);
        reader.accept(cls, 0);
        int captured = 0;
        for (MethodNode method : cls.methods) {
            if (!(method.name.startsWith("lambda$") || method.name.equals("applyAsDouble"))
                || !Type.getReturnType(method.desc).equals(Type.DOUBLE_TYPE)) continue;
            for (AbstractInsnNode node : method.instructions.toArray()) {
                if (!(node instanceof MethodInsnNode)) continue;
                MethodInsnNode call = (MethodInsnNode) node;
                if (call.owner.equals("com/shadow/taint/agent/model/StackFrame") && call.name.equals("visitReturn") && call.desc.equals("(D)V")) {
                    method.instructions.insert(call, new MethodInsnNode(Opcodes.INVOKESTATIC, "MirrorTaintStreamAdapter", "mapperReturned", "()V", false));
                    captured++;
                }
            }
        }
        if (captured == 0) return null;
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        cls.accept(writer);
        System.err.println("TF2_MT_ADAPTER mapper-return-hooks class=" + cls.name + " count=" + captured);
        return writer.toByteArray();
    }

    private static byte[] boundCollector(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassNode cls = new ClassNode(Opcodes.ASM9);
        reader.accept(cls, 0);
        int methods = 0;
        for (MethodNode method : cls.methods) {
            if (!method.name.equals("collect") || !(method.desc.equals("(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V")
                || method.desc.equals("(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V"))) continue;
            method.instructions.clear(); method.tryCatchBlocks.clear();
            if (method.localVariables != null) method.localVariables.clear();
            method.instructions.add(new VarInsnNode(Opcodes.ALOAD, 0));
            method.instructions.add(new VarInsnNode(Opcodes.ALOAD, 1));
            method.instructions.add(new VarInsnNode(Opcodes.ALOAD, 2));
            method.instructions.add(new MethodInsnNode(Opcodes.INVOKESTATIC, "MirrorTaintLogAdapter", "collect",
                "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V", false));
            method.instructions.add(new InsnNode(Opcodes.RETURN));
            method.maxStack = 3; method.maxLocals = 3; methods++;
        }
        if (methods != 2) throw new IllegalStateException("Expected two pinned collector overloads");
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        cls.accept(writer);
        System.err.println("TF2_MT_ADAPTER bounded-event-collector installed");
        return writer.toByteArray();
    }

    private static byte[] adaptSpringSubmit(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassNode cls = new ClassNode(Opcodes.ASM9);
        reader.accept(cls, 0);
        int adapted = 0;
        for (MethodNode method : cls.methods) {
            for (AbstractInsnNode node : method.instructions.toArray()) {
                if (!(node instanceof MethodInsnNode)) continue;
                MethodInsnNode call = (MethodInsnNode) node;
                if (call.owner.equals("org/springframework/core/task/AsyncTaskExecutor") && call.name.equals("submit")
                    && call.desc.equals("(Ljava/util/concurrent/Callable;)Ljava/util/concurrent/Future;")) {
                    method.instructions.set(call, new MethodInsnNode(Opcodes.INVOKESTATIC, "MirrorTaintThreadAdapter", "submit",
                        "(Ljava/util/concurrent/Executor;Ljava/util/concurrent/Callable;)Ljava/util/concurrent/Future;", false));
                    adapted++;
                }
            }
        }
        // Spring 4.3 doSubmit has one Future branch and one fire-and-forget fallback.
        if (adapted != 2) throw new IllegalStateException("Expected two Spring 4.3 Future submit sites, found " + adapted);
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        cls.accept(writer);
        System.err.println("TF2_MT_ADAPTER spring-future-submit adapted=" + adapted);
        return writer.toByteArray();
    }

    private static byte[] applyStringRules(ClassLoader loader, String name, byte[] bytes) throws Exception {
        ClassPool pool = new ClassPool(true);
        pool.appendClassPath(new LoaderClassPath(loader));
        CtClass cls = pool.makeClass(new java.io.ByteArrayInputStream(bytes));
        try {
            // Invoke the original JAR's existing append/toString rules before its stack instrumentation.
            for (CtBehavior method : cls.getDeclaredBehaviors()) {
                if (Modifier.isAbstract(method.getModifiers()) || Modifier.isNative(method.getModifiers())) continue;
                method.instrument(new com.shadow.taint.agent.K.F());
                method.instrument(new com.shadow.taint.agent.K.G());
            }
            System.err.println("TF2_MT_ADAPTER original-string-rules class=" + name);
            return cls.toBytecode();
        } finally { cls.detach(); }
    }

    private static AbstractInsnNode nextInstruction(AbstractInsnNode node) {
        if (node == null) return null;
        do { node = node.getNext(); } while (node != null && node.getOpcode() < 0);
        return node;
    }

    private static byte[] prepareSourceBoundary(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
            public MethodVisitor visitMethod(int access, String name, String desc, String signature, String[] exceptions) {
                MethodVisitor mv = super.visitMethod(access, name, desc, signature, exceptions);
                if (!name.equals("tagDbQueryResult")
                    || !desc.equals("(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V")) return mv;
                return new MethodVisitor(Opcodes.ASM9, mv) {
                    public void visitCode() {
                        super.visitCode();
                        super.visitVarInsn(Opcodes.ALOAD, 2);
                        super.visitMethodInsn(Opcodes.INVOKESTATIC, "MirrorTaintIntegrationAdapter", "prepareSource",
                            "(Ljava/lang/Object;)V", false);
                    }
                    public void visitInsn(int opcode) {
                        if (opcode == Opcodes.RETURN && Boolean.getBoolean("tf2.mt.logging")) {
                            super.visitVarInsn(Opcodes.ALOAD, 0);
                            super.visitVarInsn(Opcodes.ALOAD, 1);
                            super.visitVarInsn(Opcodes.ALOAD, 2);
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, "MirrorTaintLogAdapter", "sourceCompleted",
                                "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V", false);
                        }
                        super.visitInsn(opcode);
                    }
                };
            }
        }, 0);
        System.err.println("TF2_MT_ADAPTER prepare-empty-source-slots installed");
        return writer.toByteArray();
    }

    public static void prepareSource(Object object) {
        if (!com.shadow.taint.agent.runtime.TaintHeap.available()) return;
        try {
            java.util.Set<Object> seen = java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<Object, Boolean>());
            clearEmptySourceSlots(object, seen, 0);
        } catch (Throwable error) {
            System.err.println("TF2_MT_ADAPTER error mode=sources cause=" + error);
        }
    }

    private static void clearEmptySourceSlots(Object object, java.util.Set<Object> seen, int depth) throws Exception {
        if (object == null || depth >= 10 || !seen.add(object)) return;
        java.util.Map<String, com.shadow.taint.agent.model.A> fields = com.shadow.taint.agent.runtime.TaintHeap.B.get().get(object);
        if (fields != null) fields.entrySet().removeIf(e -> e.getValue() == null || e.getValue().A().isEmpty());
        Class<?> type = object.getClass();
        if (type.isArray()) {
            if (!type.getComponentType().isPrimitive())
                for (Object item : (Object[]) object) clearEmptySourceSlots(item, seen, depth + 1);
        } else if (object instanceof java.util.Collection) {
            for (Object item : (java.util.Collection<?>) object) clearEmptySourceSlots(item, seen, depth + 1);
        } else if (object instanceof java.util.Map) {
            for (java.util.Map.Entry<?, ?> entry : ((java.util.Map<?, ?>) object).entrySet()) {
                clearEmptySourceSlots(entry.getKey(), seen, depth + 1);
                clearEmptySourceSlots(entry.getValue(), seen, depth + 1);
            }
        } else if (!type.getName().startsWith("java.") && !type.isEnum()) {
            for (Class<?> current = type; current != Object.class && current != null; current = current.getSuperclass()) {
                for (java.lang.reflect.Field field : current.getDeclaredFields()) {
                    if (java.lang.reflect.Modifier.isStatic(field.getModifiers()) || field.getType().isPrimitive()) continue;
                    field.setAccessible(true);
                    clearEmptySourceSlots(field.get(object), seen, depth + 1);
                }
            }
        }
    }

    private static byte[] repairReceivers(String name, byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassNode cls = new ClassNode(Opcodes.ASM9);
        reader.accept(cls, 0);
        int repaired = 0;
        int deferred = 0;
        for (MethodNode method : cls.methods) {
            boolean initializedReceiver = !method.name.equals("<init>");
            for (AbstractInsnNode node : method.instructions.toArray()) {
                if (node instanceof MethodInsnNode) {
                    MethodInsnNode invocation = (MethodInsnNode) node;
                    if (invocation.getOpcode() == Opcodes.INVOKESPECIAL && invocation.name.equals("<init>")
                        && (invocation.owner.equals(cls.superName) || invocation.owner.equals(cls.name)))
                        initializedReceiver = true;
                }
                if (!(node instanceof LdcInsnNode) || !(((LdcInsnNode) node).cst instanceof String)) continue;
                String placeholder = (String) ((LdcInsnNode) node).cst;
                if (!placeholder.endsWith("-instance")) continue;
                AbstractInsnNode[] seq = new AbstractInsnNode[8];
                AbstractInsnNode cursor = node;
                for (int i = 0; i < seq.length; i++) { cursor = nextInstruction(cursor); seq[i] = cursor; }
                // Exact original hook signature: frame load, swap, opcode, owner, name, desc, hook, field.
                if (!(seq[0] instanceof VarInsnNode) || seq[0].getOpcode() != Opcodes.ALOAD
                    || seq[1] == null || seq[1].getOpcode() != Opcodes.SWAP
                    || !(seq[2] instanceof LdcInsnNode) || !(seq[3] instanceof LdcInsnNode)
                    || !(seq[4] instanceof LdcInsnNode) || !(seq[5] instanceof LdcInsnNode)
                    || !(seq[6] instanceof MethodInsnNode) || !(seq[7] instanceof FieldInsnNode)) continue;
                MethodInsnNode hook = (MethodInsnNode) seq[6];
                FieldInsnNode field = (FieldInsnNode) seq[7];
                if (!hook.owner.equals("com/shadow/taint/agent/model/StackFrame")
                    || !hook.name.equals("visitFieldInsn")
                    || !hook.desc.equals("(Ljava/lang/Object;ILjava/lang/String;Ljava/lang/String;Ljava/lang/String;)V")
                    || !placeholder.equals(field.owner + "-instance")
                    || !Integer.valueOf(field.getOpcode()).equals(((LdcInsnNode) seq[2]).cst)
                    || !field.owner.equals(((LdcInsnNode) seq[3]).cst)
                    || !field.name.equals(((LdcInsnNode) seq[4]).cst)
                    || !field.desc.equals(((LdcInsnNode) seq[5]).cst)) continue;
                // Captured anonymous/inner-class fields may be assigned before super():
                // JVM uninitializedThis cannot be passed to an Object-taking hook.
                if (!initializedReceiver) { deferred++; continue; }
                InsnList replacement = new InsnList();
                if (field.getOpcode() == Opcodes.GETFIELD) {
                    replacement.add(new InsnNode(Opcodes.DUP));
                } else if (field.getOpcode() == Opcodes.PUTFIELD) {
                    if (Type.getType(field.desc).getSize() == 2) {
                        replacement.add(new InsnNode(Opcodes.DUP2_X1));
                        replacement.add(new InsnNode(Opcodes.POP2));
                        replacement.add(new InsnNode(Opcodes.DUP_X2));
                    } else {
                        replacement.add(new InsnNode(Opcodes.DUP2));
                        replacement.add(new InsnNode(Opcodes.POP));
                    }
                } else continue; // Static field hooks have no receiver to repair.
                method.instructions.insertBefore(node, replacement);
                method.instructions.remove(node);
                repaired++;
            }
        }
        if (deferred != 0)
            System.err.println("TF2_MT_ADAPTER deferred-uninitialized-receivers class=" + name + " count=" + deferred);
        if (repaired == 0) return null;
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        cls.accept(writer);
        System.err.println("TF2_MT_ADAPTER repaired-field-receivers class=" + name + " count=" + repaired);
        return writer.toByteArray();
    }
}
