import java.lang.reflect.Field;
import java.util.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.ser.*;

/** Root-to-wire identity witnesses and explicitly admitted pre-output sources. */
public final class ResponseBindingHooks implements Opcodes {
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
            arguments(after,call,recv,types,slots);
            if(ret.getSort()==Type.VOID)after.add(new InsnNode(ACONST_NULL));else{after.add(new VarInsnNode(ret.getOpcode(ILOAD),result));PlannedServiceAgent.box(after,ret);}
            after.add(new MethodInsnNode(INVOKESTATIC,R,"after","(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;Ljava/lang/Object;)V",false));
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
    static List<Map> snapshot(Object obj,boolean target)throws Exception{
        List<Map> result=new ArrayList<>();walk(obj,"",null,result,new IdentityHashMap<Object,Boolean>(),0,target);return result;
    }
    static void leaf(Object owner,String field,Object value,String path,String anchor,List<Map> result,boolean target){
        List wanted=target?Collections.singletonList(binding().get("target")):(List)binding().get("source_fields");
        boolean dynamic=target&&Boolean.TRUE.equals(binding().get("runtime_container_path"))&&field.startsWith("@")&&path.equals(binding().get("path"));
        if(!dynamic&&!wanted.contains(anchor==null?field:anchor))return;
        Map r=new LinkedHashMap();r.put("path",path);r.put("owner",PlannedServiceAgent.Recorder.id(owner));r.put("field",field);
        r.put("version",field.startsWith("@")?CollectionServiceHooks.epoch(owner):PlannedServiceAgent.Recorder.VERSIONS.getOrDefault(PlannedServiceAgent.Recorder.id(owner)+":"+field,0));
        r.put("observed",PlannedServiceAgent.Recorder.value(value));if(anchor!=null)r.put("schema_field",anchor);result.add(r);
    }
    static void walk(Object o,String path,String anchor,List<Map> result,IdentityHashMap<Object,Boolean> seen,int depth,boolean target)throws Exception{
        if(o==null||SpringTransportAgent.Transport.primitive(o)||o.getClass().getName().equals("org.springframework.http.HttpHeaders"))return;
        if(depth>12||result.size()>10000)throw new IllegalStateException("Binding snapshot bound");
        if(seen.put(o,true)!=null)throw new IllegalStateException("Binding object cycle");
        try{
            if(o instanceof List){if(!Arrays.asList("java.util.ArrayList","java.util.Arrays$ArrayList","java.util.Collections$SingletonList","java.util.Collections$EmptyList").contains(o.getClass().getName()))throw new IllegalStateException("Unmodeled binding List type");
                if(sourceCapture)CollectionServiceHooks.received(o);
                int i=0;for(Object x:(List)o){String p=path+"/"+i;if(SpringTransportAgent.Transport.primitive(x)&&anchor!=null)leaf(o,"@list:"+i,x,p,anchor,result,target);else walk(x,p,anchor,result,seen,depth+1,target);i++;}return;}
            if(o instanceof Map){if(o.getClass()!=HashMap.class&&o.getClass()!=LinkedHashMap.class)throw new IllegalStateException("Unmodeled binding Map type");
                if(sourceCapture)CollectionServiceHooks.received(o);
                for(Object k:((Map)o).keySet()){if(!(k instanceof String))throw new IllegalStateException("Non-string binding key");Object v=((Map)o).get(k);String p=path+"/"+SpringTransportAgent.Transport.escape((String)k);
                    if(SpringTransportAgent.Transport.primitive(v)&&anchor!=null)leaf(o,"@map:"+k,v,p,anchor,result,target);else walk(v,p,anchor,result,seen,depth+1,target);}return;}
            Map schema=(Map)PlannedServiceAgent.plan.get("response_graph_schema");List<Map> props=(List<Map>)schema.get(o.getClass().getName().replace('.','/'));if(props==null)return;
            if(!PlannedServiceAgent.Recorder.CHECKED_CLASSES.contains(o.getClass().getName().replace('.','/')))throw new IllegalStateException("Binding DTO was loaded without frozen-class instrumentation check");
            for(Map p:props){String field=(String)p.get("field");Field f=o.getClass().getDeclaredField(field.substring(field.lastIndexOf('.')+1));f.setAccessible(true);Object value=f.get(o);String next=path+"/"+SpringTransportAgent.Transport.escape((String)p.get("property"));
                if(SpringTransportAgent.Transport.primitive(value))leaf(o,field,value,next,null,result,target);else walk(value,next,field,result,seen,depth+1,target);}
        }finally{seen.remove(o);}
    }
    static List<Map> sourceSnapshot(Object value)throws Exception{boolean old=sourceCapture;sourceCapture=true;try{return snapshot(value,false);}finally{sourceCapture=old;}}
    static void mark(String kind,String call,Object value)throws Exception{
        List<Map> fields;try{fields=kind.equals("binding-source")?sourceSnapshot(value):snapshot(value,false);}
        catch(IllegalStateException unsupported){
            if(!ExecutionKernelHooks.enabled()||!kind.startsWith("binding-opaque")||!"Unmodeled binding Map type".equals(unsupported.getMessage()))throw unsupported;
            // Diagnostic snapshots cannot turn an unsupported callback value
            // into a new business exception. The execution kernel still treats
            // the original invocation and reachable effects as opaque.
            Map r=row();r.put("callee",call);r.put("fields",Collections.emptyList());r.put("opaque_identity",PlannedServiceAgent.Recorder.value(value));r.put("snapshot_unsupported",unsupported.getMessage());emit(kind,r);return;
        }
        if(fields.isEmpty())return;Map r=row();r.put("callee",call);r.put("fields",fields);emit(kind,r);
    }
    public static void before(String call,Object recv,Object[] args){synchronized(PlannedServiceAgent.Recorder.class){if(!active())return;try{if(ReadEffectHooks.enabled()){ReadEffectHooks.before(call,recv,args);return;}if(admitted(call,recv))return;mark("binding-opaque-touch",call,recv);for(Object a:args)mark("binding-opaque-touch",call,a);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("binding-before:"+e);throw new IllegalStateException(e);}}}
    public static void after(String call,Object recv,Object[] args,Object result){synchronized(PlannedServiceAgent.Recorder.class){if(!active())return;try{
        TemporalDateHooks.bindingCall(call,recv,args,result);
        if(ReadEffectHooks.enabled()){ReadEffectHooks.after(call,recv,args,result);return;}
        if(((List)binding().get("source_calls")).contains(call)){mark("binding-source",call,result);}
        else if(!admitted(call,recv))mark("binding-opaque-result",call,result);
    }catch(Throwable e){PlannedServiceAgent.Recorder.problem("binding-after:"+e);throw new IllegalStateException(e);}}}
    public static void exceptional(String call,Object recv,Object[] args,Throwable error){synchronized(PlannedServiceAgent.Recorder.class){if(!active())return;try{if(ExecutionKernelHooks.enabled()){SaveEffectHooks.exceptional(call,error);ExecutionKernelHooks.exceptional(call,error);}else if(ReadEffectHooks.enabled())ReadEffectHooks.exceptional(call,recv,args,error);}catch(Throwable e){PlannedServiceAgent.Recorder.problem("binding-exceptional:"+e);throw new IllegalStateException(e);}}}
    static void abort()throws Exception{if(enabled()&&ReadEffectHooks.enabled())ReadEffectHooks.abort();}
    static void enter(Object[] args)throws Exception{if(!enabled())return;TemporalDateHooks.enter();if(ExecutionKernelHooks.enabled())ExecutionKernelHooks.enter();if(ReadEffectHooks.enabled())ReadEffectHooks.enter();for(int i=0;i<args.length;i++){if(!((List)binding().get("source_arguments")).contains(i))continue;Map r=row();r.put("argument",i);r.put("fields",sourceSnapshot(args[i]));emit("binding-input",r);}}
    static void exit(Object result)throws Exception{if(!enabled())return;if(ReadEffectHooks.enabled())ReadEffectHooks.exit(result);Map r=row();if(r.get("message")!=null)RETURN_MESSAGES.add((String)r.get("message"));r.put("result",PlannedServiceAgent.Recorder.value(result));r.put("fields",snapshot(result,true));emit("binding-return",r);}
    static Object member(Object object,String name)throws Exception{for(Class c=object.getClass();c!=null;c=c.getSuperclass())try{Field f=c.getDeclaredField(name);f.setAccessible(true);return f.get(object);}catch(NoSuchFieldException e){}throw new IllegalStateException("Serializer structure unsupported: "+name);}
    static void serializer(JsonSerializer serializer,Object value)throws Exception{
        if(serializer==null)return;String name=serializer.getClass().getName();
        Set<String> allowed=new HashSet<>(Arrays.asList("com.fasterxml.jackson.databind.ser.BeanSerializer",
          "com.fasterxml.jackson.databind.ser.std.StringSerializer","com.fasterxml.jackson.databind.ser.std.BooleanSerializer",
          "com.fasterxml.jackson.databind.ser.std.NumberSerializers$IntegerSerializer","com.fasterxml.jackson.databind.ser.std.NumberSerializers$LongSerializer",
          "com.fasterxml.jackson.databind.ser.std.NumberSerializers$DoubleSerializer","com.fasterxml.jackson.databind.ser.std.NumberSerializers$FloatSerializer",
          "com.fasterxml.jackson.databind.ser.std.NullSerializer","com.fasterxml.jackson.databind.ser.std.MapSerializer",
          "com.fasterxml.jackson.databind.ser.impl.IndexedListSerializer","com.fasterxml.jackson.databind.ser.impl.IndexedStringListSerializer",
          "com.fasterxml.jackson.databind.ser.impl.StringCollectionSerializer","com.fasterxml.jackson.databind.ser.std.CollectionSerializer"));
        if(TemporalDateHooks.config()!=null&&name.equals("com.fasterxml.jackson.databind.ser.std.DateSerializer")){TemporalDateHooks.serializer(serializer);return;}
        if(!allowed.contains(name)||serializer.usesObjectId())throw new IllegalStateException("Unmodeled serializer: "+name);
        if(name.endsWith("MapSerializer")){
            Object key=member(serializer,"_keySerializer");if(key!=null&&!key.getClass().getName().equals("com.fasterxml.jackson.databind.ser.std.StdKeySerializers$StringKeySerializer"))throw new IllegalStateException("Custom map-key serializer");
            Object content=member(serializer,"_valueSerializer");if(content!=null)serializer((JsonSerializer)content,null);
        }
    }
    public static void verifySerialization(Object body,Object mapper)throws Exception{
        if(!enabled())return;
        synchronized(PlannedServiceAgent.Recorder.class){if(!RETURN_MESSAGES.contains(row().get("message")))return;}
        String[] target=((String)binding().get("path")).split("/");boolean applicable=false;
        for(Object raw:SpringTransportAgent.Transport.snapshot(body)){String[] actual=((String)((Map)raw).get("path")).split("/");if(actual.length!=target.length)continue;boolean equal=true;for(int i=0;i<actual.length;i++)if(!target[i].equals(actual[i])&&!(target[i].equals("*")&&actual[i].matches("[0-9]+")))equal=false;if(equal)applicable=true;}
        if(!applicable)return;
        if(mapper.getClass()!=ObjectMapper.class)throw new IllegalStateException("Unmodeled ObjectMapper subclass");
        ObjectMapper actual=(ObjectMapper)mapper;
        if(actual.getPropertyNamingStrategy()!=null||actual.getSerializationConfig().getActiveView()!=null||actual.getSerializationConfig().getFilterProvider()!=null)throw new IllegalStateException("Dynamic serialization configuration unsupported");
        checkPath(body,actual,((String)binding().get("path")).substring(1).split("/"),0);
    }
    static void checkPath(Object value,ObjectMapper mapper,String[] path,int index)throws Exception{
        if(value==null)return;serializer(mapper.getSerializerProviderInstance().findValueSerializer(value.getClass()),value);
        if(index==path.length){if(TemporalDateHooks.date(value))TemporalDateHooks.serialization((java.util.Date)value,mapper);return;}String part=path[index].replace("~1","/").replace("~0","~");
        if(value instanceof List){if(part.equals("*")){for(Object x:(List)value)checkPath(x,mapper,path,index+1);}else{int at=Integer.parseInt(part);if(at<((List)value).size())checkPath(((List)value).get(at),mapper,path,index+1);}return;}
        if(value instanceof Map){JsonSerializer key=mapper.getSerializerProviderInstance().findKeySerializer(mapper.constructType(String.class),null);if(!key.getClass().getName().equals("com.fasterxml.jackson.databind.ser.std.StdKeySerializers$StringKeySerializer"))throw new IllegalStateException("Custom map-key serializer");if(((Map)value).containsKey(part))checkPath(((Map)value).get(part),mapper,path,index+1);return;}
        if(mapper.findMixInClassFor(value.getClass())!=null)throw new IllegalStateException("Serialization mix-in unsupported");
        JsonSerializer ser=mapper.getSerializerProviderInstance().findValueSerializer(value.getClass());
        if(ser.getClass()!=BeanSerializer.class||member(ser,"_propertyFilterId")!=null||member(ser,"_anyGetterWriter")!=null)throw new IllegalStateException("Unmodeled bean serializer effects");
        List<Map<String,Object>> props=SpringTransportAgent.Transport.schema.get(value.getClass().getName().replace('.','/'));Map prop=null;
        if(props!=null)for(Map p:props)if(part.equals(p.get("property")))prop=p;
        if(prop==null)throw new IllegalStateException("Unverified serialized property: "+part);
        Iterator<PropertyWriter> writers=ser.properties();List<BeanPropertyWriter> matched=new ArrayList<>();
        while(writers.hasNext()){PropertyWriter writer=writers.next();if(writer.getName().equals(part)){if(writer.getClass()!=BeanPropertyWriter.class)throw new IllegalStateException("Custom property writer");matched.add((BeanPropertyWriter)writer);}}
        if(matched.size()!=1)throw new IllegalStateException("Serialized property absent or ambiguous");BeanPropertyWriter writer=matched.get(0);
        String field=(String)prop.get("field");String name=field.substring(field.lastIndexOf('.')+1);java.lang.reflect.Member used=writer.getMember().getMember();String getter=(String)prop.get("getter");
        if(used instanceof java.lang.reflect.Method){if(getter==null||!getter.contains("."+used.getName()+"("))throw new IllegalStateException("Serializer getter differs from frozen direct getter");}
        else if(!(used instanceof Field)||!used.getName().equals(name))throw new IllegalStateException("Serializer field differs");
        Field f=value.getClass().getDeclaredField(name);f.setAccessible(true);Object child=f.get(value);
        if(writer.getTypeSerializer()!=null||member(writer,"_suppressableValue")!=null||writer.willSuppressNulls()&&child==null)throw new IllegalStateException("Polymorphic or suppressing property serialization unsupported");
        serializer(writer.getSerializer(),null);Object nullSer=member(writer,"_nullSerializer");if(nullSer!=null)serializer((JsonSerializer)nullSer,null);
        checkPath(child,mapper,path,index+1);
    }
}
