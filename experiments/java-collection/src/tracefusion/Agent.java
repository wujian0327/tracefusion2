package tracefusion;

import java.lang.instrument.*;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Explicitly bounded ASM frontend: static int/reference methods, int instance fields. */
public final class Agent implements Opcodes {
    private static final String R = "tracefusion/Recorder";
    private static Path output;
    private static Set<String> selected;
    private static Set<String> methods;
    private static Properties scope;
    private static String mode;

    public static void premain(String args, Instrumentation inst) throws Exception {
        output = Paths.get(System.getProperty("tracefusion.output", "java-trace"));
        Files.createDirectories(output);
        mode = System.getProperty("tracefusion.mode", "full");
        if (!mode.equals("full") && !mode.equals("sparse") && !mode.equals("boundary")) throw new IllegalArgumentException("capture_mode");
        String scopePath = System.getProperty("tracefusion.scope");
        if (scopePath != null) {
            byte[] scopeBytes = Files.readAllBytes(Paths.get(scopePath));
            System.setProperty("tracefusion.scopeHash", sha(scopeBytes));
            scope = new Properties();
            scope.load(new java.io.ByteArrayInputStream(scopeBytes));
            methods = new HashSet<>();
            for (int i = 0; i < Integer.parseInt(scope.getProperty("method.count")); i++)
                methods.add(scope.getProperty("method." + i));
            if (!methods.contains(scope.getProperty("entry"))) throw new IllegalArgumentException("scope_entry");
            Files.write(output.resolve("observation.properties"), scopeBytes, StandardOpenOption.CREATE_NEW);
        }
        if (mode.equals("sparse") && scope == null) throw new IllegalArgumentException("sparse_requires_scope");
        if (mode.equals("boundary") && (scope == null || !scope.getProperty("schema").equals("java-observation-scope-v2")))
            throw new IllegalArgumentException("boundary_requires_snapshots");
        selected = new HashSet<>(Arrays.asList(System.getProperty("tracefusion.classes",
            scope == null ? "demo.Subject" : scope.getProperty("classes")).replace('.', '/').split(",")));
        for (String c : selected) if (c.isEmpty() || c.startsWith("java/") || c.startsWith("tracefusion/"))
            throw new IllegalArgumentException("Explicit application classes required");
        Recorder.start(output.resolve("events.jsonl"), Integer.getInteger("tracefusion.maxEvents", 100000));
        inst.addTransformer(new ClassFileTransformer() {
            public byte[] transform(ClassLoader loader, String name, Class<?> prior,
                                    ProtectionDomain pd, byte[] bytes) {
                if (!selected.contains(name)) return null;
                try {
                    if (loader != ClassLoader.getSystemClassLoader() || prior != null)
                        throw new IllegalArgumentException("unsupported_classloader_or_redefinition");
                    return instrument(name, bytes);
                } catch (Exception e) {
                    Recorder.rejected(name, e.toString());
                    // JVM ignores transformer exceptions. Return original deliberately, but mark unknown.
                    return null;
                }
            }
        });
    }
    private static boolean type(Type t) {
        return t.getSort() == Type.INT || t.getSort() == Type.BOOLEAN
            || t.getSort() == Type.BYTE || t.getSort() == Type.SHORT
            || t.getSort() == Type.CHAR || t.getSort() == Type.OBJECT;
    }
    private static void audit(MethodNode m) {
        if ((m.access & (ACC_STATIC | ACC_NATIVE | ACC_ABSTRACT | ACC_SYNCHRONIZED)) != ACC_STATIC)
            throw new IllegalArgumentException("static_concrete_unsynchronized_methods_only:" + m.name);
        if (!m.tryCatchBlocks.isEmpty()) throw new IllegalArgumentException("exception_handlers:" + m.name);
        for (Type t : Type.getArgumentTypes(m.desc)) if (!type(t)) throw new IllegalArgumentException("argument_type");
        Type ret = Type.getReturnType(m.desc);
        if (ret.getSort() != Type.VOID && !type(ret)) throw new IllegalArgumentException("return_type");
        for (AbstractInsnNode n : m.instructions) {
            int op = n.getOpcode();
            if (op < 0) continue;
            boolean ok = op == NOP || op == ACONST_NULL || (op >= ICONST_M1 && op <= ICONST_5)
                || op == BIPUSH || op == SIPUSH || op == ILOAD || op == ALOAD || op == ISTORE
                || op == ASTORE || op == POP || op == DUP || op == SWAP || op == IADD || op == ISUB
                || op == IMUL || op == IDIV || op == IREM || op == INEG || op == ISHL || op == ISHR
                || op == IUSHR || op == IAND || op == IOR || op == IXOR || op == IINC
                || op == I2B || op == I2C || op == I2S || (op >= IFEQ && op <= GOTO)
                || op == IFNULL || op == IFNONNULL || op == IRETURN || op == ARETURN || op == RETURN;
            if (n instanceof LdcInsnNode) ok = ((LdcInsnNode)n).cst instanceof Integer;
            if (n instanceof FieldInsnNode) {
                FieldInsnNode f = (FieldInsnNode)n;
                ok = (op == GETFIELD || op == PUTFIELD) && f.desc.equals("I");
            }
            if (n instanceof MethodInsnNode) {
                MethodInsnNode c = (MethodInsnNode)n;
                ok = op == INVOKESTATIC && selected.contains(c.owner) && !c.name.startsWith("<");
                ok &= methods == null || methods.contains(c.owner + "." + c.name + c.desc);
                for (Type t : Type.getArgumentTypes(c.desc)) ok &= type(t);
                Type r = Type.getReturnType(c.desc);
                ok &= r.getSort() == Type.VOID || type(r);
            }
            if (!ok) throw new IllegalArgumentException("unsupported_opcode:" + op + ":" + m.name);
        }
    }
    private static String sha(byte[] b) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(b));
    }
    private static byte[] instrument(String name, byte[] bytes) throws Exception {
        ClassNode c = new ClassNode(ASM9);
        new ClassReader(bytes).accept(c, 0);
        if (scope != null && !sha(bytes).equals(scope.getProperty("sha256." + name)))
            throw new IllegalArgumentException("scope_class_hash:" + name);
        for (MethodNode m : c.methods) if (!m.name.equals("<init>")
                && (methods == null || methods.contains(name + "." + m.name + m.desc))) audit(m);
        // A symbolic owner must actually DECLARE this nonvolatile int field. Otherwise
        // inherited-field spellings could create two version counters for one location.
        Map<String, byte[]> fieldOwners = new TreeMap<>();
        for (MethodNode m : c.methods) if (!m.name.equals("<init>")
                && (methods == null || methods.contains(name + "." + m.name + m.desc))) {
            for (AbstractInsnNode n : m.instructions) if (n instanceof FieldInsnNode) {
                FieldInsnNode f = (FieldInsnNode)n;
                byte[] ownerBytes = fieldOwners.get(f.owner);
                if (ownerBytes == null) {
                    try (InputStream in = ClassLoader.getSystemResourceAsStream(f.owner + ".class")) {
                        if (in == null) throw new IllegalArgumentException("unavailable_field_owner:" + f.owner);
                        ownerBytes = in.readAllBytes();
                    }
                    fieldOwners.put(f.owner, ownerBytes);
                }
                ClassNode owner = new ClassNode(ASM9);
                new ClassReader(ownerBytes).accept(owner, ClassReader.SKIP_CODE);
                boolean declared = false;
                for (FieldNode field : owner.fields) if (field.name.equals(f.name) && field.desc.equals(f.desc)) {
                    declared = (field.access & (ACC_STATIC | ACC_VOLATILE)) == 0;
                }
                if (!declared) throw new IllegalArgumentException("inherited_or_volatile_field:" + f.owner + "." + f.name);
            }
        }
        List<String> plans = new ArrayList<>();
        if (scope != null && scope.getProperty("schema").equals("java-observation-scope-v2")) {
            for (String key : scope.stringPropertyNames()) if (key.startsWith("snapshot.sha256.")) {
                String owner = key.substring("snapshot.sha256.".length());
                byte[] data;
                try (InputStream in = ClassLoader.getSystemResourceAsStream(owner + ".class")) {
                    if (in == null) throw new IllegalArgumentException("missing_snapshot_owner");
                    data = in.readAllBytes();
                }
                if (!sha(data).equals(scope.getProperty(key))) throw new IllegalArgumentException("snapshot_owner_hash");
                fieldOwners.put(owner, data);
            }
        }
        for (MethodNode m : c.methods) {
            if (m.name.equals("<init>")) continue; // Constructors outside this experiment's boundary.
            String method = name + "." + m.name + m.desc;
            if (methods != null && !methods.contains(method)) continue;
            boolean boundary = mode.equals("boundary");
            boolean root = scope != null && method.equals(scope.getProperty("entry"));
            AbstractInsnNode[] original = m.instructions.toArray();
            IdentityHashMap<AbstractInsnNode, Integer> pcs = new IdentityHashMap<>();
            int pc = 0;
            for (AbstractInsnNode n : original) if (n.getOpcode() >= 0) pcs.put(n, pc++);
            Map<LabelNode, Integer> targets = new IdentityHashMap<>();
            for (AbstractInsnNode n : original) if (n instanceof LabelNode) {
                AbstractInsnNode next = n;
                while (next != null && next.getOpcode() < 0) next = next.getNext();
                targets.put((LabelNode)n, next == null ? pc : pcs.get(next));
            }
            for (AbstractInsnNode n : original) {
                int op = n.getOpcode();
                if (op < 0) continue;
                int index = pcs.get(n);
                String site = method + "@" + index;
                Object[] operands = new Object[0];
                if (n instanceof VarInsnNode) operands = new Object[]{((VarInsnNode)n).var};
                if (n instanceof IntInsnNode) operands = new Object[]{((IntInsnNode)n).operand};
                if (n instanceof LdcInsnNode) operands = new Object[]{((LdcInsnNode)n).cst};
                if (n instanceof IincInsnNode) operands = new Object[]{((IincInsnNode)n).var, ((IincInsnNode)n).incr};
                if (n instanceof JumpInsnNode) operands = new Object[]{targets.get(((JumpInsnNode)n).label)};
                if (n instanceof MethodInsnNode) {
                    MethodInsnNode x = (MethodInsnNode)n;
                    operands = new Object[]{x.owner + "." + x.name + x.desc};
                }
                if (n instanceof FieldInsnNode) {
                    FieldInsnNode x = (FieldInsnNode)n;
                    operands = new Object[]{x.owner + "." + x.name + ":" + x.desc};
                }
                plans.add("{\"site\":" + Recorder.json(site) + ",\"method\":" + Recorder.json(method)
                    + ",\"pc\":" + index + ",\"opcode\":" + op + ",\"operands\":" + Recorder.json(operands) + "}");
                if (mode.equals("full")) m.instructions.insertBefore(n, event("step", site, null));
                if (!boundary && n instanceof FieldInsnNode) instrumentField(m, (FieldInsnNode)n, site);
                if (!boundary && n instanceof JumpInsnNode && op != GOTO) {
                    JumpInsnNode jump = (JumpInsnNode)n;
                    LabelNode taken = new LabelNode(), after = new LabelNode();
                    InsnList replacement = new InsnList();
                    replacement.add(new JumpInsnNode(op, taken));
                    replacement.add(event("branch", site, 0));
                    replacement.add(new JumpInsnNode(GOTO, after));
                    replacement.add(taken);
                    replacement.add(event("branch", site, 1));
                    replacement.add(new JumpInsnNode(GOTO, jump.label));
                    replacement.add(after);
                    m.instructions.insertBefore(n, replacement);
                    m.instructions.remove(n);
                }
                if (!boundary && n instanceof MethodInsnNode) {
                    m.instructions.insertBefore(n, event("call", site, null));
                    m.instructions.insert(n, event("call_return", site, null));
                }
                if ((!boundary || root) && (op == IRETURN || op == ARETURN || op == RETURN)) {
                    InsnList e = new InsnList();
                    int v = m.maxLocals++;
                    if (op != RETURN) {
                        e.add(new InsnNode(DUP));
                        e.add(new VarInsnNode(op == ARETURN ? ASTORE : ISTORE, v));
                    }
                    e.add(new LdcInsnNode(boundary ? method : site));
                    arrayStart(e, op == RETURN ? 0 : 1);
                    if (op != RETURN) arrayValue(e, 0, op == ARETURN ? Type.getType(Object.class) : Type.INT_TYPE, v);
                    e.add(new MethodInsnNode(INVOKESTATIC, R, "exit", "(Ljava/lang/String;[Ljava/lang/Object;)V", false));
                    m.instructions.insertBefore(n, e);
                }
            }
            if (boundary && !root) continue;
            InsnList entry = new InsnList();
            entry.add(new LdcInsnNode(method));
            Type[] args = Type.getArgumentTypes(m.desc);
            arrayStart(entry, args.length);
            for (int i = 0; i < args.length; i++) arrayValue(entry, i, args[i], i);
            entry.add(new MethodInsnNode(INVOKESTATIC, R, "enter", "(Ljava/lang/String;[Ljava/lang/Object;)V", false));
            if (root && scope.getProperty("schema").equals("java-observation-scope-v2")) {
                for (int i = 0; i < Integer.parseInt(scope.getProperty("snapshot.count")); i++) {
                    int slot = Integer.parseInt(scope.getProperty("snapshot." + i + ".arg"));
                    String field = scope.getProperty("snapshot." + i + ".field");
                    int split = field.lastIndexOf('.');
                    entry.add(new LdcInsnNode(method)); entry.add(new LdcInsnNode(slot));
                    entry.add(new VarInsnNode(ALOAD, slot)); entry.add(new LdcInsnNode(field));
                    LabelNode nonnull = new LabelNode(), done = new LabelNode();
                    entry.add(new VarInsnNode(ALOAD, slot)); entry.add(new JumpInsnNode(IFNONNULL, nonnull));
                    entry.add(new InsnNode(ICONST_0)); entry.add(new JumpInsnNode(GOTO, done));
                    entry.add(nonnull); entry.add(new VarInsnNode(ALOAD, slot));
                    entry.add(new FieldInsnNode(GETFIELD, field.substring(0, split), field.substring(split + 1, field.length() - 2), "I"));
                    entry.add(done);
                    entry.add(new MethodInsnNode(INVOKESTATIC, R, "snapshot", "(Ljava/lang/String;ILjava/lang/Object;Ljava/lang/String;I)V", false));
                }
            }
            m.instructions.insert(entry);
        }
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
        c.accept(writer);
        byte[] rewritten = writer.toByteArray();
        String file = name.replace('/', '_');
        Files.write(output.resolve(file + ".original.class"), bytes, StandardOpenOption.CREATE_NEW);
        Files.write(output.resolve(file + ".instrumented.class"), rewritten, StandardOpenOption.CREATE_NEW);
        Files.write(output.resolve(file + ".plan.jsonl"), plans, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        for (Map.Entry<String, byte[]> fieldOwner : fieldOwners.entrySet()) {
            Path path = output.resolve("field_" + fieldOwner.getKey().replace('/', '_') + ".class");
            if (Files.exists(path)) {
                if (!Arrays.equals(Files.readAllBytes(path), fieldOwner.getValue()))
                    throw new IllegalArgumentException("changed_field_owner");
            } else Files.write(path, fieldOwner.getValue(), StandardOpenOption.CREATE_NEW);
        }
        Recorder.transformed(name, sha(bytes));
        return rewritten;
    }
    private static void arrayStart(InsnList a, int count) {
        a.add(new LdcInsnNode(count)); a.add(new TypeInsnNode(ANEWARRAY, "java/lang/Object"));
    }
    private static void arrayValue(InsnList a, int index, Type type, int local) {
        a.add(new InsnNode(DUP)); a.add(new LdcInsnNode(index));
        if (type.getSort() == Type.OBJECT) {
            a.add(new VarInsnNode(ALOAD, local));
            a.add(new MethodInsnNode(INVOKESTATIC, R, "ref", "(Ljava/lang/Object;)Ljava/lang/String;", false));
        } else {
            a.add(new VarInsnNode(ILOAD, local));
            a.add(new MethodInsnNode(INVOKESTATIC, "java/lang/Integer", "valueOf", "(I)Ljava/lang/Integer;", false));
        }
        a.add(new InsnNode(AASTORE));
    }
    private static InsnList event(String kind, String site, Integer value) {
        InsnList a = new InsnList();
        a.add(new LdcInsnNode(kind)); a.add(new LdcInsnNode(site));
        arrayStart(a, value == null ? 0 : 1);
        if (value != null) {
            a.add(new InsnNode(DUP)); a.add(new InsnNode(ICONST_0)); a.add(new LdcInsnNode(value));
            a.add(new MethodInsnNode(INVOKESTATIC, "java/lang/Integer", "valueOf", "(I)Ljava/lang/Integer;", false));
            a.add(new InsnNode(AASTORE));
        }
        a.add(new MethodInsnNode(INVOKESTATIC, R, "event", "(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V", false));
        return a;
    }
    private static void instrumentField(MethodNode m, FieldInsnNode n, String site) {
        boolean write = n.getOpcode() == PUTFIELD;
        int obj = m.maxLocals++, val = m.maxLocals++;
        InsnList before = new InsnList();
        if (write) before.add(new VarInsnNode(ISTORE, val));
        before.add(new InsnNode(DUP)); before.add(new VarInsnNode(ASTORE, obj));
        if (write) before.add(new VarInsnNode(ILOAD, val));
        m.instructions.insertBefore(n, before);
        InsnList after = new InsnList();
        if (!write) { after.add(new InsnNode(DUP)); after.add(new VarInsnNode(ISTORE, val)); }
        after.add(new LdcInsnNode(write ? "write" : "read")); after.add(new LdcInsnNode(site));
        after.add(new VarInsnNode(ALOAD, obj)); after.add(new VarInsnNode(ILOAD, val));
        after.add(new LdcInsnNode(n.owner + "." + n.name + ":" + n.desc));
        after.add(new MethodInsnNode(INVOKESTATIC, R, "field", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;ILjava/lang/String;)V", false));
        m.instructions.insert(n, after);
    }
}
