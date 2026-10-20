import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Additional concrete evidence only. No provenance or expected-source code. */
public final class ExecutionKernelHooks implements Opcodes {
    static final String R="ExecutionKernelHooks";
    static boolean runtimeEmitted;
    static final String[] PINNED={"java/util/ArrayList","java/util/ArrayList$Itr","java/util/Arrays$ArrayList","java/util/Iterator"};
    static boolean enabled(){return "execution-dependency".equals(PlannedServiceAgent.plan.get("profile"));}
    static boolean method(String key){return enabled()&&(((Map)PlannedServiceAgent.plan.get("execution_kernel")).containsKey("methods")?((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("methods")).containsKey(key):key.equals(PlannedServiceAgent.plan.get("entry")));}
    static boolean contracts(){return PlannedServiceAgent.plan!=null&&enabled()&&Boolean.TRUE.equals(((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("public_contracts"));}
    static final Map<Object,List> STREAMS=new IdentityHashMap<>();
    static final Map<Object,Integer> ARRAY_VERSIONS=new IdentityHashMap<>();
    static final Map<Object,int[]> ARRAY_SLOTS=new IdentityHashMap<>();
    static Map instruction(String key,int pc){return (Map)((List)((Map)((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("methods")).get(key)).get("instructions")).get(pc);}
    static void args(InsnList h,Type[] types,int[] slots){h.add(new LdcInsnNode(types.length));h.add(new TypeInsnNode(ANEWARRAY,"java/lang/Object"));for(int j=0;j<types.length;j++){h.add(new InsnNode(DUP));h.add(new LdcInsnNode(j));h.add(new VarInsnNode(types[j].getOpcode(ILOAD),slots[j]));PlannedServiceAgent.box(h,types[j]);h.add(new InsnNode(AASTORE));}}
    static boolean instrument(MethodNode method,String key,List<AbstractInsnNode> code){
        if(!method(key))return false;
        boolean changed=false;
        for(int pc=0;pc<code.size();pc++){
            AbstractInsnNode n=code.get(pc);
            if(contracts()&&n instanceof LdcInsnNode&&((LdcInsnNode)n).cst instanceof Type){
                InsnList after=new InsnList();after.add(new InsnNode(DUP));after.add(new LdcInsnNode(pc));after.add(new MethodInsnNode(INVOKESTATIC,R,"classLiteral","(Ljava/lang/Class;I)V",false));method.instructions.insert(n,after);changed=true;continue;
            }
            if(contracts()&&n instanceof InvokeDynamicInsnNode){
                InvokeDynamicInsnNode call=(InvokeDynamicInsnNode)n;Type[] types=Type.getArgumentTypes(call.desc);int[] slots=new int[types.length];InsnList before=new InsnList(),after=new InsnList();
                for(int j=types.length-1;j>=0;j--){slots[j]=method.maxLocals;method.maxLocals+=types[j].getSize();before.add(new VarInsnNode(types[j].getOpcode(ISTORE),slots[j]));}
                for(int j=0;j<types.length;j++)before.add(new VarInsnNode(types[j].getOpcode(ILOAD),slots[j]));
                after.add(new InsnNode(DUP));after.add(new LdcInsnNode(key));after.add(new LdcInsnNode(pc));args(after,types,slots);after.add(new MethodInsnNode(INVOKESTATIC,R,"lambda","(Ljava/lang/Object;Ljava/lang/String;I[Ljava/lang/Object;)V",false));
                method.instructions.insertBefore(n,before);method.instructions.insert(n,after);changed=true;continue;
            }
            if(contracts()&&Arrays.asList(ANEWARRAY,AALOAD,AASTORE,ARRAYLENGTH).contains(n.getOpcode())){
                instrumentArray(method,n,pc);changed=true;continue;
            }
            if(!(n instanceof MethodInsnNode))continue;
            MethodInsnNode call=(MethodInsnNode)n;if(!call.name.equals("<init>"))continue;
            if(method.name.equals("<init>")&&((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).getOrDefault("constructor_starts",Collections.emptyMap())).containsKey(key)&&pc==((Number)((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("constructor_starts")).get(key)).intValue()-1)continue;
            Type[] types=Type.getArgumentTypes(call.desc);int[] slots=new int[types.length];InsnList before=new InsnList(),after=new InsnList();
            for(int j=types.length-1;j>=0;j--){slots[j]=method.maxLocals;method.maxLocals+=types[j].getSize();before.add(new VarInsnNode(types[j].getOpcode(ISTORE),slots[j]));}
            int receiver=method.maxLocals++;before.add(new VarInsnNode(ASTORE,receiver));before.add(new VarInsnNode(ALOAD,receiver));
            for(int j=0;j<types.length;j++)before.add(new VarInsnNode(types[j].getOpcode(ILOAD),slots[j]));
            // Uninitialized receiver is never passed to a hook. JVM initializes
            // its local alias only after successful original invokespecial.
            after.add(new LdcInsnNode(key));after.add(new LdcInsnNode(pc));after.add(new VarInsnNode(ALOAD,receiver));after.add(new LdcInsnNode(types.length));after.add(new TypeInsnNode(ANEWARRAY,"java/lang/Object"));
            for(int j=0;j<types.length;j++){after.add(new InsnNode(DUP));after.add(new LdcInsnNode(j));after.add(new VarInsnNode(types[j].getOpcode(ILOAD),slots[j]));PlannedServiceAgent.box(after,types[j]);after.add(new InsnNode(AASTORE));}
            after.add(new MethodInsnNode(INVOKESTATIC,R,"constructedAt","(Ljava/lang/String;ILjava/lang/Object;[Ljava/lang/Object;)V",false));
            LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode(),resume=new LabelNode();before.add(start);InsnList guarded=new InsnList();guarded.add(end);guarded.add(after);guarded.add(new JumpInsnNode(GOTO,resume));guarded.add(handler);int error=method.maxLocals++;guarded.add(new VarInsnNode(ASTORE,error));guarded.add(new LdcInsnNode(pc));guarded.add(new VarInsnNode(ALOAD,error));guarded.add(new MethodInsnNode(INVOKESTATIC,R,"constructorFailed","(ILjava/lang/Throwable;)V",false));guarded.add(new VarInsnNode(ALOAD,error));guarded.add(new InsnNode(ATHROW));guarded.add(resume);method.tryCatchBlocks.add(0,new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));
            method.instructions.insertBefore(n,before);method.instructions.insert(n,guarded);changed=true;
        }return changed;
    }
    static Map<String,Object> runtime()throws Exception{
        Map<String,Object> r=new LinkedHashMap<>();r.put("java_runtime_version",System.getProperty("java.runtime.version"));Map<String,String> hashes=new TreeMap<>();
        for(String name:PINNED)hashes.put(name,JdkContractProbe.hash(name));if(contracts()||probeExtended)hashes.putAll(JdkContractProbe.hashes());r.put("class_sha256",hashes);return r;
    }
    static void enter()throws Exception{if(!runtimeEmitted){PlannedServiceAgent.Recorder.emit("execution-runtime",runtime());runtimeEmitted=true;}}
    public static void classLiteral(Class type,int pc){synchronized(PlannedServiceAgent.Recorder.class){try{Map r=PlannedServiceAgent.Recorder.row();r.put("pc",pc);r.put("descriptor",Type.getDescriptor(type));r.put("observed",PlannedServiceAgent.Recorder.value(type));r.put("class_sha256",classHash(type));PlannedServiceAgent.Recorder.emit("execution-class-literal",r);}catch(Exception e){throw new IllegalStateException(e);}}}
    public static void constructed(int pc,Object receiver,Object[] args){synchronized(PlannedServiceAgent.Recorder.class){try{
        enter();
        Map<String,Object> r=PlannedServiceAgent.Recorder.row();r.put("pc",pc);r.put("receiver",PlannedServiceAgent.Recorder.value(receiver));r.put("receiver_type",receiver.getClass().getName());
        List<Object> values=new ArrayList<>();for(Object a:args)values.add(PlannedServiceAgent.Recorder.value(a));r.put("args",values);TemporalDateHooks.constructed(receiver,args,r);if(FrameworkCallHooks.config()!=null&&receiver.getClass().getName().equals("org.springframework.http.HttpEntity"))r.put("framework_contract",FrameworkCallHooks.entity(receiver,args));PlannedServiceAgent.Recorder.emit("execution-constructed",r);
    }catch(Throwable e){PlannedServiceAgent.Recorder.problem("execution-constructor:"+e);throw new IllegalStateException(e);}}}
    public static void constructorFailed(int pc,Throwable error){synchronized(PlannedServiceAgent.Recorder.class){Map r=PlannedServiceAgent.Recorder.row();r.put("pc",pc);r.put("exception",PlannedServiceAgent.Recorder.value(error));r.put("exception_type",error.getClass().getName());PlannedServiceAgent.Recorder.emit("execution-constructor-throw",r);}}
    public static void constructedAt(String method,int pc,Object receiver,Object[] args){constructed(pc,receiver,args);}
    static void exceptional(String call,Throwable error){
        Deque<Map<String,Object>> pending=CollectionServiceHooks.CALLS.get();if(pending.isEmpty())return;
        Map<String,Object> top=pending.peek(),current=PlannedServiceAgent.Recorder.row();
        if(Objects.equals(top.get("frame"),current.get("frame"))&&Objects.equals(top.get("callee"),call)){
            pending.pop();current.put("pc",top.get("pc"));current.put("call_id",top.get("call_id"));current.put("exception_type",error.getClass().getName());current.put("exception",PlannedServiceAgent.Recorder.value(error));PlannedServiceAgent.Recorder.emit("collection-call-throw",current);
        }
    }
    static boolean probeExtended;
    public static void lambda(Object lambda,String key,int pc,Object[] captured){synchronized(PlannedServiceAgent.Recorder.class){
        Map r=PlannedServiceAgent.Recorder.row();r.put("pc",pc);r.put("site",key+"@"+pc);r.put("lambda",PlannedServiceAgent.Recorder.value(lambda));r.put("lambda_type",lambda.getClass().getName());r.put("instruction",instruction(key,pc));List vs=new ArrayList();for(Object a:captured)vs.add(PlannedServiceAgent.Recorder.value(a));r.put("captures",vs);PlannedServiceAgent.Recorder.emit("execution-lambda",r);
    }}
    static void libraryEnd(Map start,Object result,Map row){if(!contracts())return;
        String call=(String)start.get("callee");Object recv=start.get("_receiver_ref");Map fact=new LinkedHashMap();
        if(call.equals("java/util/Collection.stream()Ljava/util/stream/Stream;")||call.equals("java/util/List.stream()Ljava/util/stream/Stream;")){
            if(!ReadEffectHooks.list(recv))return;
            boolean valid=result!=null&&result.getClass().getName().equals("java.util.stream.ReferencePipeline$Head")&&!((java.util.stream.Stream)result).isParallel();
            fact.put("kind","list-stream");fact.put("valid",valid);fact.put("source",PlannedServiceAgent.Recorder.id(recv));fact.put("epoch",CollectionServiceHooks.epoch(recv));fact.put("elements",CollectionServiceHooks.contents(recv));
            if(valid)STREAMS.put(result,Arrays.asList(recv,CollectionServiceHooks.contents(recv),CollectionServiceHooks.epoch(recv)));
        }else if(call.equals("java/util/stream/Stream.filter(Ljava/util/function/Predicate;)Ljava/util/stream/Stream;")&&STREAMS.containsKey(recv)){
            List source=STREAMS.remove(recv);Object predicate=((Object[])start.get("_args_ref"))[0];boolean valid=source.size()==3&&result!=null&&result.getClass().getName().equals("java.util.stream.ReferencePipeline$2")&&!((java.util.stream.Stream)result).isParallel();
            fact.put("kind","stream-filter");fact.put("valid",valid);fact.put("predicate",PlannedServiceAgent.Recorder.id(predicate));fact.put("source",PlannedServiceAgent.Recorder.id(source.get(0)));fact.put("epoch",source.get(2));
            try{fact.put("filter_class_sha256",JdkContractProbe.hash("java/util/stream/ReferencePipeline$2"));}catch(Exception e){throw new IllegalStateException(e);}
            if(valid)STREAMS.put(result,Arrays.asList(source.get(0),source.get(1),source.get(2),predicate));
        }else if(call.equals("java/util/stream/Stream.findFirst()Ljava/util/Optional;")&&STREAMS.containsKey(recv)){
            List source=STREAMS.remove(recv);List list=(List)source.get(0);boolean valid=result!=null&&result.getClass()==Optional.class&&source.get(1).equals(CollectionServiceHooks.contents(list))&&source.get(2).equals(CollectionServiceHooks.epoch(list));Optional o=(Optional)result;
            valid=valid&&(source.size()==4?(!o.isPresent()||containsIdentity(list,o.get())):(o.isPresent()==!list.isEmpty()&&(!o.isPresent()||o.get()==list.get(0))));fact.put("kind",source.size()==4?"filter-first":"stream-first");if(source.size()==4)fact.put("predicate",PlannedServiceAgent.Recorder.id(source.get(3)));fact.put("valid",valid);fact.put("source",PlannedServiceAgent.Recorder.id(list));fact.put("epoch",source.get(2));fact.put("present",o.isPresent());fact.put("selected",PlannedServiceAgent.Recorder.value(o.isPresent()?o.get():null));
        }else if((call.equals("java/util/Optional.orElseGet(Ljava/util/function/Supplier;)Ljava/lang/Object;")||call.equals("java/util/Optional.orElseThrow(Ljava/util/function/Supplier;)Ljava/lang/Object;"))&&recv!=null&&recv.getClass()==Optional.class){
            Optional o=(Optional)recv;fact.put("kind","optional-result");fact.put("present",o.isPresent());fact.put("valid",!o.isPresent()||result==o.get());fact.put("selected",PlannedServiceAgent.Recorder.value(o.isPresent()?o.get():null));
        }
        if(call.equals("java/lang/Object.getClass()Ljava/lang/Class;")&&recv!=null){fact.put("kind","object-class");fact.put("valid",result==recv.getClass());fact.put("receiver_type",recv.getClass().getName());}
        if(call.equals("java/lang/String.equals(Ljava/lang/Object;)Z")){fact.put("kind","string-equality");fact.put("valid",recv!=null&&recv.getClass()==String.class);try{fact.put("class_sha256",JdkContractProbe.hash("java/lang/String"));}catch(Exception e){throw new IllegalStateException(e);}}
        if(call.equals("org/slf4j/LoggerFactory.getLogger(Ljava/lang/Class;)Lorg/slf4j/Logger;")){
            fact.put("kind","logger-factory");try{Class factory=Class.forName("org.slf4j.LoggerFactory",false,Thread.currentThread().getContextClassLoader());Object context=factory.getMethod("getILoggerFactory").invoke(null);Map hashes=new TreeMap();for(Class c:new Class[]{factory,result.getClass(),context.getClass()})hashes.put(c.getName().replace('.','/'),classHash(c));Object type=((Object[])start.get("_args_ref"))[0];boolean valid=type instanceof Class&&result.getClass().getName().equals("ch.qos.logback.classic.Logger")&&context.getClass().getName().equals("ch.qos.logback.classic.LoggerContext")&&result.getClass().getMethod("getName").invoke(result).equals(((Class)type).getName());fact.put("valid",valid);fact.put("class_sha256",hashes);}catch(Exception e){fact.put("valid",false);fact.put("reason",e.getClass().getName());}
        }
        if(!fact.isEmpty())row.put("contract",fact);
    }
    static boolean containsIdentity(List list,Object wanted){for(Object item:list)if(item==wanted)return true;return false;}
    static final Map<Class,String> LIBRARY_HASHES=new IdentityHashMap<>();
    static String classHash(Class type)throws Exception{if(LIBRARY_HASHES.containsKey(type))return LIBRARY_HASHES.get(type);java.security.MessageDigest digest=java.security.MessageDigest.getInstance("SHA-256");try(java.io.InputStream in=type.getResourceAsStream("/"+type.getName().replace('.','/')+".class")){if(in==null)throw new IllegalStateException("Library bytes absent");byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1)digest.update(buffer,0,n);}StringBuilder text=new StringBuilder();for(byte b:digest.digest())text.append(String.format("%02x",b&255));String value=text.toString();LIBRARY_HASHES.put(type,value);return value;}
    static void callbackSite(Map row){if(!enabled()||CollectionServiceHooks.CALLS.get().isEmpty())return;Map top=CollectionServiceHooks.CALLS.get().peek();List source=STREAMS.get(top.get("_receiver_ref"));if(source!=null&&source.size()==4&&"java/util/stream/Stream.findFirst()Ljava/util/Optional;".equals(top.get("callee"))&&Objects.equals(top.get("frame"),row.get("parent"))){row.put("callsite",top.get("method")+"@"+top.get("pc"));row.put("callback_call_id",top.get("call_id"));}}
    static Map arrayRow(String operation,Object[] array,int index,int pc){Map r=PlannedServiceAgent.Recorder.row();r.put("pc",pc);r.put("operation",operation);r.put("array",PlannedServiceAgent.Recorder.value(array));r.put("index",index);r.put("version",ARRAY_VERSIONS.getOrDefault(array,0));if(array!=null){List values=new ArrayList();for(Object x:array)values.add(PlannedServiceAgent.Recorder.value(x));r.put("elements",values);r.put("component",array.getClass().getComponentType().getName());int[] versions=ARRAY_SLOTS.get(array);if(versions==null){versions=new int[array.length];ARRAY_SLOTS.put(array,versions);}List slots=new ArrayList();for(int v:versions)slots.add(v);r.put("element_versions",slots);}return r;}
    public static Object arrayBefore(String operation,Object[] array,int index,Object value,int pc){synchronized(PlannedServiceAgent.Recorder.class){Map r=arrayRow(operation,array,index,pc);r.put("value",PlannedServiceAgent.Recorder.value(value));if(operation.equals("store")&&array!=null)r.put("store_compatible",value==null||array.getClass().getComponentType().isInstance(value));return r;}}
    public static void arrayAfter(Object token,Object[] array,Object result,Throwable error){synchronized(PlannedServiceAgent.Recorder.class){Map r=(Map)token;String operation=(String)r.get("operation");
        if(error!=null){r.put("exception",PlannedServiceAgent.Recorder.value(error));r.put("exception_type",error.getClass().getName());PlannedServiceAgent.Recorder.emit("execution-array-throw",r);return;}
        if(operation.equals("new")){ARRAY_VERSIONS.put(array,0);r=arrayRow(operation,array,((Number)r.get("index")).intValue(),((Number)r.get("pc")).intValue());}
        if(operation.equals("store")){ARRAY_VERSIONS.put(array,ARRAY_VERSIONS.getOrDefault(array,0)+1);r.put("after_version",ARRAY_VERSIONS.get(array));int index=((Number)r.get("index")).intValue();int[] versions=ARRAY_SLOTS.get(array);versions[index]++;List slots=new ArrayList();for(int v:versions)slots.add(v);r.put("after_element_versions",slots);}
        if(operation.equals("length"))r.put("result",result);else r.put("result",PlannedServiceAgent.Recorder.value(result));PlannedServiceAgent.Recorder.emit("execution-array",r);
    }}
    static void instrumentArray(MethodNode method,AbstractInsnNode n,int pc){
        int op=n.getOpcode(),array=method.maxLocals++,index=method.maxLocals++,value=method.maxLocals++,token=method.maxLocals++,result=method.maxLocals++,error=method.maxLocals++;
        String operation=op==ANEWARRAY?"new":op==AALOAD?"load":op==AASTORE?"store":"length";InsnList before=new InsnList(),after=new InsnList();
        if(op==AASTORE)before.add(new VarInsnNode(ASTORE,value));
        if(op!=ARRAYLENGTH)before.add(new VarInsnNode(ISTORE,index));else{before.add(new LdcInsnNode(-1));before.add(new VarInsnNode(ISTORE,index));}
        if(op!=ANEWARRAY)before.add(new VarInsnNode(ASTORE,array));else{before.add(new InsnNode(ACONST_NULL));before.add(new VarInsnNode(ASTORE,array));}
        before.add(new LdcInsnNode(operation));before.add(new VarInsnNode(ALOAD,array));before.add(new VarInsnNode(ILOAD,index));before.add(op==AASTORE?new VarInsnNode(ALOAD,value):new InsnNode(ACONST_NULL));before.add(new LdcInsnNode(pc));before.add(new MethodInsnNode(INVOKESTATIC,R,"arrayBefore","(Ljava/lang/String;[Ljava/lang/Object;ILjava/lang/Object;I)Ljava/lang/Object;",false));before.add(new VarInsnNode(ASTORE,token));
        if(op!=ANEWARRAY)before.add(new VarInsnNode(ALOAD,array));if(op!=ARRAYLENGTH)before.add(new VarInsnNode(ILOAD,index));if(op==AASTORE)before.add(new VarInsnNode(ALOAD,value));
        LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode(),resume=new LabelNode();before.add(start);after.add(end);
        if(op==ANEWARRAY){after.add(new InsnNode(DUP));after.add(new VarInsnNode(ASTORE,array));}
        if(op==AALOAD){after.add(new InsnNode(DUP));after.add(new VarInsnNode(ASTORE,result));}
        if(op==ARRAYLENGTH){after.add(new InsnNode(DUP));after.add(new VarInsnNode(ISTORE,result));}
        after.add(new VarInsnNode(ALOAD,token));after.add(new VarInsnNode(ALOAD,array));
        if(op==AALOAD)after.add(new VarInsnNode(ALOAD,result));else if(op==ARRAYLENGTH){after.add(new VarInsnNode(ILOAD,result));PlannedServiceAgent.box(after,Type.INT_TYPE);}else after.add(new InsnNode(ACONST_NULL));
        after.add(new InsnNode(ACONST_NULL));after.add(new MethodInsnNode(INVOKESTATIC,R,"arrayAfter","(Ljava/lang/Object;[Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Throwable;)V",false));after.add(new JumpInsnNode(GOTO,resume));
        after.add(handler);after.add(new VarInsnNode(ASTORE,error));after.add(new VarInsnNode(ALOAD,token));after.add(new VarInsnNode(ALOAD,array));after.add(new InsnNode(ACONST_NULL));after.add(new VarInsnNode(ALOAD,error));after.add(new MethodInsnNode(INVOKESTATIC,R,"arrayAfter","(Ljava/lang/Object;[Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Throwable;)V",false));after.add(new VarInsnNode(ALOAD,error));after.add(new InsnNode(ATHROW));after.add(resume);
        method.tryCatchBlocks.add(0,new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));method.instructions.insertBefore(n,before);method.instructions.insert(n,after);
    }
    public static void main(String[] args)throws Exception{probeExtended=args.length>0;System.out.println(new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(runtime()));}
}
