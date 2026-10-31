import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Observes original values at actual default SQL entry points. */
public final class SqlResultLocalityInstrumentation implements Opcodes {
 static final String H="SqlResultLocalityHooks";
 static void call(InsnList x,String name,String desc){x.add(new MethodInsnNode(INVOKESTATIC,H,name,desc,false));}
 static void observeReceiver(MethodNode method,MethodInsnNode invoke,boolean callback,String site){
  Type[] types=Type.getArgumentTypes(invoke.desc);int[] slots=new int[types.length];InsnList before=new InsnList();
  for(int n=types.length-1;n>=0;n--){slots[n]=method.maxLocals;method.maxLocals+=types[n].getSize();before.add(new VarInsnNode(types[n].getOpcode(ISTORE),slots[n]));}
  int receiver=method.maxLocals++;before.add(new VarInsnNode(ASTORE,receiver));before.add(new VarInsnNode(ALOAD,receiver));
  if(callback)before.add(new LdcInsnNode(site));call(before,callback?"callbackBegin":"handler",callback?"(Ljava/lang/Object;Ljava/lang/String;)V":"(Ljava/lang/Object;)V");
  before.add(new VarInsnNode(ALOAD,receiver));for(int n=0;n<types.length;n++)before.add(new VarInsnNode(types[n].getOpcode(ILOAD),slots[n]));method.instructions.insertBefore(invoke,before);
  if(callback){InsnList after=new InsnList();call(after,"callbackEnd","()V");method.instructions.insert(invoke,after);}
 }
 static byte[] transform(final ClassLoader loader,String owner,byte[] original,byte[] previous)throws Exception{
  ClassNode c=new ClassNode(ASM9);new ClassReader(previous).accept(c,ClassReader.EXPAND_FRAMES);boolean changed=false;List sites=new ArrayList();
  for(MethodNode m:c.methods){if(m.name.startsWith("$tf2$")||(m.access&(ACC_ABSTRACT|ACC_NATIVE))!=0)continue;
   if(owner.equals("org/apache/ibatis/reflection/MetaObject")&&m.name.equals("forObject")){InsnList x=new InsnList();for(int n:new int[]{1,2,3})x.add(new VarInsnNode(ALOAD,n));call(x,"meta","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V");m.instructions.insert(x);changed=true;}
   if(owner.equals("org/apache/ibatis/type/BaseTypeHandler")&&m.name.equals("getResult")){InsnList x=new InsnList();x.add(new VarInsnNode(ALOAD,0));call(x,"handler","(Ljava/lang/Object;)V");m.instructions.insert(x);changed=true;}
   if(owner.equals("org/apache/ibatis/executor/resultset/DefaultResultSetHandler")&&m.name.equals("handleResultSets")){InsnList x=new InsnList();x.add(new VarInsnNode(ALOAD,0));call(x,"handlerStart","(Ljava/lang/Object;)V");m.instructions.insert(x);changed=true;}
   for(AbstractInsnNode n:m.instructions.toArray()){
    if(n instanceof MethodInsnNode){MethodInsnNode i=(MethodInsnNode)n;
     boolean callback=owner.equals("com/baomidou/mybatisplus/extension/plugins/MybatisPlusInterceptor")&&i.owner.equals("com/baomidou/mybatisplus/extension/plugins/inner/InnerInterceptor");
     boolean handler=owner.equals("org/apache/ibatis/executor/resultset/DefaultResultSetHandler")&&i.owner.equals("org/apache/ibatis/type/TypeHandler")&&i.name.equals("getResult");
     if(callback||handler){String site=m.name+m.desc+"|"+i.name+i.desc;sites.add(site);observeReceiver(m,i,callback,site);changed=true;}
     if(owner.equals("org/apache/ibatis/session/defaults/DefaultSqlSession")&&m.name.equals("selectList")&&Type.getArgumentTypes(m.desc).length==4&&i.name.equals("getMappedStatement")){InsnList x=new InsnList();x.add(new InsnNode(DUP));x.add(new VarInsnNode(ALOAD,0));x.add(new VarInsnNode(ALOAD,4));call(x,"selected","(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V");m.instructions.insert(n,x);changed=true;}
     if(owner.equals("org/mybatis/spring/SqlSessionTemplate$SqlSessionInterceptor")&&m.name.equals("invoke")&&i.owner.equals("org/mybatis/spring/SqlSessionUtils")&&i.name.equals("isSqlSessionTransactional")){InsnList x=new InsnList();x.add(new InsnNode(DUP));call(x,"transactional","(Z)V");m.instructions.insert(n,x);changed=true;}
    }
    if(n.getOpcode()==ARETURN){String hook=null,desc=null;boolean self=false;
     if(owner.equals("org/apache/ibatis/reflection/factory/DefaultObjectFactory")&&m.name.equals("create")&&Type.getArgumentTypes(m.desc).length==3){hook="birth";self=true;}
     if(owner.equals("org/apache/ibatis/type/DateTypeHandler")&&m.name.equals("getNullableResult")&&m.desc.endsWith("Ljava/util/Date;")){hook="date";self=true;}
     if(owner.equals("org/apache/ibatis/reflection/DefaultReflectorFactory")&&m.name.equals("findForClass")){hook="reflector";self=true;}
     if(owner.equals("org/apache/ibatis/reflection/Reflector")&&(m.name.equals("getSetInvoker")||m.name.equals("getGetInvoker")))hook="invoker";
     if(owner.equals("org/apache/ibatis/executor/resultset/ResultSetWrapper")&&m.name.equals("getTypeHandler"))hook="handler";
     if(owner.equals("com/baomidou/mybatisplus/core/override/MybatisMapperProxy")&&m.name.equals("cachedInvoker")){hook="mapperInvoker";self=true;}
     if(owner.equals("org/apache/ibatis/executor/resultset/DefaultResultSetHandler")&&m.name.equals("handleResultSets")){hook="handlerResult";self=true;}
     if(hook!=null){InsnList x=new InsnList();x.add(new InsnNode(DUP));if(self)x.add(new VarInsnNode(ALOAD,0));if(hook.equals("birth")){x.add(new VarInsnNode(ALOAD,2));x.add(new VarInsnNode(ALOAD,3));}if(hook.equals("mapperInvoker"))x.add(new VarInsnNode(ALOAD,1));call(x,hook,hook.equals("birth")?"(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V":hook.equals("mapperInvoker")?"(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)V":self?"(Ljava/lang/Object;Ljava/lang/Object;)V":"(Ljava/lang/Object;)V");m.instructions.insertBefore(n,x);changed=true;}
    }
    if(n.getOpcode()==RETURN&&owner.equals("org/apache/ibatis/session/defaults/DefaultSqlSession")&&m.name.equals("close")){InsnList x=new InsnList();x.add(new VarInsnNode(ALOAD,0));call(x,"closed","(Ljava/lang/Object;)V");m.instructions.insertBefore(n,x);changed=true;}
   }
  }
  Collections.sort(sites);List expected=(List)((Map)SqlResultLocalityHooks.config().get("instrumented_callsites")).getOrDefault(owner,Collections.emptyList());
  if(!sites.equals(expected))throw new IllegalStateException("SQL necessary callsite instrumentation differs: "+owner);
  SqlResultLocalityHooks.framework(owner,original,sites);if(!changed)return previous;
  List<MethodNode> guards=new ArrayList<>();int serial=0;
  for(MethodNode m:new ArrayList<MethodNode>(c.methods))if(!m.name.startsWith("$tf2$"))for(AbstractInsnNode n:m.instructions.toArray())if(n instanceof MethodInsnNode&&((MethodInsnNode)n).owner.equals(H)){
   MethodInsnNode i=(MethodInsnNode)n;String name="$tf2$sqlLocality$"+(serial++);guards.add(MonitorSafety.wrapper(name,i));i.owner=c.name;i.name=name;
  }c.methods.addAll(guards);ClassWriter w=new ClassWriter(ClassWriter.COMPUTE_MAXS|ClassWriter.COMPUTE_FRAMES){protected String getCommonSuperClass(String a,String b){return PlannedServiceAgent.commonType(loader,a,b);}};c.accept(w);return w.toByteArray();
 }
}
