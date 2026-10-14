import java.lang.instrument.*;
import java.security.ProtectionDomain;
import edu.columbia.cs.psl.phosphor.org.objectweb.asm.*;

/** Statement sources/sinks only. All propagation is performed by Phosphor.
 * Getter sources preserve the actual value, tagging only at the declared read.
 */
public final class PhosphorStatementAgent implements ClassFileTransformer, Opcodes {
    private static final String REC = "PhosphorStatementAgent$Recorder";
    public static void premain(String args, Instrumentation inst) throws Exception {
        Class.forName("PhosphorStatementAgent$1");
        Class.forName("PhosphorStatementAgent$1$1");
        inst.addTransformer(new PhosphorStatementAgent());
        System.out.println("PHOSPHOR_STATEMENT registered");
    }
    public edu.columbia.cs.psl.phosphor.struct.LazyByteArrayObjTags transform$$PHOSPHORTAGGED(
            ClassLoader loader, String name, Class<?> prior, ProtectionDomain domain,
            edu.columbia.cs.psl.phosphor.struct.LazyByteArrayObjTags tags, byte[] bytes) {
        return new edu.columbia.cs.psl.phosphor.struct.LazyByteArrayObjTags(transform(loader,name,prior,domain,bytes));
    }
    public byte[] transform(ClassLoader loader, final String owner, Class<?> prior, ProtectionDomain domain, byte[] bytes) {
        if(owner==null || !owner.startsWith("works/weave/socks/")) return null;
        try {
            ClassReader reader=new ClassReader(bytes);
            ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);
            reader.accept(new ClassVisitor(ASM5,writer) {
                public MethodVisitor visitMethod(int access,final String method,String desc,String sig,String[] exceptions) {
                    MethodVisitor next=super.visitMethod(access,method,desc,sig,exceptions);
                    final boolean shipping=owner.endsWith("/shipping/controllers/ShippingController") && method.equals("postShipping");
                    final boolean cartGet=owner.endsWith("/cart/controllers/CartsController") && method.equals("get");
                    return new MethodVisitor(ASM5,next) {
                        private void call(String name,String desc) {super.visitMethodInsn(INVOKESTATIC,REC,name,desc,false);}
                        public void visitCode() {
                            super.visitCode();
                            if(shipping) {super.visitVarInsn(ALOAD,1);super.visitLdcInsn("shipping.param");call("sourceGraph","(Ljava/lang/Object;Ljava/lang/String;)V");}
                        }
                        public void visitFieldInsn(int opcode,String declaring,String field,String desc) {
                            if(opcode==PUTFIELD && method.equals("<init>") && declaring.equals("works/weave/socks/orders/entities/CustomerOrder") && field.equals("total") && desc.equals("F")) {
                                super.visitInsn(DUP);super.visitLdcInsn("orders.total");call("sinkFloat","(FLjava/lang/String;)V");
                            }
                            super.visitFieldInsn(opcode,declaring,field,desc);
                            if(opcode!=GETFIELD || !owner.startsWith("works/weave/socks/orders/entities/") || !method.startsWith("get")) return;
                            String entity=owner.substring(owner.lastIndexOf('/')+1);
                            boolean selected=(entity.equals("Item") && (field.equals("quantity")||field.equals("unitPrice")||field.equals("itemId")))
                                ||(entity.equals("Customer")&&field.equals("firstName"))||(entity.equals("Address")&&field.equals("street"))
                                ||(entity.equals("Card")&&(field.equals("longNum")||field.equals("ccv")));
                            if(!selected) return;
                            String site="orders."+entity+"."+field;
                            super.visitLdcInsn(site);
                            if(desc.equals("I")) call("sourceInt","(ILjava/lang/String;)I");
                            else if(desc.equals("F")) call("sourceFloat","(FLjava/lang/String;)F");
                            else if(desc.equals("Ljava/lang/String;")) call("sourceString","(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;");
                            else throw new IllegalStateException("Unsupported declared source type "+desc);
                        }
                        public void visitMethodInsn(int opcode,String declaring,String name,String desc,boolean itf) {
                            boolean dao=declaring.equals("works/weave/socks/cart/cart/CartDAO");
                            if(dao && (name.equals("delete")||name.equals("save"))) {
                                boolean destroy=owner.endsWith("/cart/cart/CartResource")&&method.startsWith("lambda$destroy$");
                                boolean merge=owner.endsWith("/cart/cart/CartContentsResource")&&method.startsWith("lambda$add$");
                                if((name.equals("delete")&&destroy)||(name.equals("save")&&merge)) {
                                    super.visitInsn(DUP);super.visitLdcInsn(destroy?"carts.delete":"carts.mergeCarts");call("sinkGraph","(Ljava/lang/Object;Ljava/lang/String;)V");
                                }
                            }
                            super.visitMethodInsn(opcode,declaring,name,desc,itf);
                            if(dao && name.equals("findByCustomerId") && owner.endsWith("/cart/cart/CartResource") && method.equals("value")) {
                                super.visitInsn(DUP);super.visitLdcInsn("carts.dao");call("sourceGraph","(Ljava/lang/Object;Ljava/lang/String;)V");
                            }
                        }
                        public void visitInsn(int opcode) {
                            if(opcode==ARETURN && (shipping||cartGet)) {
                                super.visitInsn(DUP);super.visitLdcInsn(shipping?"shipping.return":"carts.get");call("sinkGraph","(Ljava/lang/Object;Ljava/lang/String;)V");
                            }
                            super.visitInsn(opcode);
                        }
                    };
                }
            },0);
            return writer.toByteArray();
        } catch(Throwable error) {
            System.err.println("PHOSPHOR_STATEMENT_ERROR transform "+owner+" "+error);
            throw new IllegalStateException(error);
        }
    }
    public static final class Recorder {
        private static final java.util.concurrent.atomic.AtomicLong SEQ=new java.util.concurrent.atomic.AtomicLong();
        private static java.util.Set<String> labels(edu.columbia.cs.psl.phosphor.runtime.Taint<?> tag) {
            java.util.Set<String> result=new java.util.TreeSet<String>();
            if(tag==null) return result;
            try {
                try {
                    for(Object value:(Object[])tag.getClass().getMethod("getLabels").invoke(tag))
                        if(value!=null)result.add(value.toString());
                } catch(NoSuchMethodException legacy) {
                    Object label=tag.getClass().getMethod("getLabel").invoke(tag);
                    if(label!=null)result.add(label.toString());
                    Object deps=tag.getClass().getMethod("getDependencies").invoke(tag);
                    if(deps!=null) {
                        Object node=deps.getClass().getMethod("getFirst").invoke(deps);
                        while(node!=null) {
                            Object value=node.getClass().getField("entry").get(node);
                            if(value!=null)result.add(value.toString());
                            node=node.getClass().getField("next").get(node);
                        }
                    }
                }
            } catch(Exception error) {throw new IllegalStateException("Native label API unavailable",error);}
            return result;
        }
        private static String quote(String s) {return "\""+s.replace("\\","\\\\").replace("\"","\\\"")+"\"";}
        private static synchronized void emit(String kind,String site,java.util.Set<String> labels) {
            StringBuilder text=new StringBuilder();
            for(String label:labels) {if(text.length()>0)text.append(',');text.append(quote(label));}
            System.out.println("PHOSPHOR_STATEMENT_EVENT {\"seq\":"+SEQ.incrementAndGet()+",\"kind\":"+quote(kind)+",\"site\":"+quote(site)+",\"labels\":["+text+"]}");
        }
        public static int sourceInt(int value,String site) {
            int tagged=edu.columbia.cs.psl.phosphor.runtime.MultiTainter.taintedInt(value,site);
            emit("source",site,labels(edu.columbia.cs.psl.phosphor.runtime.MultiTainter.getTaint(tagged)));return tagged;
        }
        public static float sourceFloat(float value,String site) {
            float tagged=edu.columbia.cs.psl.phosphor.runtime.MultiTainter.taintedFloat(value,site);
            emit("source",site,labels(edu.columbia.cs.psl.phosphor.runtime.MultiTainter.getTaint(tagged)));return tagged;
        }
        public static String sourceString(String value,String site) {
            edu.columbia.cs.psl.phosphor.runtime.MultiTainter.taintedObject(value,new edu.columbia.cs.psl.phosphor.runtime.Taint<String>(site));
            emit("source",site,labels(edu.columbia.cs.psl.phosphor.runtime.MultiTainter.getTaint(value)));return value;
        }
        public static void sinkFloat(float value,String site) {emit("sink",site,labels(edu.columbia.cs.psl.phosphor.runtime.MultiTainter.getTaint(value)));}
        private static void graph(Object root,String source,java.util.Set<String> tags,java.util.IdentityHashMap<Object,Boolean> seen) throws Exception {
            if(root==null || seen.put(root,Boolean.TRUE)!=null)return;
            if(seen.size()>10000)throw new IllegalStateException("Graph observation limit");
            if(source!=null)edu.columbia.cs.psl.phosphor.runtime.MultiTainter.taintedObject(root,new edu.columbia.cs.psl.phosphor.runtime.Taint<String>(source));
            tags.addAll(labels(edu.columbia.cs.psl.phosphor.runtime.MultiTainter.getTaint(root)));
            if(root instanceof java.util.Collection) {for(Object child:(java.util.Collection<?>)root)graph(child,source,tags,seen);return;}
            if(!root.getClass().getName().startsWith("works.weave.socks."))return;
            for(Class<?> c=root.getClass();c!=null&&c!=Object.class;c=c.getSuperclass())for(java.lang.reflect.Field field:c.getDeclaredFields()) {
                if(java.lang.reflect.Modifier.isStatic(field.getModifiers())||field.isSynthetic()||field.getName().contains("PHOSPHOR")||field.getType().isPrimitive())continue;
                field.setAccessible(true);graph(field.get(root),source,tags,seen);
            }
        }
        public static void sourceGraph(Object value,String site) {
            try {java.util.Set<String> tags=new java.util.TreeSet<String>();graph(value,site,tags,new java.util.IdentityHashMap<Object,Boolean>());emit("source",site,tags);}
            catch(Throwable error) {System.err.println("PHOSPHOR_STATEMENT_ERROR source "+error);throw new IllegalStateException(error);}
        }
        public static void sinkGraph(Object value,String site) {
            try {java.util.Set<String> tags=new java.util.TreeSet<String>();graph(value,null,tags,new java.util.IdentityHashMap<Object,Boolean>());emit("sink",site,tags);}
            catch(Throwable error) {System.err.println("PHOSPHOR_STATEMENT_ERROR sink "+error);throw new IllegalStateException(error);}
        }
    }
}
