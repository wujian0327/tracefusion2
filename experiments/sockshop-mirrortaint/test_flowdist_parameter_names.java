import java.lang.reflect.Method;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Wide JVM slots, missing debug data, metadata-only repair and reflection. */
class FlowDistParameterNameTest {
    static void check(boolean condition) {if(!condition)throw new AssertionError();}
    static class Loader extends ClassLoader {Class<?> define(byte[] bytes){return defineClass(null,bytes,0,bytes.length);}}
    static byte[] bytes(ClassNode value) {ClassWriter writer=new ClassWriter(0);value.accept(writer);return writer.toByteArray();}
    public static void main(String[] args) throws Exception {
        ClassNode clazz=new ClassNode(Opcodes.ASM9);clazz.version=Opcodes.V1_8;clazz.access=Opcodes.ACC_PUBLIC;
        clazz.name="ParameterFixture";clazz.superName="java/lang/Object";
        MethodNode source=new MethodNode(Opcodes.ACC_PUBLIC,"handler","(JLjava/lang/String;)V",null,null);
        LabelNode start=new LabelNode(),end=new LabelNode();source.instructions.add(start);
        source.instructions.add(new InsnNode(Opcodes.RETURN));source.instructions.add(end);
        source.maxLocals=4;source.maxStack=0;source.localVariables=new ArrayList<>();
        source.localVariables.add(new LocalVariableNode("number","J",null,start,end,1));
        source.localVariables.add(new LocalVariableNode("customerId","Ljava/lang/String;",null,start,end,3));
        clazz.methods.add(source);
        List<ParameterNode> names=FlowDistParameterNames.names(source);
        check(names.size()==2 && names.get(0).name.equals("number") && names.get(1).name.equals("customerId"));
        byte[] before=bytes(clazz);
        Method original=new Loader().define(before).getMethod("handler",long.class,String.class);
        check(!original.getParameters()[1].isNamePresent());
        source.parameters=names;byte[] repaired=bytes(clazz);
        check(Arrays.equals(FlowDistParameterNames.canonical(before),FlowDistParameterNames.canonical(repaired)));
        Method reflected=new Loader().define(repaired).getMethod("handler",long.class,String.class);
        check(reflected.getParameters()[1].isNamePresent() && reflected.getParameters()[1].getName().equals("customerId"));
        MethodNode absent=new MethodNode(Opcodes.ACC_PUBLIC|Opcodes.ACC_ABSTRACT,"missing","(Ljava/lang/String;)V",null,null);
        check(FlowDistParameterNames.names(absent)==null);
        System.out.println("5 parameter-name regression checks passed");
    }
}
