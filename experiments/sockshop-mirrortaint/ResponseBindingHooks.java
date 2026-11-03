import java.lang.reflect.Field;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Root-to-wire identity witnesses and explicitly admitted pre-output sources. */
public final class ResponseBindingHooks implements Opcodes {
    static final Map<ClassLoader,Map<String,Map>> WRAPPER_CLASSES=Collections.synchronizedMap(new IdentityHashMap<ClassLoader,Map<String,Map>>());
    static synchronized void registerClass(ClassNode cls,ClassLoader loader){
        Map policy=(Map)PlannedServiceAgent.plan.get("map_wrapper_observation");if(policy==null)return;
        boolean needed=false;for(Object raw:((Map)policy.get("candidates")).values())for(Object item:(List)raw)if(cls.name.equals(((Map)item).get("class")))needed=true;if(!needed)return;
        Map m=new LinkedHashMap();m.put("super",cls.superName);boolean eligible=(cls.visibleAnnotations==null||cls.visibleAnnotations.isEmpty())&&(cls.invisibleAnnotations==null||cls.invisibleAnnotations.isEmpty());
        for(FieldNode f:cls.fields)if((f.access&ACC_STATIC)==0)eligible=false;
        for(MethodNode method:cls.methods)if(((List)((Map)policy.get("contract")).get("read_methods")).contains(method.name))eligible=false;
        m.put("eligible",eligible);Map<String,Map> group=WRAPPER_CLASSES.get(loader);if(group==null){group=new java.util.concurrent.ConcurrentHashMap<>();WRAPPER_CLASSES.put(loader,group);}group.put(cls.name,m);
        Map fact=PlannedServiceAgent.Recorder.row();fact.put("class",cls.name);fact.put("class_sha256",PlannedServiceAgent.hashes.get(cls.name));fact.put("loader",PlannedServiceAgent.Recorder.id(loader));PlannedServiceAgent.Recorder.emit("map-wrapper-class",fact);
    }
    static void mapWrapper(Object value,boolean target,List<Map> proofs)throws Exception{
        if(value.getClass()==HashMap.class||value.getClass()==LinkedHashMap.class)return;
        Map policy=(Map)PlannedServiceAgent.plan.get("map_wrapper_observation");
        String type=value.getClass().getName().replace('.','/');
        if(!target||proofs==null||policy==null||!((Map)policy.get("candidates")).containsKey(type))throw new IllegalStateException("Unmodeled binding Map type");
        List<Map> chain=(List<Map>)((Map)policy.get("candidates")).get(type);Class<?> actual=value.getClass();List loaders=new ArrayList();
        for(Map expected:chain){String owner=actual.getName().replace('.','/');Map<String,Map> group=WRAPPER_CLASSES.get(actual.getClassLoader());Map checked=group==null?null:group.get(owner);
            if(!owner.equals(expected.get("class"))||!PlannedServiceAgent.Recorder.CHECKED_CLASSES.contains(owner)||checked==null||!Boolean.TRUE.equals(checked.get("eligible"))||!Objects.equals(checked.get("super"),expected.get("super")))throw new IllegalStateException("Map wrapper frozen hierarchy/read dispatch differs");
            loaders.add(PlannedServiceAgent.Recorder.id(actual.getClassLoader()));actual=actual.getSuperclass();
        }
        if(actual!=HashMap.class)throw new IllegalStateException("Map wrapper base differs");
        Map contract=(Map)policy.get("contract"),runtime=new LinkedHashMap();runtime.put("java_runtime_version",System.getProperty("java.runtime.version"));Map hashes=new TreeMap();
        for(Object name:((Map)((Map)((List)contract.get("profiles")).get(0)).get("class_sha256")).keySet())hashes.put(name,JdkContractProbe.hash((String)name));
        runtime.put("class_sha256",hashes);if(!((List)contract.get("profiles")).contains(runtime))throw new IllegalStateException("Map wrapper JDK implementation differs");
        String id=PlannedServiceAgent.Recorder.id(value);for(Map previous:proofs)if(id.equals(previous.get("owner")))return;
        Map fact=new LinkedHashMap();fact.put("owner",id);fact.put("class",type);fact.put("chain",chain);fact.put("loaders",loaders);fact.put("runtime",runtime);fact.put("methods",contract.get("read_methods"));proofs.add(fact);
    }
    static List<Map.Entry> wrapperEntries(Object value,List<Map> proofs)throws Exception{
        // Never invoke a wrapper's get/keySet/iterator, including lazy JDK view
        // creation. Read only the pinned HashMap/Node representation.
        Field table=HashMap.class.getDeclaredField("table"),size=HashMap.class.getDeclaredField("size"),mod=HashMap.class.getDeclaredField("modCount");table.setAccessible(true);size.setAccessible(true);mod.setAccessible(true);
        int count=(Integer)size.get(value),version=(Integer)mod.get(value);if(count<0||count>10000)throw new IllegalStateException("Wrapper size bound");
        Class<?> nodeType=Class.forName("java.util.HashMap$Node",false,null);Field key=nodeType.getDeclaredField("key"),val=nodeType.getDeclaredField("value"),next=nodeType.getDeclaredField("next");key.setAccessible(true);val.setAccessible(true);next.setAccessible(true);
        List<Map.Entry> entries=new ArrayList<>();IdentityHashMap<Object,Boolean> nodes=new IdentityHashMap<>();Object[] buckets=(Object[])table.get(value);
        if(buckets!=null)for(Object first:buckets)for(Object node=first;node!=null;node=next.get(node)){
            if(node.getClass()!=nodeType||nodes.put(node,true)!=null||entries.size()>=count)throw new IllegalStateException("Unsupported wrapper Node shape");
            Object k=key.get(node);if(k==null||k.getClass()!=String.class)throw new IllegalStateException("Non-string binding key");
            entries.add(new AbstractMap.SimpleImmutableEntry(k,val.get(node)));
        }
        if(entries.size()!=count||count!=(Integer)size.get(value)||version!=(Integer)mod.get(value))throw new IllegalStateException("Wrapper changed during snapshot");
        String id=PlannedServiceAgent.Recorder.id(value);for(Map fact:proofs)if(id.equals(fact.get("owner"))){fact.put("size",count);fact.put("mod_count",version);fact.put("entries",entries.size());}
        return entries;
    }
    static final String R="ResponseBindingHooks";
    static boolean sourceCapture=false;
    static final Set<String> RETURN_MESSAGES=new HashSet<>();
    static Map binding(){return (Map)PlannedServiceAgent.plan.get("response_binding");}
    static boolean enabled(){return binding()!=null;}
    static Map row()throws Exception{
        Map r=PlannedServiceAgent.Recorder.row();
        try{r.putAll(SpringTransportAgent.Transport.context());}catch(ClassNotFoundException ignored){W3CTraceContext c=SpringTransportAgent.Transport.ASYNC.get();if(c!=null)r.putAll(c.fields());}
        return r;
    }
    static void emit(String kind,Map r){PlannedServiceAgent.Recorder.emit(kind,r);}
    static boolean admitted(String key,Object recv){
        boolean declared=((List)binding().get("source_calls")).contains(key)||((List)binding().get("transparent_calls")).contains(key);if(!declared)return false;
        if(recv!=null&&(key.startsWith("java/util/List.")||key.startsWith("java/util/Collection.")||key.startsWith("java/util/ArrayList.")))return Arrays.asList("java.util.ArrayList","java.util.Arrays$ArrayList","java.util.Collections$SingletonList","java.util.Collections$EmptyList").contains(recv.getClass().getName());
        if(recv!=null&&(key.startsWith("org/springframework/http/HttpEntity.getBody")||key.startsWith("org/springframework/http/ResponseEntity.getBody")))return Arrays.asList("org.springframework.http.HttpEntity","org.springframework.http.ResponseEntity").contains(recv.getClass().getName());
        if(recv!=null&&key.startsWith("org/springframework/hateoas/Resource.getContent"))return recv.getClass().getName().equals("org.springframework.hateoas.Resource");
        return true;
    }
    static boolean instrument(MethodNode m,String key,List<AbstractInsnNode> code){
        if(!enabled()||(m.name.equals("<init>")&&!ExecutionKernelHooks.method(key)))return false;
        boolean changed=false;
        for(AbstractInsnNode n:code){
            if(!(n instanceof MethodInsnNode))continue;MethodInsnNode c=(MethodInsnNode)n;if(c.name.equals("<init>"))continue;
            Type[] types=Type.getArgumentTypes(c.desc);Type ret=Type.getReturnType(c.desc);
            int[] slots=new int[types.length];int recv=-1;InsnList before=new InsnList(),after=new InsnList();
            for(int j=types.length-1;j>=0;j--){slots[j]=m.maxLocals;m.maxLocals+=types[j].getSize();before.add(new VarInsnNode(types[j].getOpcode(ISTORE),slots[j]));}
            if(c.getOpcode()!=INVOKESTATIC){recv=m.maxLocals++;before.add(new VarInsnNode(ASTORE,recv));}
            // Read-only source collections are guarded even for forwarding profiles.
            if(CollectionServiceHooks.mutate(c)&&recv>=0){before.add(new VarInsnNode(ALOAD,recv));before.add(new MethodInsnNode(INVOKESTATIC,"CollectionServiceHooks","guardMutation","(Ljava/lang/Object;)V",false));}
            String call=c.owner+"."+c.name+c.desc;
            arguments(before,call,recv,types,slots);before.add(new MethodInsnNode(INVOKESTATIC,R,"before","(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)V",false));
            if(recv>=0)before.add(new VarInsnNode(ALOAD,recv));for(int j=0;j<types.length;j++)before.add(new VarInsnNode(types[j].getOpcode(ILOAD),slots[j]));
            int result=m.maxLocals;m.maxLocals+=Math.max(1,ret.getSize());
            if(ReadEffectHooks.enabled()||ExecutionKernelHooks.enabled()){
                // Catch only the original invoke, including failures before the
                // callee enters. The handler is inline inside the original
                // protected ranges, so rethrow reaches the original catch/finally.
                LabelNode start=new LabelNode(),end=new LabelNode(),handler=new LabelNode(),done=new LabelNode();
                before.add(start);after.add(end);after.add(new JumpInsnNode(GOTO,done));after.add(handler);
                int error=m.maxLocals++;after.add(new VarInsnNode(ASTORE,error));
                arguments(after,call,recv,types,slots);after.add(new VarInsnNode(ALOAD,error));
                after.add(new MethodInsnNode(INVOKESTATIC,R,"exceptional","(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;Ljava/lang/Throwable;)V",false));
                after.add(new VarInsnNode(ALOAD,error));after.add(new InsnNode(ATHROW));after.add(done);
                m.tryCatchBlocks.add(0,new TryCatchBlockNode(start,end,handler,"java/lang/Throwable"));
            }
            if(ret.getSort()!=Type.VOID)after.add(new VarInsnNode(ret.getOpcode(ISTORE),result));
            after.add(new LdcInsnNode(key+"@"+code.indexOf(n)));arguments(after,call,recv,types,slots);
            if(ret.getSort()==Type.VOID)after.add(new InsnNode(ACONST_NULL));else{after.add(new VarInsnNode(ret.getOpcode(ILOAD),result));PlannedServiceAgent.box(after,ret);}
            after.add(new MethodInsnNode(INVOKESTATIC,R,"afterAt","(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;Ljava/lang/Object;)V",false));
            if(ret.getSort()!=Type.VOID)after.add(new VarInsnNode(ret.getOpcode(ILOAD),result));
            m.instructions.insertBefore(n,before);m.instructions.insert(n,after);changed=true;
        }return changed;
    }
    static void arguments(InsnList out,String key,int recv,Type[] ts,int[] slots){
        out.add(new LdcInsnNode(key));out.add(recv<0?new InsnNode(ACONST_NULL):new VarInsnNode(ALOAD,recv));
        out.add(new LdcInsnNode(ts.length));out.add(new TypeInsnNode(ANEWARRAY,"java/lang/Object"));
        for(int j=0;j<ts.length;j++){out.add(new InsnNode(DUP));out.add(new LdcInsnNode(j));out.add(new VarInsnNode(ts[j].getOpcode(ILOAD),slots[j]));PlannedServiceAgent.box(out,ts[j]);out.add(new InsnNode(AASTORE));}
    }
    static boolean active(){return enabled()&&!PlannedServiceAgent.Recorder.STACK.get().isEmpty();}
    // Value demands are independent of reference/effect obligations. This
    // context never suppresses a call, write counter, alias or contract hook.
    static final class SnapshotPolicy {
        Map policy,proof;boolean selected;
        SnapshotPolicy(Map witness,String call,boolean input){
            policy=(Map)PlannedServiceAgent.plan.get("target_observation_closure");
            if(policy==null)return;
            Deque<PlannedServiceAgent.Recorder.Frame> stack=PlannedServiceAgent.Recorder.STACK.get();
            boolean rooted=!stack.isEmpty()&&stack.peekLast().method.equals(PlannedServiceAgent.plan.get("entry"));
            boolean scoped=input&&rooted&&stack.peek().method.equals(PlannedServiceAgent.plan.get("entry"));
            if(!input&&rooted&&!CollectionServiceHooks.CALLS.get().isEmpty()){
                Map actual=CollectionServiceHooks.CALLS.get().peek();
                scoped=Objects.equals(actual.get("frame"),stack.peek().id)&&Objects.equals(actual.get("callee"),call)
                    &&((Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("methods")).containsKey(actual.get("method"));
            }
            selected=rooted&&scoped&&!PlannedServiceAgent.Recorder.captureInvalid&&"selective".equals(PlannedServiceAgent.mode)
                &&Boolean.TRUE.equals(policy.get("enabled"))&&!System.getProperty("service.target.observation","true").equals("false");
            proof=new LinkedHashMap();proof.put("version",1);proof.put("policy_sha256",policy.get("sha256"));proof.put("selected",selected);
            proof.put("scalar_fields",new TreeMap());proof.put("container_values",new TreeMap());witness.put("target_observation",proof);
        }
        void count(String kind,String field){Map counts=(Map)proof.get(kind);counts.put(field,((Number)counts.getOrDefault(field,0)).intValue()+1);}
        boolean scalar(Map property){
            String field=(String)property.get("field");
            if(!selected||!Objects.equals(((Map)policy.get("omittable_scalar_fields")).get(field),property.get("descriptor")))return false;
            count("scalar_fields",field);return true;
        }
        boolean member(String anchor,String path,Object value){
            if(!selected||anchor==null||!((Map)policy.get("container_values")).containsKey(anchor))return false;
            if(value!=null&&!Arrays.asList(String.class,Integer.class,Long.class,Boolean.class,Double.class,Float.class,Short.class,Byte.class,Character.class).contains(value.getClass()))return false;
            String target=(String)binding().get("path");int slash=path.lastIndexOf('/');
            // A differently positioned instance is ordinary ineligibility:
            // collect all its values BEFORE any cut at that location.
            if(slash<0||!path.substring(0,slash).equals(target.substring(0,target.lastIndexOf('/'))))return false;
            if(path.equals(target))return false;
            count("container_values",anchor);return true;
        }
    }
    static List<Map> snapshot(Object obj,boolean target)throws Exception{
        return snapshot(obj,target,null);
    }
    static List<Map> snapshot(Object obj,boolean target,SnapshotPolicy policy)throws Exception{
        return snapshot(obj,target,policy,null);
    }
    static List<Map> snapshot(Object obj,boolean target,SnapshotPolicy policy,List<Map> wrappers)throws Exception{
        List<Map> result=new ArrayList<>();walk(obj,"",null,result,new IdentityHashMap<Object,Boolean>(),0,target,policy,wrappers);return result;
    }
    static void leaf(Object owner,String field,Object value,String path,String anchor,List<Map> result,boolean target,SnapshotPolicy policy){
        List wanted=target?Collections.singletonList(binding().get("target")):(List)binding().get("source_fields");
        boolean dynamic=target&&Boolean.TRUE.equals(binding().get("runtime_container_path"))&&field.startsWith("@")&&path.equals(binding().get("path"));
        if(!dynamic&&!wanted.contains(anchor==null?field:anchor))return;
        if(!target&&policy!=null&&field.startsWith("@map:")&&policy.member(anchor,path,value))return;
        Map r=new LinkedHashMap();r.put("path",path);r.put("owner",PlannedServiceAgent.Recorder.id(owner));r.put("field",field);
        r.put("version",field.startsWith("@")?CollectionServiceHooks.epoch(owner):PlannedServiceAgent.Recorder.VERSIONS.getOrDefault(PlannedServiceAgent.Recorder.id(owner)+":"+field,0));
        r.put("observed",PlannedServiceAgent.Recorder.value(value));if(anchor!=null)r.put("schema_field",anchor);result.add(r);
    }
    static void walk(Object o,String path,String anchor,List<Map> result,IdentityHashMap<Object,Boolean> seen,int depth,boolean target,SnapshotPolicy policy,List<Map> wrappers)throws Exception{
        if(o==null||SpringTransportAgent.Transport.primitive(o)||o.getClass().getName().equals("org.springframework.http.HttpHeaders"))return;
        if(depth>12||result.size()>10000)throw new IllegalStateException("Binding snapshot bound");
        if(seen.put(o,true)!=null)throw new IllegalStateException("Binding object cycle");
        try{
            if(o instanceof List){if(!Arrays.asList("java.util.ArrayList","java.util.Arrays$ArrayList","java.util.Collections$SingletonList","java.util.Collections$EmptyList").contains(o.getClass().getName()))throw new IllegalStateException("Unmodeled binding List type");
                if(sourceCapture)CollectionServiceHooks.received(o);
                int i=0;for(Object x:(List)o){String p=path+"/"+i;if(SpringTransportAgent.Transport.primitive(x)&&anchor!=null)leaf(o,"@list:"+i,x,p,anchor,result,target,policy);else walk(x,p,anchor,result,seen,depth+1,target,policy,wrappers);i++;}return;}
            if(o instanceof Map){mapWrapper(o,target,wrappers);
                if(sourceCapture)CollectionServiceHooks.received(o);
                List<Map.Entry> actual=new ArrayList<>();if(o.getClass()!=HashMap.class&&o.getClass()!=LinkedHashMap.class)actual=wrapperEntries(o,wrappers);
                else for(Object k:((Map)o).keySet()){if(!(k instanceof String))throw new IllegalStateException("Non-string binding key");actual.add(new AbstractMap.SimpleImmutableEntry(k,((Map)o).get(k)));}
                for(Map.Entry pair:actual){Object k=pair.getKey(),v=pair.getValue();String p=path+"/"+SpringTransportAgent.Transport.escape((String)k);
                    if(SpringTransportAgent.Transport.primitive(v)&&anchor!=null)leaf(o,"@map:"+k,v,p,anchor,result,target,policy);else walk(v,p,anchor,result,seen,depth+1,target,policy,wrappers);}return;}
            Map schema=(Map)PlannedServiceAgent.plan.get("response_graph_schema");List<Map> props=(List<Map>)schema.get(o.getClass().getName().replace('.','/'));if(props==null)return;
            if(!PlannedServiceAgent.Recorder.CHECKED_CLASSES.contains(o.getClass().getName().replace('.','/')))throw new IllegalStateException("Binding DTO was loaded without frozen-class instrumentation check");
            for(Map p:props){String field=(String)p.get("field");if(!target&&policy!=null&&policy.scalar(p))continue;Field f=o.getClass().getDeclaredField(field.substring(field.lastIndexOf('.')+1));f.setAccessible(true);Object value=f.get(o);String next=path+"/"+SpringTransportAgent.Transport.escape((String)p.get("property"));
                if(SpringTransportAgent.Transport.primitive(value))leaf(o,field,value,next,null,result,target,policy);else walk(value,next,field,result,seen,depth+1,target,policy,wrappers);}
        }finally{seen.remove(o);}
    }
    static List<Map> sourceSnapshot(Object value)throws Exception{boolean old=sourceCapture;sourceCapture=true;try{return snapshot(value,false);}finally{sourceCapture=old;}}
    static List<Map> sourceSnapshot(Object value,SnapshotPolicy policy)throws Exception{boolean old=sourceCapture;sourceCapture=true;try{return snapshot(value,false,policy);}finally{sourceCapture=old;}}
    static void mark(String kind,String call,Object value)throws Exception{mark(kind,call,value,null);}
    static void mark(String kind,String call,Object value,String site)throws Exception{
        Map projection=new LinkedHashMap();SnapshotPolicy policy=new SnapshotPolicy(projection,call,false);
        List<Map> fields;try{fields=kind.equals("binding-source")?sourceSnapshot(value,policy):snapshot(value,false,policy);}
        catch(IllegalStateException unsupported){
            if(!ExecutionKernelHooks.enabled()||!kind.startsWith("binding-opaque")||!"Unmodeled binding Map type".equals(unsupported.getMessage()))throw unsupported;
            // Diagnostic snapshots cannot turn an unsupported callback value
            // into a new business exception. The execution kernel still treats
            // the original invocation and reachable effects as opaque.
            Map r=row();r.put("callee",call);r.put("fields",Collections.emptyList());r.put("opaque_identity",PlannedServiceAgent.Recorder.value(value));r.put("snapshot_unsupported",unsupported.getMessage());emit(kind,r);return;
        }
        if(fields.isEmpty()&&(policy.proof==null||((Map)policy.proof.get("scalar_fields")).isEmpty()&&((Map)policy.proof.get("container_values")).isEmpty()))return;Map r=row();r.put("callee",call);r.put("fields",fields);r.putAll(projection);
        if(kind.equals("binding-source")&&ExecutionKernelHooks.enabled()&&binding().get("source_occurrence_protocol")!=null){
            Map invocation=CollectionServiceHooks.CALLS.get().peek();boolean paired=invocation!=null&&call.equals(invocation.get("callee"))&&Objects.equals(r.get("frame"),invocation.get("frame"));
            if(((Number)binding().get("source_occurrence_protocol")).intValue()>=2)paired=paired&&Objects.equals(site,invocation.get("method")+"@"+invocation.get("pc"));
            r.put("source_callsite",site);
            r.put("source_call_id",paired?invocation.get("call_id"):null);r.put("source_caller_method",paired?invocation.get("method"):null);r.put("source_pc",paired?invocation.get("pc"):null);r.put("source_scope",paired?"planned-call":"unscoped-fact-only");if(!paired&&SourceObservationHooks.bind(r,site,call))r.put("source_result",PlannedServiceAgent.Recorder.value(value));
        }
        emit(kind,r);
    }
    public static void before(String call,Object recv,Object[] args){synchronized(PlannedServiceAgent.Recorder.class){if(!active())return;try{if(ReadEffectHooks.enabled()){ReadEffectHooks.before(call,recv,args);return;}if(admitted(call,recv))return;mark("binding-opaque-touch",call,recv);for(Object a:args)mark("binding-opaque-touch",call,a);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("binding-before:"+e);throw new IllegalStateException(e);}}}
    public static void after(String call,Object recv,Object[] args,Object result){afterAt(null,call,recv,args,result);}
    public static void afterAt(String site,String call,Object recv,Object[] args,Object result){synchronized(PlannedServiceAgent.Recorder.class){if(!active())return;try{
        TemporalDateHooks.bindingCall(call,recv,args,result);
        if(ReadEffectHooks.enabled()){ReadEffectHooks.after(call,recv,args,result);return;}
        if(((List)binding().get("source_calls")).contains(call)){mark("binding-source",call,result,site);}
        else if(!admitted(call,recv))mark("binding-opaque-result",call,result);
    }catch(Throwable e){PlannedServiceAgent.Recorder.problem("binding-after:"+e);throw new IllegalStateException(e);}}}
    public static void exceptional(String call,Object recv,Object[] args,Throwable error){synchronized(PlannedServiceAgent.Recorder.class){if(!active())return;try{if(ExecutionKernelHooks.enabled()){SaveEffectHooks.exceptional(call,error);ExecutionKernelHooks.exceptional(call,error);}else if(ReadEffectHooks.enabled())ReadEffectHooks.exceptional(call,recv,args,error);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("binding-exceptional:"+e);throw new IllegalStateException(e);}}}
    static void abort()throws Exception{if(enabled()&&ReadEffectHooks.enabled())ReadEffectHooks.abort();}
    static void enter(Object[] args)throws Exception{if(!enabled())return;TemporalDateHooks.enter();UuidProjectionHooks.enter();if(ExecutionKernelHooks.enabled())ExecutionKernelHooks.enter();if(ReadEffectHooks.enabled())ReadEffectHooks.enter();for(int i=0;i<args.length;i++){if(!((List)binding().get("source_arguments")).contains(i))continue;Map r=row();r.put("argument",i);SnapshotPolicy policy=new SnapshotPolicy(r,null,true);r.put("fields",sourceSnapshot(args[i],policy));emit("binding-input",r);}}
    static void rememberReturn(String message){MonitorSafety.rememberReturn(message);RETURN_MESSAGES.add(message);}
    static void exit(Object result)throws Exception{if(!enabled())return;if(ReadEffectHooks.enabled())ReadEffectHooks.exit(result);Map r=row();if(r.get("message")!=null)rememberReturn((String)r.get("message"));r.put("result",PlannedServiceAgent.Recorder.value(result));List<Map> wrappers=new ArrayList<>();r.put("fields",snapshot(result,true,null,wrappers));if(PlannedServiceAgent.plan.get("map_wrapper_observation")!=null)r.put("map_wrappers",wrappers);emit("binding-return",r);}
    static Object member(Object object,String name)throws Exception{for(Class c=object.getClass();c!=null;c=c.getSuperclass())try{Field f=c.getDeclaredField(name);f.setAccessible(true);return f.get(object);}catch(NoSuchFieldException e){}throw new IllegalStateException("Serializer structure unsupported: "+name);}
    static void serializer(Object serializer,Object value)throws Exception{
        if(serializer==null)return;String name=serializer.getClass().getName();
        Set<String> allowed=new HashSet<>(Arrays.asList("com.fasterxml.jackson.databind.ser.BeanSerializer",
          "com.fasterxml.jackson.databind.ser.std.StringSerializer","com.fasterxml.jackson.databind.ser.std.BooleanSerializer",
          "com.fasterxml.jackson.databind.ser.std.NumberSerializers$IntegerSerializer","com.fasterxml.jackson.databind.ser.std.NumberSerializers$LongSerializer",
          "com.fasterxml.jackson.databind.ser.std.NumberSerializers$DoubleSerializer","com.fasterxml.jackson.databind.ser.std.NumberSerializers$FloatSerializer",
          "com.fasterxml.jackson.databind.ser.std.NullSerializer","com.fasterxml.jackson.databind.ser.std.MapSerializer",
          "com.fasterxml.jackson.databind.ser.impl.IndexedListSerializer","com.fasterxml.jackson.databind.ser.impl.IndexedStringListSerializer",
          "com.fasterxml.jackson.databind.ser.impl.StringCollectionSerializer","com.fasterxml.jackson.databind.ser.std.CollectionSerializer"));
        if(ScalarProjectionHooks.config()!=null&&(name.equals("com.fasterxml.jackson.databind.ser.std.NumberSerializer")||name.equals("com.fasterxml.jackson.databind.ser.std.EnumSerializer"))){ScalarProjectionHooks.serializer(serializer,value);return;}
        if(TemporalDateHooks.config()!=null&&name.equals("com.fasterxml.jackson.databind.ser.std.DateSerializer")){TemporalDateHooks.serializer(serializer);return;}
        if(UuidProjectionHooks.config()!=null&&name.equals("com.fasterxml.jackson.databind.ser.std.UUIDSerializer")){UuidProjectionHooks.serializer(serializer);return;}
        if(!allowed.contains(name)||BusinessJackson.yes(BusinessJackson.call(serializer,"usesObjectId")))throw new IllegalStateException("Unmodeled serializer: "+name);
        if(name.endsWith("MapSerializer")){
            Object key=member(serializer,"_keySerializer");if(key!=null&&!key.getClass().getName().equals("com.fasterxml.jackson.databind.ser.std.StdKeySerializers$StringKeySerializer"))throw new IllegalStateException("Custom map-key serializer");
            Object content=member(serializer,"_valueSerializer");if(content!=null)serializer(content,null);
        }
    }
    public static void verifySerialization(Object body,Object mapper)throws Exception{
        if(!enabled())return;
        synchronized(PlannedServiceAgent.Recorder.class){if(!RETURN_MESSAGES.contains(row().get("message")))return;}
        String[] target=((String)binding().get("path")).split("/");boolean applicable=false;
        for(Object raw:SpringTransportAgent.Transport.snapshot(body)){String[] actual=((String)((Map)raw).get("path")).split("/");if(actual.length!=target.length)continue;boolean equal=true;for(int i=0;i<actual.length;i++)if(!target[i].equals(actual[i])&&!(target[i].equals("*")&&actual[i].matches("[0-9]+")))equal=false;if(equal)applicable=true;}
        if(!applicable)return;
        BusinessJackson.mapper(mapper);
        Object actual=mapper;
        if(BusinessJackson.call(actual,"getPropertyNamingStrategy")!=null||BusinessJackson.call(BusinessJackson.call(actual,"getSerializationConfig"),"getActiveView")!=null||BusinessJackson.call(BusinessJackson.call(actual,"getSerializationConfig"),"getFilterProvider")!=null)throw new IllegalStateException("Dynamic serialization configuration unsupported");
        checkPath(body,actual,((String)binding().get("path")).substring(1).split("/"),0);
    }
    static void checkPath(Object value,Object mapper,String[] path,int index)throws Exception{
        if(value!=null&&UuidProjectionHooks.config()!=null&&BusinessJackson.call(mapper,"findMixInClassFor",value.getClass())!=null)throw new IllegalStateException("UUID path mix-in unsupported");
        if(value==null)return;serializer(BusinessJackson.call(BusinessJackson.call(mapper,"getSerializerProviderInstance"),"findValueSerializer",value.getClass()),value);
        if(index==path.length){ScalarProjectionHooks.serialization(value,mapper);if(UuidProjectionHooks.uuid(value))UuidProjectionHooks.serialization((java.util.UUID)value,mapper);if(TemporalDateHooks.date(value))TemporalDateHooks.serialization((java.util.Date)value,mapper);return;}String part=path[index].replace("~1","/").replace("~0","~");
        if(value instanceof List){if(part.equals("*")){for(Object x:(List)value)checkPath(x,mapper,path,index+1);}else{int at=Integer.parseInt(part);if(at<((List)value).size())checkPath(((List)value).get(at),mapper,path,index+1);}return;}
        if(value instanceof Map){Object key=BusinessJackson.call(BusinessJackson.call(mapper,"getSerializerProviderInstance"),"findKeySerializer",BusinessJackson.call(mapper,"constructType",String.class),null);if(!key.getClass().getName().equals("com.fasterxml.jackson.databind.ser.std.StdKeySerializers$StringKeySerializer"))throw new IllegalStateException("Custom map-key serializer");if(((Map)value).containsKey(part))checkPath(((Map)value).get(part),mapper,path,index+1);return;}
        if(BusinessJackson.call(mapper,"findMixInClassFor",value.getClass())!=null)throw new IllegalStateException("Serialization mix-in unsupported");
        Object ser=BusinessJackson.call(BusinessJackson.call(mapper,"getSerializerProviderInstance"),"findValueSerializer",value.getClass());
        if(!BusinessJackson.exact(ser,"ser.BeanSerializer")||member(ser,"_propertyFilterId")!=null||member(ser,"_anyGetterWriter")!=null)throw new IllegalStateException("Unmodeled bean serializer effects");
        List<Map<String,Object>> props=SpringTransportAgent.Transport.schema.get(value.getClass().getName().replace('.','/'));Map prop=null;
        if(props!=null)for(Map p:props)if(part.equals(p.get("property")))prop=p;
        if(prop==null)throw new IllegalStateException("Unverified serialized property: "+part);
        Iterator writers=(Iterator)BusinessJackson.call(ser,"properties");List<Object> matched=new ArrayList<>();
        while(writers.hasNext()){Object writer=writers.next();if(BusinessJackson.call(writer,"getName").equals(part)){if(!BusinessJackson.exact(writer,"ser.BeanPropertyWriter"))throw new IllegalStateException("Custom property writer");matched.add(writer);}}
        if(matched.size()!=1)throw new IllegalStateException("Serialized property absent or ambiguous");Object writer=matched.get(0);
        String field=(String)prop.get("field");String name=field.substring(field.lastIndexOf('.')+1);java.lang.reflect.Member used=(java.lang.reflect.Member)BusinessJackson.call(BusinessJackson.call(writer,"getMember"),"getMember");String getter=(String)prop.get("getter");
        if(used instanceof java.lang.reflect.Method){if(getter==null||!getter.contains("."+used.getName()+"("))throw new IllegalStateException("Serializer getter differs from frozen direct getter");}
        else if(!(used instanceof Field)||!used.getName().equals(name))throw new IllegalStateException("Serializer field differs");
        Field f=value.getClass().getDeclaredField(name);f.setAccessible(true);Object child=f.get(value);
        if(BusinessJackson.call(writer,"getTypeSerializer")!=null||member(writer,"_suppressableValue")!=null||BusinessJackson.yes(BusinessJackson.call(writer,"willSuppressNulls"))&&child==null)throw new IllegalStateException("Polymorphic or suppressing property serialization unsupported");
        serializer(BusinessJackson.call(writer,"getSerializer"),ScalarProjectionHooks.config()!=null&&(child instanceof java.math.BigDecimal||ScalarProjectionHooks.enumeration(child))?child:null);Object nullSer=member(writer,"_nullSerializer");if(nullSer!=null)serializer(nullSer,null);
        checkPath(child,mapper,path,index+1);
    }
}
