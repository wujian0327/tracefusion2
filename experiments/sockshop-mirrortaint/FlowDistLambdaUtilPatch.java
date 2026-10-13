import java.nio.file.Files;
import java.nio.file.Paths;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Patch only the unsupported dynamic-invoke case; leave assertions enabled. */
public final class FlowDistLambdaUtilPatch {
    public static void main(String[] args) throws Exception {
        byte[] input = Files.readAllBytes(Paths.get(args[0]));
        ClassNode node = new ClassNode();
        new ClassReader(input).accept(node, 0);
        int patched = 0;
        for (MethodNode method : node.methods) {
            if (node.name.equals("dua/util/Util") && method.name.equals("objValuesMustEqual")
                && method.desc.equals("(Lsoot/Value;Lsoot/Value;Z)Z")) {
                LabelNode original = new LabelNode(), dynamic = new LabelNode(), different = new LabelNode();
                InsnList prefix = new InsnList();
                for (int slot = 0; slot < 2; slot++) {
                    prefix.add(new VarInsnNode(Opcodes.ALOAD, slot));
                    prefix.add(new TypeInsnNode(Opcodes.INSTANCEOF, "soot/jimple/DynamicInvokeExpr"));
                    prefix.add(new JumpInsnNode(Opcodes.IFNE, dynamic));
                }
                prefix.add(new JumpInsnNode(Opcodes.GOTO, original));
                prefix.add(dynamic);
                // Match the original allocation/Local rule: expression identity
                // only; distinct factory expressions are not definite aliases.
                prefix.add(new VarInsnNode(Opcodes.ALOAD, 0));
                prefix.add(new VarInsnNode(Opcodes.ALOAD, 1));
                prefix.add(new JumpInsnNode(Opcodes.IF_ACMPNE, different));
                prefix.add(new InsnNode(Opcodes.ICONST_1));
                prefix.add(new InsnNode(Opcodes.IRETURN));
                prefix.add(different);
                prefix.add(new InsnNode(Opcodes.ICONST_0));
                prefix.add(new InsnNode(Opcodes.IRETURN));
                prefix.add(original);
                method.instructions.insert(prefix);
                patched++;
                continue;
            }
            if (node.name.equals("dua/method/CFGDefUses$ObjVariable") && method.name.equals("mayAlias")
                && method.desc.equals("(Ldua/method/CFGDefUses$Variable;)Z")) {
                LabelNode original = new LabelNode(), unknown = new LabelNode();
                InsnList prefix = new InsnList();
                for (int slot = 0; slot < 2; slot++) {
                    prefix.add(new VarInsnNode(Opcodes.ALOAD, slot));
                    prefix.add(new MethodInsnNode(Opcodes.INVOKEVIRTUAL, "dua/method/CFGDefUses$Variable", "getValue", "()Lsoot/Value;", false));
                    prefix.add(new TypeInsnNode(Opcodes.INSTANCEOF, "soot/jimple/DynamicInvokeExpr"));
                    prefix.add(new JumpInsnNode(Opcodes.IFNE, unknown));
                }
                prefix.add(new JumpInsnNode(Opcodes.GOTO, original));
                prefix.add(unknown);
                // Unknown lambda points-to set: permit type-compatible aliases;
                // never replace unsupported values with an empty points-to set.
                prefix.add(new VarInsnNode(Opcodes.ALOAD, 0));
                prefix.add(new VarInsnNode(Opcodes.ALOAD, 1));
                prefix.add(new MethodInsnNode(Opcodes.INVOKEVIRTUAL, node.name, "mayEqual", "(Ldua/method/CFGDefUses$Variable;)Z", false));
                prefix.add(new InsnNode(Opcodes.IRETURN));
                prefix.add(original);
                method.instructions.insert(prefix);
                patched++;
                continue;
            }
            if (!method.name.equals("getAllPossibleRuntimeRefTypes") ||
                !method.desc.equals("(Lsoot/Value;)Ljava/util/List;")) continue;
            LabelNode original = new LabelNode();
            InsnList prefix = new InsnList();
            prefix.add(new VarInsnNode(Opcodes.ALOAD, 0));
            prefix.add(new TypeInsnNode(Opcodes.INSTANCEOF, "soot/jimple/DynamicInvokeExpr"));
            prefix.add(new JumpInsnNode(Opcodes.IFEQ, original));
            prefix.add(new VarInsnNode(Opcodes.ALOAD, 0));
            prefix.add(new MethodInsnNode(Opcodes.INVOKESTATIC, "dua/util/FlowDistDynamicTargets", "targets", "(Lsoot/Value;)Ljava/util/List;", false));
            prefix.add(new InsnNode(Opcodes.ARETURN));
            prefix.add(original);
            method.instructions.insert(prefix);
            patched++;
        }
        int expected = node.name.equals("dua/util/Util") ? 2 : 1;
        if (patched != expected || node.version != Opcodes.V1_5)
            throw new IllegalStateException("Unexpected original DUA Util layout/version");
        // Original class version 49 uses the verifier without stack-map frames.
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
        node.accept(writer);
        Files.write(Paths.get(args[1]), writer.toByteArray());
    }
}
