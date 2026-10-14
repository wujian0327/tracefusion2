import java.nio.file.*;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Emit original returnInto at actual normal returns from calls in monitored
 * methods. Excluded framework calls can invoke callbacks or asynchronous work;
 * the original selected-callsite instrumenter omits their caller resumption.
 * No return is recorded on exceptional exits, no synthetic enter is emitted.
 */
public final class FlowDistResumeCalls {
    static byte[] canonical(ClassNode node) {ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_MAXS);node.accept(writer);return writer.toByteArray();}
    public static void main(String[] args) throws Exception {
        byte[] input=Files.readAllBytes(Paths.get(args[0]));ClassNode node=new ClassNode(Opcodes.ASM9);
        new ClassReader(input).accept(node,0);byte[] before=canonical(node);
        List<AbstractInsnNode[]> added=new ArrayList<>();List<MethodNode> methods=new ArrayList<>();
        for(MethodNode method:node.methods) {
            boolean active=false;
            StringJoiner parameters=new StringJoiner(",");for(Type type:Type.getArgumentTypes(method.desc))parameters.add(type.getClassName());
            String caller="<"+node.name.replace('/','.')+": "+Type.getReturnType(method.desc).getClassName()+" "+method.name+"("+parameters+")>";
            for(AbstractInsnNode insn:method.instructions.toArray()) {
                if(!(insn instanceof MethodInsnNode))continue;MethodInsnNode call=(MethodInsnNode)insn;
                if(call.owner.equals("disttaint/OTMonitor")&&call.name.equals("enter")) {active=true;continue;}
                if(!active||call.owner.startsWith("disttaint/")||call.owner.startsWith("profile/"))continue;
                InsnList probe=new InsnList();
                AbstractInsnNode[] instructions={new LdcInsnNode(caller),new LdcInsnNode("normal return: "+call.owner+"."+call.name+call.desc),
                    new MethodInsnNode(Opcodes.INVOKESTATIC,"disttaint/OTMonitor","returnInto","(Ljava/lang/String;Ljava/lang/String;)V",false)};
                for(AbstractInsnNode item:instructions)probe.add(item);
                method.instructions.insert(call,probe);added.add(instructions);methods.add(method);
            }
        }
        byte[] result=canonical(node);
        for(int i=0;i<added.size();i++)for(AbstractInsnNode instruction:added.get(i))methods.get(i).instructions.remove(instruction);
        if(!Arrays.equals(before,canonical(node)))throw new IllegalStateException("Call-return probes changed other class data");
        Path output=Paths.get(args[1]);Files.createDirectories(output.getParent());Files.write(output,result);
        System.out.println(node.name+" normal-return probes="+added.size()+" inverse-canonical-comparison=passed");
    }
}
