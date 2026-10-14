import java.nio.file.*;
import java.util.*;
import java.util.jar.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Repair one trace-ID/graph-ID lookup; never add edges or change traversal. */
public final class FlowDistFieldIndexPatch {
    static final String OWNER="disttaint/DynTransferGraph";
    static final String DESC="(Ldisttaint/DynTransferGraph;Ljava/lang/String;ZLjava/util/HashMap;)I";
    static byte[] encode(ClassNode node) {
        ClassWriter writer=new ClassWriter(0);node.accept(writer);return writer.toByteArray();
    }
    public static void main(String[] args) throws Exception {
        byte[] original;
        try(JarFile jar=new JarFile(args[0])) {
            try(java.io.InputStream in=jar.getInputStream(jar.getJarEntry(OWNER+".class"))) {
                java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();byte[] buffer=new byte[8192];int n;
                while((n=in.read(buffer))!=-1)bytes.write(buffer,0,n);original=bytes.toByteArray();
            }
        }
        ClassNode node=new ClassNode(Opcodes.ASM9);new ClassReader(original).accept(node,0);
        byte[] canonical=encode(node);int changed=0;MethodNode target=null;
        FieldInsnNode oldField=null,newField=null;VarInsnNode receiver=null;MethodInsnNode call=null;
        for(MethodNode method:node.methods)if(method.name.equals("buildGraph")&&method.desc.equals(DESC)) {
            for(AbstractInsnNode insn:method.instructions.toArray()) {
                if(!(insn instanceof FieldInsnNode))continue;FieldInsnNode field=(FieldInsnNode)insn;
                if(field.getOpcode()!=Opcodes.GETSTATIC||!field.owner.equals(OWNER)||!field.name.equals("EAmethod2idx"))continue;
                AbstractInsnNode key=field.getNext(),next=key==null?null:key.getNext();
                if(!(key instanceof VarInsnNode)||!(next instanceof MethodInsnNode))continue;
                MethodInsnNode invocation=(MethodInsnNode)next;
                if(!invocation.name.equals("get")||!invocation.owner.equals("java/util/LinkedHashMap"))continue;
                target=method;oldField=field;call=invocation;receiver=new VarInsnNode(Opcodes.ALOAD,0);
                newField=new FieldInsnNode(Opcodes.GETFIELD,OWNER,"method2idx","Ljava/util/Map;");
                method.instructions.insertBefore(field,receiver);method.instructions.set(field,newField);
                call.setOpcode(Opcodes.INVOKEINTERFACE);call.owner="java/util/Map";call.itf=true;changed++;
            }
        }
        if(changed!=1)throw new IllegalStateException("Expected exactly one trace-to-graph index lookup, found "+changed);
        byte[] repaired=encode(node);
        target.instructions.remove(receiver);target.instructions.set(newField,oldField);
        call.setOpcode(Opcodes.INVOKEVIRTUAL);call.owner="java/util/LinkedHashMap";call.itf=false;
        if(!Arrays.equals(canonical,encode(node)))throw new IllegalStateException("Other class data changed");
        Path output=Paths.get(args[1]).resolve(OWNER+".class");Files.createDirectories(output.getParent());Files.write(output,repaired);
        System.out.println("One method-ID namespace lookup repaired; inverse patch restores canonical original class byte-for-byte.");
    }
}
