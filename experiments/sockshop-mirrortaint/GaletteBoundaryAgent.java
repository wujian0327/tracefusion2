import java.lang.instrument.*;
import java.security.ProtectionDomain;
import java.util.*;
import java.nio.file.*;
import edu.neu.ccs.prl.galette.internal.transform.org.objectweb.asm.*;
import edu.neu.ccs.prl.galette.internal.transform.org.objectweb.asm.tree.*;

/** Configuration-only boundary observer. Runs before Galette's transformer. */
public final class GaletteBoundaryAgent implements ClassFileTransformer, Opcodes {
    static Properties config=new Properties(); static Set<String> sources=new HashSet<>();
    public static void premain(String args,Instrumentation instrumentation)throws Exception {
        try(java.io.InputStream in=Files.newInputStream(Paths.get(System.getProperty("galette.boundary.config")))){config.load(in);}
        sources.addAll(Arrays.asList(config.getProperty("sources").split("\\|")));
        instrumentation.addTransformer(new GaletteBoundaryAgent());
    }
    public static void premain(String args,Instrumentation instrumentation,edu.neu.ccs.prl.galette.internal.runtime.TagFrame frame)throws Exception{premain(args,instrumentation);}
    static InsnList textCall(String method,String text){InsnList h=new InsnList();h.add(new LdcInsnNode(text));h.add(new MethodInsnNode(INVOKESTATIC,"GaletteBoundaryHooks",method,"(Ljava/lang/String;)V",false));return h;}
    public byte[] transform(ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes) {
        if(owner==null||!owner.startsWith(config.getProperty("prefix")))return null;
        try {
            ClassNode c=new ClassNode(ASM9);new ClassReader(bytes).accept(c,0);
            for(MethodNode m:c.methods) {
                if((m.access&(ACC_ABSTRACT|ACC_NATIVE))!=0)continue;
                String key=owner+"."+m.name+m.desc;AbstractInsnNode[] code=m.instructions.toArray();
                m.instructions.insert(textCall("enter",key));int pc=0;boolean initialized=!m.name.equals("<init>");
                for(AbstractInsnNode n:code) {
                    if(n.getOpcode()<0)continue;
                    int originalPC=pc++;
                    if(n instanceof MethodInsnNode) {
                        MethodInsnNode call=(MethodInsnNode)n;String callee=call.owner+"."+call.name+call.desc;
                        if(call.getOpcode()==INVOKESPECIAL&&call.name.equals("<init>"))initialized=true;
                        if(sources.contains(callee)) {
                            if(Type.getReturnType(call.desc).getSort()!=Type.OBJECT)throw new IllegalArgumentException("Source must return an object");
                            InsnList before=new InsnList();before.add(new LdcInsnNode(key));before.add(new LdcInsnNode(originalPC));before.add(new LdcInsnNode(callee));
                            before.add(new MethodInsnNode(INVOKESTATIC,"GaletteBoundaryHooks","sourceEnter","(Ljava/lang/String;ILjava/lang/String;)V",false));
                            LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode(),done=new LabelNode();before.add(start);
                            InsnList after=new InsnList();after.add(end);after.add(new InsnNode(DUP));after.add(new LdcInsnNode(callee));after.add(new MethodInsnNode(INVOKESTATIC,"GaletteBoundaryHooks","sourceExit","(Ljava/lang/Object;Ljava/lang/String;)V",false));after.add(new JumpInsnNode(GOTO,done));
                            after.add(handler);int error=m.maxLocals++;after.add(new VarInsnNode(ASTORE,error));after.add(new VarInsnNode(ALOAD,error));after.add(new LdcInsnNode(callee));after.add(new MethodInsnNode(INVOKESTATIC,"GaletteBoundaryHooks","sourceThrow","(Ljava/lang/Throwable;Ljava/lang/String;)V",false));after.add(new VarInsnNode(ALOAD,error));after.add(new InsnNode(ATHROW));after.add(done);
                            m.instructions.insertBefore(n,before);m.instructions.insert(n,after);m.tryCatchBlocks.add(0,new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));
                        }
                    }
                    if(n instanceof FieldInsnNode&&n.getOpcode()==PUTFIELD&&initialized) {
                        FieldInsnNode f=(FieldInsnNode)n;Type type=Type.getType(f.desc);int slot=m.maxLocals;m.maxLocals+=type.getSize();
                        InsnList before=new InsnList();before.add(new VarInsnNode(type.getOpcode(ISTORE),slot));before.add(new InsnNode(DUP));before.add(new VarInsnNode(type.getOpcode(ILOAD),slot));m.instructions.insertBefore(n,before);
                        InsnList after=new InsnList();after.add(new LdcInsnNode(f.owner+"."+f.name));after.add(new MethodInsnNode(INVOKESTATIC,"GaletteBoundaryHooks","written","(Ljava/lang/Object;Ljava/lang/String;)V",false));m.instructions.insert(n,after);
                    }
                    if(n.getOpcode()>=IRETURN&&n.getOpcode()<=RETURN) {
                        InsnList end=new InsnList();if(key.equals(config.getProperty("entry"))){if(n.getOpcode()!=ARETURN)throw new IllegalArgumentException("Root must return object");end.add(new InsnNode(DUP));end.add(new MethodInsnNode(INVOKESTATIC,"GaletteBoundaryHooks","target","(Ljava/lang/Object;)V",false));}
                        end.add(textCall("exit",key));m.instructions.insertBefore(n,end);
                    }
                }
            }
            ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){try{Class<?> x=Class.forName(a.replace('/','.'),false,loader),y=Class.forName(b.replace('/','.'),false,loader);if(x.isAssignableFrom(y))return a;if(y.isAssignableFrom(x))return b;if(x.isInterface()||y.isInterface())return "java/lang/Object";do{x=x.getSuperclass();}while(!x.isAssignableFrom(y));return x.getName().replace('.','/');}catch(Exception e){throw new IllegalStateException(e);}}};c.accept(writer);
            byte[] digest=java.security.MessageDigest.getInstance("SHA-256").digest(bytes);StringBuilder hex=new StringBuilder();for(byte b:digest)hex.append(String.format("%02x",b&255));
            Files.write(Paths.get(System.getProperty("galette.boundary.events")+".coverage"),(owner+" "+hex+"\n").getBytes("UTF-8"),StandardOpenOption.CREATE,StandardOpenOption.APPEND);
            return writer.toByteArray();
        }catch(Throwable error){try{Files.write(Paths.get(System.getProperty("galette.boundary.events")+".invalid"),(owner+":"+error.getClass().getName()+":"+error.getMessage()+"\n").getBytes("UTF-8"),StandardOpenOption.CREATE,StandardOpenOption.APPEND);}catch(Exception ignored){}return null;}
    }
    // The instrumented JCL invokes this signature. Match the official Agent's
    // TransformerWrapper bridge; otherwise the inherited default is a no-op.
    public byte[] transform(ClassLoader loader,String owner,Class<?> prior,ProtectionDomain domain,byte[] bytes,edu.neu.ccs.prl.galette.internal.runtime.TagFrame frame){return transform(loader,owner,prior,domain,bytes);}
}
