package tracefusion.cost;
import java.io.*;
import java.util.*;
import org.objectweb.asm.*;

/** A loader that rejects class definition proves frame computation is read-only. */
class CostHierarchyTest {
    private static byte[] type(String name,String parent,String... interfaces) {
        ClassWriter writer=new ClassWriter(0);writer.visit(Opcodes.V1_8,Opcodes.ACC_PUBLIC,name,null,parent,interfaces);writer.visitEnd();return writer.toByteArray();
    }
    public static void main(String[] args) {
        final Map<String,byte[]> resources=new HashMap<>();
        resources.put("fixture/Parent.class",type("fixture/Parent","java/lang/Object"));
        resources.put("fixture/Other.class",type("fixture/Other","fixture/Parent"));
        ClassLoader loader=new ClassLoader(CostHierarchyTest.class.getClassLoader()) {
            protected Class<?> loadClass(String name,boolean resolve) {throw new AssertionError("Frame hierarchy attempted class definition: "+name);}
            public InputStream getResourceAsStream(String name) {
                byte[] bytes=resources.get(name);
                return bytes==null?getParent().getResourceAsStream(name):new ByteArrayInputStream(bytes);
            }
        };
        CostFrameHierarchy hierarchy=new CostFrameHierarchy(loader,type("fixture/Owner","fixture/Parent"));
        if(!hierarchy.common("fixture/Owner","fixture/Other").equals("fixture/Parent"))throw new AssertionError();
        if(!hierarchy.common("fixture/Owner","fixture/Parent").equals("fixture/Parent"))throw new AssertionError();
        if(!hierarchy.common("fixture/Owner","fixture/Owner").equals("fixture/Owner"))throw new AssertionError();
        if(!hierarchy.common("fixture/Owner","java/lang/Object").equals("java/lang/Object"))throw new AssertionError();
        try {hierarchy.common("fixture/Owner","fixture/Missing");throw new AssertionError();}catch(IllegalStateException expected){}
        try {hierarchy.common("[I","[F");throw new AssertionError();}catch(IllegalStateException expected){}
        System.out.println("Passed 6 verifier hierarchy checks without class definition");
    }
}
