import java.lang.reflect.Field;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Observation of original root instructions. All provenance runs offline. */
public final class CollectionServiceHooks implements Opcodes {
    static final String R="CollectionServiceHooks";
    static final ThreadLocal<Deque<Map<String,Object>>> CALLS=new ThreadLocal<Deque<Map<String,Object>>>(){
        protected Deque<Map<String,Object>> initialValue(){return new ArrayDeque<>();}};
    static final Set<Object> READ_ONLY=Collections.newSetFromMap(new IdentityHashMap<Object,Boolean>());
    static final Map<Object,List<Object>> CONTENTS=new IdentityHashMap<>();
    static final Map<Object,Integer> EPOCHS=new IdentityHashMap<>();
    static long callCounter;
    static Map<String,Object> plan(){return PlannedServiceAgent.plan;}
    static Map<String,Object> value(Object x){return PlannedServiceAgent.Recorder.value(x);}
    static String id(Object x){return PlannedServiceAgent.Recorder.id(x);}
    static void emit(String kind,Map<String,Object> r){PlannedServiceAgent.Recorder.emit(kind,r);}
    static Map<String,Object> row(){return PlannedServiceAgent.Recorder.row();}
    static boolean enabled(){return "collection-computation".equals(plan().get("profile"))||"bounded-scalar".equals(plan().get("profile"))||ExecutionKernelHooks.enabled();}
    static boolean mutate(MethodInsnNode c){return (c.owner.startsWith("java/util/")&&Arrays.asList("add","addAll","set","put","putAll","remove","removeAll","retainAll","clear","replace","replaceAll","sort","compute","computeIfAbsent","computeIfPresent","merge").contains(c.name));}
    static boolean instrument(MethodNode m,String key,List<AbstractInsnNode> code){
        if(!enabled()&&!ResponseBindingHooks.enabled())return false;boolean root=key.equals(plan().get("entry"))||ExecutionKernelHooks.method(key),changed=false;
        if(((List)plan().getOrDefault("json_conversion_methods",Collections.emptyList())).contains(key)){
            int token=m.maxLocals++;InsnList h=new InsnList();h.add(new VarInsnNode(ALOAD,0));h.add(new MethodInsnNode(INVOKESTATIC,R,"convertStart","(Ljava/lang/Object;)Ljava/lang/Object;",false));h.add(new VarInsnNode(ASTORE,token));m.instructions.insert(h);
            for(AbstractInsnNode n:code)if(n.getOpcode()==ARETURN){InsnList e=new InsnList();e.add(new InsnNode(DUP));e.add(new VarInsnNode(ALOAD,token));e.add(new MethodInsnNode(INVOKESTATIC,R,"convertEnd","(Ljava/lang/Object;Ljava/lang/Object;)V",false));m.instructions.insertBefore(n,e);}changed=true;
        }
        if(!enabled())return changed;
        List selected=(List)plan().get("collection_selected_calls");
        for(int i=0;i<code.size();i++){
            AbstractInsnNode n=code.get(i);
            if(n instanceof MethodInsnNode){MethodInsnNode c=(MethodInsnNode)n;
                boolean call=root&&!c.name.equals("<init>")&&(PlannedServiceAgent.full||ExecutionKernelHooks.method(key)||selected.contains(i));
                boolean guard=mutate(c)&&c.getOpcode()!=INVOKESTATIC;
                if(!call&&!guard)continue;
                Type[] ts=Type.getArgumentTypes(c.desc);int[] slots=new int[ts.length];InsnList a=new InsnList(),b=new InsnList();
                for(int j=ts.length-1;j>=0;j--){slots[j]=m.maxLocals;m.maxLocals+=ts[j].getSize();a.add(new VarInsnNode(ts[j].getOpcode(ISTORE),slots[j]));}
                int recv=-1;if(c.getOpcode()!=INVOKESTATIC){recv=m.maxLocals++;a.add(new VarInsnNode(ASTORE,recv));}
                if(guard){a.add(new VarInsnNode(ALOAD,recv));a.add(new MethodInsnNode(INVOKESTATIC,R,"guardMutation","(Ljava/lang/Object;)V",false));}
                if(call){a.add(new LdcInsnNode(key));a.add(new LdcInsnNode(i));a.add(recv<0?new InsnNode(ACONST_NULL):new VarInsnNode(ALOAD,recv));
                    a.add(new LdcInsnNode(ts.length));a.add(new TypeInsnNode(ANEWARRAY,"java/lang/Object"));
                    for(int j=0;j<ts.length;j++){a.add(new InsnNode(DUP));a.add(new LdcInsnNode(j));a.add(new VarInsnNode(ts[j].getOpcode(ILOAD),slots[j]));PlannedServiceAgent.box(a,ts[j]);a.add(new InsnNode(AASTORE));}
                    a.add(new MethodInsnNode(INVOKESTATIC,R,"beginAt","(Ljava/lang/String;ILjava/lang/Object;[Ljava/lang/Object;)V",false));}
                if(recv>=0)a.add(new VarInsnNode(ALOAD,recv));for(int j=0;j<ts.length;j++)a.add(new VarInsnNode(ts[j].getOpcode(ILOAD),slots[j]));
                if(call){Type t=Type.getReturnType(c.desc);if(t.getSort()==Type.VOID)b.add(new InsnNode(ACONST_NULL));else{b.add(new InsnNode(t.getSize()==2?DUP2:DUP));PlannedServiceAgent.box(b,t);}
                    b.add(new MethodInsnNode(INVOKESTATIC,R,"end","(Ljava/lang/Object;)V",false));}
                m.instructions.insertBefore(n,a);m.instructions.insert(n,b);changed=true;
            }
            if(root&&n instanceof JumpInsnNode&&n.getOpcode()!=GOTO&&!PlannedServiceAgent.full){
                JumpInsnNode j=(JumpInsnNode)n;LabelNode original=j.label,taken=new LabelNode(),next=new LabelNode();j.label=taken;
                InsnList h=new InsnList();PlannedServiceAgent.branch(h,key+"@"+i,false);h.add(new JumpInsnNode(GOTO,next));h.add(taken);PlannedServiceAgent.branch(h,key+"@"+i,true);h.add(new JumpInsnNode(GOTO,original));h.add(next);m.instructions.insert(n,h);changed=true;
            }
        }
        if(root){Set<LabelNode> seen=Collections.newSetFromMap(new IdentityHashMap<LabelNode,Boolean>());
            for(TryCatchBlockNode t:new ArrayList<TryCatchBlockNode>(m.tryCatchBlocks))if(seen.add(t.handler)){
                AbstractInsnNode n=t.handler;while(n!=null&&n.getOpcode()<0)n=n.getNext();int index=code.indexOf(n);if(index<0)throw new IllegalStateException("Handler index absent");
                InsnList h=new InsnList();h.add(new InsnNode(DUP));h.add(new LdcInsnNode(index));h.add(new MethodInsnNode(INVOKESTATIC,R,"caught","(Ljava/lang/Throwable;I)V",false));m.instructions.insertBefore(n,h);changed=true;
            }
        }return changed;
    }
    public static void guardMutation(Object o){synchronized(PlannedServiceAgent.Recorder.class){if(READ_ONLY.contains(o)){PlannedServiceAgent.Recorder.problem("Mutation of a received collection");throw new IllegalStateException("Received collection is read-only");}}}
    public static Object convertStart(Object source){synchronized(PlannedServiceAgent.Recorder.class){try{return SpringTransportAgent.Transport.conversionSnapshot(source);}catch(Exception e){throw new IllegalStateException(e);}}}
    public static void convertEnd(Object target,Object token){synchronized(PlannedServiceAgent.Recorder.class){try{Map<String,Object> r=row();r.put("input",token);r.put("output",SpringTransportAgent.Transport.conversionSnapshot(target));SpringTransportAgent.Transport.received(target,new IdentityHashMap<>());emit("json-conversion",r);}catch(Exception e){PlannedServiceAgent.Recorder.problem("conversion:"+e);throw new IllegalStateException(e);}}}
    static List<Object> contents(Object o){List<Object> out=new ArrayList<>();
        if(o instanceof List){for(Object x:(List)o){if(out.size()>=10000)throw new IllegalStateException("List bound");out.add(value(x));}}
        else if(o instanceof Map){for(Object key:((Map)o).keySet()){if(!(key instanceof String))throw new IllegalStateException("Only String map keys admitted");if(out.size()>=10000)throw new IllegalStateException("Map bound");Map<String,Object> r=new LinkedHashMap<>();r.put("key",key);r.put("observed",value(((Map)o).get(key)));out.add(r);}out.sort((a,b)->((String)((Map)a).get("key")).compareTo((String)((Map)b).get("key")));}
        return out;
    }
    public static int epoch(Object o){synchronized(PlannedServiceAgent.Recorder.class){List<Object> now=contents(o),before=CONTENTS.get(o);int epoch=EPOCHS.getOrDefault(o,0);if(before!=null&&!before.equals(now)){if(READ_ONLY.contains(o))throw new IllegalStateException("Received collection changed outside guarded bytecode");epoch++;}CONTENTS.put(o,now);EPOCHS.put(o,epoch);return epoch;}}
    public static void received(Object o){synchronized(PlannedServiceAgent.Recorder.class){if(o instanceof List||o instanceof Map){epoch(o);READ_ONLY.add(o);}}}
    public static void begin(int pc,Object receiver,Object[] args){beginAt((String)plan().get("entry"),pc,receiver,args);}
    public static void beginAt(String key,int pc,Object receiver,Object[] args){synchronized(PlannedServiceAgent.Recorder.class){try{
        Map<String,Object> r=row();r.put("pc",pc);r.put("receiver",value(receiver));if(ExecutionKernelHooks.enabled())r.put("receiver_type",receiver==null?null:receiver.getClass().getName());List<Object> vs=new ArrayList<>();for(Object x:args)vs.add(value(x));r.put("args",vs);
        Map method=(Map)plan().get("collection_method");if(ExecutionKernelHooks.enabled()){Map cfg=(Map)plan().get("execution_kernel");if(cfg.containsKey("methods"))method=(Map)((Map)cfg.get("methods")).get(key);r.put("method",key);r.put("call_id",++callCounter);}Map ins=(Map)((List)method.get("instructions")).get(pc);String callee=ins.get("owner")+"."+ins.get("name")+ins.get("desc");r.put("callee",callee);
        Map getter=(Map)((Map)plan().get("collection_getters")).get(callee);
        if(receiver!=null&&(getter!=null||((Map)plan().get("collection_setters")).containsKey(callee))&&!receiver.getClass().getName().replace('.','/').equals(ins.get("owner")))throw new IllegalStateException("Unresolved accessor virtual dispatch");
        if(receiver instanceof List&&!(ExecutionKernelHooks.contracts()?ReadEffectHooks.list(receiver):Arrays.asList("java.util.ArrayList","java.util.Arrays$ArrayList").contains(receiver.getClass().getName())))throw new IllegalStateException("List implementation outside explicit summary");
        if(receiver instanceof Map&&!receiver.getClass().getName().equals("java.util.HashMap"))throw new IllegalStateException("Map implementation outside explicit summary");
        if(getter!=null&&receiver!=null){String name=(String)getter.get("field");int at=name.lastIndexOf('.');Class<?> owner=Class.forName(name.substring(0,at).replace('/','.'),false,receiver.getClass().getClassLoader());Field f=owner.getDeclaredField(name.substring(at+1));f.setAccessible(true);
            Map<String,Object> v=new LinkedHashMap<>();v.put("owner",id(receiver));v.put("field",name);v.put("version",PlannedServiceAgent.Recorder.VERSIONS.getOrDefault(id(receiver)+":"+name,0));v.put("descriptor",getter.get("descriptor"));v.put("observed",value(f.get(receiver)));r.put("getter",v);}
        if(receiver instanceof List||receiver instanceof Map){r.put("collection_epoch",epoch(receiver));r.put("collection",contents(receiver));}
        r.put("_receiver_ref",receiver);r.put("_args_ref",args);if(ExecutionKernelHooks.extended()){List types=new ArrayList();for(Object a:args)types.add(a==null?null:a.getClass().getName());r.put("argument_types",types);}ExecutionKernelHooks.scalarBegin(r);RequestEntityHooks.begin(r);CALLS.get().push(r);Map<String,Object> exported=new LinkedHashMap<>(r);for(String internal:new ArrayList<String>(exported.keySet()))if(internal.startsWith("_"))exported.remove(internal);emit("collection-call-enter",exported);
    }catch(Throwable e){PlannedServiceAgent.Recorder.problem("collection-begin:"+e);throw new IllegalStateException(e);}}}
    public static void end(Object result){synchronized(PlannedServiceAgent.Recorder.class){try{Map<String,Object> start=CALLS.get().pop(),r=row();r.put("pc",start.get("pc"));r.put("result",value(result));Object receiver=start.get("_receiver_ref");if(receiver instanceof List||receiver instanceof Map){r.put("collection_epoch",epoch(receiver));if(ExecutionKernelHooks.enabled())r.put("collection_after",contents(receiver));}if(ExecutionKernelHooks.enabled()){r.put("call_id",start.get("call_id"));r.put("method",start.get("method"));r.put("result_type",result==null?null:result.getClass().getName());}ExecutionKernelHooks.libraryEnd(start,result,r);ExecutionKernelHooks.scalarEnd(start,result,r);FrameworkCallHooks.end(start,result,r);RequestEntityHooks.end(start,result,r);TemporalDateHooks.end(start,result,r);AsyncTaskHooks.completed(start,result,null,r);emit("collection-call-exit",r);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("collection-end:"+e);throw new IllegalStateException(e);}}}
    public static void caught(Throwable error,int pc){synchronized(PlannedServiceAgent.Recorder.class){Map<String,Object> r=row();r.put("pc",pc);r.put("exception",error.getClass().getName());r.put("observed",value(error));
        while(!CALLS.get().isEmpty()&&Objects.equals(CALLS.get().peek().get("frame"),r.get("frame"))){Map<String,Object> failed=CALLS.get().pop();r.put("failed_call_pc",failed.get("pc"));}
        emit("collection-catch",r);}}
}
