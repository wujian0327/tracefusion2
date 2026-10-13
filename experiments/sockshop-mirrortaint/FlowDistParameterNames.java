import java.nio.file.*;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Restore original parameter names for Spring reflection after Soot emission.
 * Canonical class comparison removes only MethodParameters and proves all
 * instructions, frames, annotations and other class data remain unchanged.
 */
public final class FlowDistParameterNames {
    static ClassNode node(byte[] bytes) {
        ClassNode value=new ClassNode(Opcodes.ASM9);new ClassReader(bytes).accept(value,0);return value;
    }
    static byte[] canonical(byte[] bytes) {
        ClassNode value=node(bytes);for(MethodNode method:value.methods)method.parameters=null;
        ClassWriter writer=new ClassWriter(0);value.accept(writer);return writer.toByteArray();
    }
    static List<ParameterNode> names(MethodNode method) {
        Type[] types=Type.getArgumentTypes(method.desc);
        if(method.parameters!=null && method.parameters.size()==types.length) return method.parameters;
        if(method.localVariables==null)return null;
        List<ParameterNode> result=new ArrayList<>();int slot=(method.access&Opcodes.ACC_STATIC)!=0?0:1;
        for(Type type:types) {
            String name=null;int first=Integer.MAX_VALUE;
            for(LocalVariableNode local:method.localVariables)if(local.index==slot) {
                int offset=method.instructions.indexOf(local.start);
                if(offset<first){first=offset;name=local.name;}
                else if(offset==first && !Objects.equals(name,local.name))throw new IllegalStateException("Ambiguous source parameter");
            }
            if(name==null)return null;
            result.add(new ParameterNode(name,0));slot+=type.getSize();
        }
        return result;
    }
    public static void main(String[] args) throws Exception {
        Path originals=Paths.get(args[0]),input=Paths.get(args[1]),output=Paths.get(args[2]);
        int changed=0,parameters=0;
        List<Path> files=new ArrayList<>();try(java.util.stream.Stream<Path> stream=Files.walk(input)) {
            stream.filter(Files::isRegularFile).forEach(files::add);
        }
        for(Path file:files) {
            Path relative=input.relativize(file),target=output.resolve(relative);Files.createDirectories(target.getParent());
            byte[] bytes=Files.readAllBytes(file);Path original=originals.resolve(relative);
            if(file.toString().endsWith(".class") && Files.exists(original)) {
                ClassNode value=node(bytes),source=node(Files.readAllBytes(original));
                Map<String,MethodNode> methods=new HashMap<>();for(MethodNode method:source.methods)methods.put(method.name+method.desc,method);
                boolean modified=false;
                for(MethodNode method:value.methods) {
                    MethodNode prior=methods.get(method.name+method.desc);
                    if(prior==null || Type.getArgumentTypes(method.desc).length==0)continue;
                    List<ParameterNode> recovered=names(prior);
                    if(recovered==null) {
                        boolean handler=false;
                        if(prior.visibleAnnotations!=null)for(AnnotationNode a:prior.visibleAnnotations)
                            if(a.desc.startsWith("Lorg/springframework/web/bind/annotation/") &&
                               !a.desc.endsWith("ResponseStatus;"))handler=true;
                        if(handler)
                            throw new IllegalStateException("Controller source parameter name missing: "+method.name);
                        continue;
                    }
                    method.parameters=new ArrayList<>();
                    for(ParameterNode p:recovered)method.parameters.add(new ParameterNode(p.name,p.access));
                    parameters+=recovered.size();modified=true;
                }
                if(modified) {
                    ClassWriter writer=new ClassWriter(0);value.accept(writer);byte[] repaired=writer.toByteArray();
                    if(!Arrays.equals(canonical(bytes),canonical(repaired)))throw new IllegalStateException("Non-parameter class data changed: "+relative);
                    bytes=repaired;changed++;
                }
            }
            Files.write(target,bytes,StandardOpenOption.CREATE_NEW);
        }
        System.out.println("Restored original parameter names in "+changed+" classes; "+parameters+" parameters. Instructions/frames/annotations unchanged.");
    }
}
