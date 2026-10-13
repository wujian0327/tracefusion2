package tracefusion.boundary;

import java.lang.instrument.*;
import java.security.ProtectionDomain;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Java 8 service boundary frontend. Records observations, never propagates source labels. */
public final class BoundaryAgent implements ClassFileTransformer, Opcodes {
    private static final String R = "tracefusion/boundary/BoundaryRecorder";
    private static final String APP = "works/weave/socks/orders/";
    private static final Set<String> DTOS = new HashSet<>(Arrays.asList("Item", "Customer", "Address", "Card", "CustomerOrder"));
    public static void premain(String args, Instrumentation instrumentation) throws Exception {
        if ("cost".equals(args)) { tracefusion.cost.CostAgent.premain(args,instrumentation); return; }
        BoundaryRecorder.start();
        instrumentation.addTransformer(new BoundaryAgent());
    }
    private static boolean observed(String owner, MethodNode method) {
        return (owner.equals("works/weave/socks/orders/controllers/OrdersController") && method.name.equals("newOrder"))
            || (owner.equals("works/weave/socks/cart/controllers/CartsController") && Arrays.asList("get", "delete", "mergeCarts").contains(method.name))
            || (owner.equals("works/weave/socks/shipping/controllers/ShippingController") && method.name.equals("postShipping"));
    }
    public byte[] transform(final ClassLoader loader, String name, Class<?> prior, ProtectionDomain domain, byte[] bytes) {
        boolean app = name != null && name.startsWith("works/weave/socks/");
        boolean dto = app && name.contains("/entities/");
        boolean rest = false;
        if (!app) return null;
        try {
            if (prior != null) throw new IllegalStateException("Redefinition unsupported");
            ClassNode clazz = new ClassNode(ASM9);
            new ClassReader(bytes).accept(clazz, ClassReader.EXPAND_FRAMES);
            int changed = 0;
            for (MethodNode method : clazz.methods) {
                if ((method.access & (ACC_ABSTRACT | ACC_NATIVE)) != 0) continue;
                boolean rpc = false;
                boolean frame = observed(name, method);
                boolean boundary = name.startsWith("works/weave/socks/cart/") && !BoundaryRecorder.metricsOnly();
                if (!dto && !frame && !boundary) continue;
                AbstractInsnNode[] original = method.instructions.toArray();
                boolean initialized = !method.name.equals("<init>");
                AbstractInsnNode entryPoint = initialized ? null : original[0];
                for (AbstractInsnNode instruction : original) {
                    if (!initialized && instruction instanceof MethodInsnNode) {
                        MethodInsnNode call = (MethodInsnNode) instruction;
                        if (call.getOpcode() == INVOKESPECIAL && call.name.equals("<init>")
                            && (call.owner.equals(clazz.name) || call.owner.equals(clazz.superName))) {
                            initialized = true; entryPoint = instruction;
                        }
                    }
                    if (dto && !BoundaryRecorder.metricsOnly() && !BoundaryRecorder.mirror() && initialized && instruction instanceof FieldInsnNode) {
                        FieldInsnNode field = (FieldInsnNode) instruction;
                        if (field.getOpcode() == GETFIELD || field.getOpcode() == PUTFIELD) {
                            observeField(method, field); changed++;
                        }
                    }
                    if (boundary && instruction instanceof MethodInsnNode) {
                        MethodInsnNode call = (MethodInsnNode) instruction;
                        if (call.owner.equals("works/weave/socks/cart/cart/CartDAO")) {
                            if (call.name.equals("findByCustomerId")) {
                                InsnList after = new InsnList(); after.add(new InsnNode(DUP));
                                after.add(new LdcInsnNode(call.owner + "." + call.name + call.desc));
                                after.add(new MethodInsnNode(INVOKESTATIC, R, "source", "(Ljava/lang/Object;Ljava/lang/String;)V", false));
                                method.instructions.insert(call, after); changed++;
                            } else if ((call.name.equals("save") || call.name.equals("delete")) && Type.getArgumentTypes(call.desc).length == 1) {
                                InsnList before = new InsnList(); before.add(new InsnNode(DUP));
                                before.add(new LdcInsnNode(call.owner + "." + call.name + call.desc));
                                before.add(new MethodInsnNode(INVOKESTATIC, R, "sink", "(Ljava/lang/Object;Ljava/lang/String;)V", false));
                                method.instructions.insertBefore(call, before); changed++;
                            }
                        }
                    }
                }
                if (frame || rpc) {
                    if (!initialized) throw new IllegalStateException("Constructor initialization not found");
                    LabelNode start = new LabelNode(), end = new LabelNode(), handler = new LabelNode();
                    InsnList enter = new InsnList();
                    {
                        enter.add(new LdcInsnNode(name + "." + method.name + method.desc));
                        enter.add((method.access & ACC_STATIC) != 0 ? new InsnNode(ACONST_NULL) : new VarInsnNode(ALOAD, 0));
                        arguments(enter, method);
                        enter.add(new MethodInsnNode(INVOKESTATIC, R, "enter", "(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)V", false));
                    }
                    enter.add(start);
                    if (entryPoint == null) method.instructions.insert(enter); else method.instructions.insert(entryPoint, enter);
                    for (AbstractInsnNode instruction : original) {
                        int opcode = instruction.getOpcode();
                        if (opcode < IRETURN || opcode > RETURN) continue;
                        InsnList exit = new InsnList();
                        if (opcode == RETURN) exit.add(new InsnNode(ACONST_NULL));
                        else {
                            Type value = Type.getReturnType(method.desc);
                            exit.add(new InsnNode(value.getSize() == 2 ? DUP2 : DUP)); box(exit, value);
                        }
                        exit.add(new MethodInsnNode(INVOKESTATIC, R, "exit", "(Ljava/lang/Object;)V", false));
                        method.instructions.insertBefore(instruction, exit);
                    }
                    method.instructions.add(end); method.instructions.add(handler);
                    int error = method.maxLocals++;
                    method.instructions.add(new VarInsnNode(ASTORE, error));
                    method.instructions.add(new LdcInsnNode("frame"));
                    method.instructions.add(new MethodInsnNode(INVOKESTATIC, R, "abort", "(Ljava/lang/String;)V", false));
                    method.instructions.add(new VarInsnNode(ALOAD, error)); method.instructions.add(new InsnNode(ATHROW));
                    method.tryCatchBlocks.add(new TryCatchBlockNode(start, end, handler, "java/lang/Throwable"));
                    changed++;
                }
            }
            if (changed == 0) return null;
            ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS) {
                protected String getCommonSuperClass(String first, String second) {
                    try {
                        Class<?> a = Class.forName(first.replace('/', '.'), false, loader);
                        Class<?> b = Class.forName(second.replace('/', '.'), false, loader);
                        if (a.isAssignableFrom(b)) return first;
                        if (b.isAssignableFrom(a)) return second;
                        if (a.isInterface() || b.isInterface()) return "java/lang/Object";
                        do { a = a.getSuperclass(); } while (!a.isAssignableFrom(b));
                        return a.getName().replace('.', '/');
                    } catch (ClassNotFoundException error) { throw new IllegalStateException(error); }
                }
            };
            clazz.accept(writer);
            BoundaryRecorder.transformed(name, bytes);
            return writer.toByteArray();
        } catch (Throwable error) { BoundaryRecorder.problem("transform:" + name + ":" + error); return null; }
    }
    private static void observeField(MethodNode method, FieldInsnNode field) {
        Type type = Type.getType(field.desc);
        int object = method.maxLocals++, value = method.maxLocals;
        method.maxLocals += type.getSize();
        InsnList before = new InsnList(), after = new InsnList();
        if (field.getOpcode() == GETFIELD) {
            before.add(new InsnNode(DUP)); before.add(new VarInsnNode(ASTORE, object));
            after.add(new InsnNode(type.getSize() == 2 ? DUP2 : DUP));
            after.add(new VarInsnNode(type.getOpcode(ISTORE), value));
        } else {
            before.add(new VarInsnNode(type.getOpcode(ISTORE), value)); before.add(new VarInsnNode(ASTORE, object));
            before.add(new VarInsnNode(ALOAD, object)); before.add(new VarInsnNode(type.getOpcode(ILOAD), value));
        }
        after.add(new VarInsnNode(ALOAD, object));
        after.add(new LdcInsnNode(field.name)); after.add(new VarInsnNode(type.getOpcode(ILOAD), value)); box(after, type);
        after.add(new MethodInsnNode(INVOKESTATIC, R, field.getOpcode() == GETFIELD ? "read" : "write",
                                    "(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/Object;)V", false));
        method.instructions.insertBefore(field, before); method.instructions.insert(field, after);
    }
    private static void arguments(InsnList code, MethodNode method) {
        Type[] args = Type.getArgumentTypes(method.desc);
        code.add(new LdcInsnNode(args.length)); code.add(new TypeInsnNode(ANEWARRAY, "java/lang/Object"));
        int slot = (method.access & ACC_STATIC) == 0 ? 1 : 0;
        for (int i = 0; i < args.length; i++) {
            code.add(new InsnNode(DUP)); code.add(new LdcInsnNode(i));
            code.add(new VarInsnNode(args[i].getOpcode(ILOAD), slot)); box(code, args[i]); code.add(new InsnNode(AASTORE));
            slot += args[i].getSize();
        }
    }
    private static void box(InsnList code, Type type) {
        String owner;
        switch (type.getSort()) {
            case Type.BOOLEAN: owner = "java/lang/Boolean"; break;
            case Type.BYTE: owner = "java/lang/Byte"; break;
            case Type.CHAR: owner = "java/lang/Character"; break;
            case Type.SHORT: owner = "java/lang/Short"; break;
            case Type.INT: owner = "java/lang/Integer"; break;
            case Type.FLOAT: owner = "java/lang/Float"; break;
            case Type.LONG: owner = "java/lang/Long"; break;
            case Type.DOUBLE: owner = "java/lang/Double"; break;
            default: return;
        }
        code.add(new MethodInsnNode(INVOKESTATIC, owner, "valueOf", "(" + type.getDescriptor() + ")L" + owner + ";", false));
    }
}
