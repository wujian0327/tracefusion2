import java.nio.file.*;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Class-file input only. No application execution, fixtures or query answers. */
public final class QueryBytecodeModel implements Opcodes {
    public static String key(String owner,MethodNode method) {return owner+"."+method.name+method.desc;}
    public static List<Map<String,Object>> instructions(MethodNode method) {
        List<AbstractInsnNode> code=new ArrayList<>();for(AbstractInsnNode n:method.instructions.toArray())if(n.getOpcode()>=0)code.add(n);
        Map<AbstractInsnNode,Integer> indices=new IdentityHashMap<>();for(int i=0;i<code.size();i++)indices.put(code.get(i),i);
        List<Map<String,Object>> rows=new ArrayList<>();
        for(int i=0;i<code.size();i++) {
            AbstractInsnNode n=code.get(i);Map<String,Object> r=new LinkedHashMap<>();r.put("index",i);r.put("op",n.getOpcode());
            if(n instanceof VarInsnNode)r.put("var",((VarInsnNode)n).var);
            if(n instanceof IincInsnNode){r.put("var",((IincInsnNode)n).var);r.put("increment",((IincInsnNode)n).incr);}
            if(n instanceof IntInsnNode)r.put("operand",((IntInsnNode)n).operand);
            if(n instanceof LdcInsnNode){Object value=((LdcInsnNode)n).cst;r.put("constant",value instanceof Number||value instanceof String?value:String.valueOf(value));r.put("constant_type",value.getClass().getSimpleName());}
            if(n instanceof TypeInsnNode)r.put("type",((TypeInsnNode)n).desc);
            if(n instanceof FieldInsnNode){FieldInsnNode f=(FieldInsnNode)n;r.put("owner",f.owner);r.put("name",f.name);r.put("desc",f.desc);}
            if(n instanceof MethodInsnNode){MethodInsnNode c=(MethodInsnNode)n;r.put("owner",c.owner);r.put("name",c.name);r.put("desc",c.desc);}
            if(n instanceof JumpInsnNode){AbstractInsnNode target=((JumpInsnNode)n).label;while(target!=null&&target.getOpcode()<0)target=target.getNext();r.put("target",indices.get(target));}
            rows.add(r);
        }
        return rows;
    }
    public static void main(String[] args) throws Exception {
        Path root=Paths.get(args[0]);Map<String,Object> classes=new TreeMap<>(),methods=new TreeMap<>();
        List<Path> paths=new ArrayList<>();try(java.util.stream.Stream<Path> files=Files.walk(root)){files.filter(p->p.toString().endsWith(".class")).forEach(paths::add);}Collections.sort(paths);
        for(Path path:paths) {
            byte[] bytes=Files.readAllBytes(path);ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,ClassReader.SKIP_DEBUG|ClassReader.SKIP_FRAMES);
            Map<String,Object> cls=new LinkedHashMap<>();cls.put("access",c.access);cls.put("super",c.superName);List<Object> fields=new ArrayList<>();
            for(FieldNode f:c.fields){Map<String,Object> field=new LinkedHashMap<>();field.put("name",f.name);field.put("desc",f.desc);field.put("access",f.access);fields.add(field);}cls.put("fields",fields);
            cls.put("sha256",QueryObservationAgent.Recorder.hash(bytes));classes.put(c.name,cls);
            for(MethodNode m:c.methods){Map<String,Object> row=new LinkedHashMap<>();row.put("owner",c.name);row.put("name",m.name);row.put("desc",m.desc);row.put("access",m.access);
                row.put("try_catches",m.tryCatchBlocks.size());row.put("instructions",instructions(m));methods.put(key(c.name,m),row);}
        }
        Map<String,Object> model=new LinkedHashMap<>();model.put("classes",classes);model.put("methods",methods);
        new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(Paths.get(args[1]).toFile(),model);
    }
}
