package tracefusion.cost;

import java.io.InputStream;
import java.util.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;

/** Resolve verifier hierarchy from class resources, without defining a class
 * that is currently being transformed (recursive definition drops probes).
 * Array joins are rejected explicitly until supported, never approximated.
 */
final class CostFrameHierarchy {
    private final ClassLoader loader;
    private final Map<String,ClassReader> classes=new HashMap<>();
    CostFrameHierarchy(ClassLoader loader,byte[] current) {
        this.loader=loader;
        ClassReader reader=new ClassReader(current);classes.put(reader.getClassName(),reader);
    }
    private ClassReader read(String name) {
        ClassReader value=classes.get(name);
        if (value!=null) return value;
        try (InputStream stream=loader.getResourceAsStream(name+".class")) {
            if (stream==null) throw new IllegalStateException("Missing hierarchy resource: "+name);
            value=new ClassReader(stream);classes.put(name,value);return value;
        } catch (java.io.IOException error) {throw new IllegalStateException(error);}
    }
    private boolean assignable(String parent,String child,Set<String> seen) {
        if (parent.equals(child)||parent.equals("java/lang/Object"))return true;
        if (!seen.add(child))return false;
        ClassReader type=read(child);
        if (type.getSuperName()!=null && assignable(parent,type.getSuperName(),seen))return true;
        for(String itf:type.getInterfaces())if(assignable(parent,itf,seen))return true;
        return false;
    }
    String common(String first,String second) {
        if(first.equals(second))return first;
        if(first.startsWith("[")||second.startsWith("["))
            throw new IllegalStateException("Unsupported array frame join: "+first+" / "+second);
        if(assignable(first,second,new HashSet<String>()))return first;
        if(assignable(second,first,new HashSet<String>()))return second;
        if((read(first).getAccess()&Opcodes.ACC_INTERFACE)!=0 ||
           (read(second).getAccess()&Opcodes.ACC_INTERFACE)!=0)return "java/lang/Object";
        do {first=read(first).getSuperName();}
        while(first!=null && !assignable(first,second,new HashSet<String>()));
        if(first==null)throw new IllegalStateException("Missing common superclass");
        return first;
    }
}
