import java.lang.reflect.*;
import java.util.*;
import org.objectweb.asm.Type;

/** Finite read-effect contracts. No provenance is created by these checks. */
public final class ReadEffectHooks {
    static long serial=0;
    static class State {String id,call,mode,implementation;Object recv;Object[] args;long failures;Map detail=new LinkedHashMap();List<Map> before=new ArrayList<>();}
    static class StreamFact {List source;Object[] elements;StreamFact(List l){source=l;elements=l.toArray();}}
    static final ThreadLocal<Map<Object,StreamFact>> STREAMS=new ThreadLocal<Map<Object,StreamFact>>(){protected Map<Object,StreamFact> initialValue(){return new IdentityHashMap<>();}};
    static final ThreadLocal<Map<Object,Object>> OPTIONALS=new ThreadLocal<Map<Object,Object>>(){protected Map<Object,Object> initialValue(){return new IdentityHashMap<>();}};
    static Map RUNTIME;
    static final ThreadLocal<Deque<State>> STACK=new ThreadLocal<Deque<State>>(){protected Deque<State> initialValue(){return new ArrayDeque<>();}};
    static final ThreadLocal<long[]> COUNTS=new ThreadLocal<long[]>(){protected long[] initialValue(){return new long[3];}};
    static Map config(){return (Map)PlannedServiceAgent.plan.get("read_forward_contracts");}
    static boolean enabled(){return config()!=null;}
    static List<Map> fields(Object recv,Object[] args)throws Exception{List<Map> r=new ArrayList<>();r.addAll(ResponseBindingHooks.snapshot(recv,false));for(Object a:args)r.addAll(ResponseBindingHooks.snapshot(a,false));return r;}
    static List compact(List<Map> fields){List r=new ArrayList();for(Map f:fields)r.add(Arrays.asList(f.get("owner"),f.get("field"),f.get("version"),((Map)f.get("observed")).get("value")));return r;}
    static String implementation(String call,Object recv){
        String own=call.substring(0,call.indexOf('.'));String name=call.substring(call.indexOf('.')+1,call.indexOf('('));String desc=call.substring(call.indexOf('('));
        if(recv==null)return call;
        for(Class c=recv.getClass();c!=null;c=c.getSuperclass())for(Method m:c.getDeclaredMethods())
            if(m.getName().equals(name)&&Type.getMethodDescriptor(m).equals(desc))return c.getName().replace('.','/')+"."+name+desc;
        return null;
    }
    static boolean list(Object o){return o!=null&&Arrays.asList("java.util.ArrayList","java.util.Arrays$ArrayList","java.util.Collections$SingletonList","java.util.Collections$EmptyList").contains(o.getClass().getName());}
    static String mode(State s){
        if(ResponseBindingHooks.admitted(s.call,s.recv)){
            String owner=s.call.substring(0,s.call.indexOf('.'));
            if(s.recv==null||!PlannedServiceAgent.hashes.containsKey(owner)||((List)ResponseBindingHooks.binding().get("source_calls")).contains(s.call)||s.call.equals(implementation(s.call,s.recv)))return "existing";
        }
        if(s.call.equals("java/util/Collection.stream()Ljava/util/stream/Stream;")||s.call.equals("java/util/List.stream()Ljava/util/stream/Stream;")){
            if(list(s.recv)){s.detail.put("element_ids",ids(((List)s.recv).toArray()));return "list-stream";}
        }
        if(s.call.equals("java/util/stream/Stream.findFirst()Ljava/util/Optional;")&&STREAMS.get().containsKey(s.recv))return "stream-first";
        if(s.call.equals("java/util/Optional.orElseGet(Ljava/util/function/Supplier;)Ljava/lang/Object;")&&s.recv!=null&&s.recv.getClass()==Optional.class&&((Optional)s.recv).isPresent()&&OPTIONALS.get().get(s.recv)==((Optional)s.recv).get()){
            s.detail.put("selected_object",PlannedServiceAgent.Recorder.id(((Optional)s.recv).get()));return "optional-present";
        }
        String actual=implementation(s.call,s.recv);
        if(actual!=null&&((List)config().get("composed_methods")).contains(actual)&&PlannedServiceAgent.Recorder.CHECKED_CLASSES.contains(actual.substring(0,actual.indexOf('.')))){
            s.implementation=actual;return "composed";
        }
        return "opaque";
    }
    static List ids(Object[] xs){List r=new ArrayList();for(Object x:xs)r.add(PlannedServiceAgent.Recorder.id(x));return r;}
    static void mark(State s,Object result)throws Exception{
        if(!s.before.isEmpty()){Map row=ResponseBindingHooks.row();row.put("callee",s.call);row.put("fields",s.before);ResponseBindingHooks.emit("binding-opaque-touch",row);}
        ResponseBindingHooks.mark("binding-opaque-result",s.call,result);
    }
    static void fail(State s,Object result)throws Exception{COUNTS.get()[0]++;mark(s,result);}
    static void emit(String kind,State s,boolean valid)throws Exception{Map r=ResponseBindingHooks.row();r.put("call_id",s.id);r.put("callee",s.call);r.put("mode",s.mode);r.put("implementation",s.implementation);r.put("receiver",PlannedServiceAgent.Recorder.id(s.recv));r.put("receiver_type",s.recv==null?null:s.recv.getClass().getName());r.put("valid",valid);r.put("detail",s.detail);ResponseBindingHooks.emit(kind,r);}
    static void enter()throws Exception{
        if(!STACK.get().isEmpty())throw new IllegalStateException("Read-effect root overlaps unfinished calls");
        COUNTS.set(new long[3]);STREAMS.get().clear();OPTIONALS.get().clear();
        if(RUNTIME==null){Map hashes=JdkContractProbe.hashes();String version=System.getProperty("java.runtime.version");boolean valid=false;
            for(Object raw:(List)config().get("runtime_profiles")){Map profile=(Map)raw;if(version.equals(profile.get("java_runtime_version"))&&hashes.equals(profile.get("class_sha256")))valid=true;}
            if(!valid)throw new IllegalStateException("Unmodeled JDK read-effect runtime");
            RUNTIME=new LinkedHashMap();RUNTIME.put("java_runtime_version",version);RUNTIME.put("class_sha256",hashes);
            Map row=ResponseBindingHooks.row();row.putAll(RUNTIME);ResponseBindingHooks.emit("binding-call-runtime",row);
        }
    }
    static void before(String call,Object recv,Object[] args)throws Exception{
        State s=new State();s.id="c"+(++serial);s.call=call;s.recv=recv;s.args=args;s.before=fields(recv,args);s.mode=mode(s);s.failures=COUNTS.get()[0];
        STACK.get().push(s);COUNTS.get()[1]++;emit("binding-call-enter",s,true);
        if(s.mode.equals("opaque"))fail(s,null);
    }
    static void after(String call,Object recv,Object[] args,Object result)throws Exception{
        if(STACK.get().isEmpty()||!STACK.get().peek().call.equals(call)||STACK.get().peek().recv!=recv){COUNTS.get()[0]++;COUNTS.get()[2]++;ResponseBindingHooks.mark("binding-opaque-result",call,result);return;}
        State s=STACK.get().pop();boolean valid=!s.mode.equals("opaque");
        if(s.mode.equals("composed"))valid=s.failures==COUNTS.get()[0]&&compact(s.before).equals(compact(fields(recv,args)));
        if(s.mode.equals("list-stream")){
            valid=result!=null&&result.getClass().getName().equals("java.util.stream.ReferencePipeline$Head")&&((java.util.stream.Stream)result).isParallel()==false&&s.detail.get("element_ids").equals(ids(((List)recv).toArray()));
            if(valid)STREAMS.get().put(result,new StreamFact((List)recv));
        }
        if(s.mode.equals("stream-first")){
            StreamFact f=STREAMS.get().remove(recv);valid=f!=null&&result!=null&&result.getClass()==Optional.class&&ids(f.elements).equals(ids(f.source.toArray()));
            if(valid){Optional o=(Optional)result;valid=o.isPresent()==(f.elements.length>0)&&(!o.isPresent()||o.get()==f.elements[0]);s.detail.put("element_ids",ids(f.elements));s.detail.put("selected_object",o.isPresent()?PlannedServiceAgent.Recorder.id(o.get()):null);s.detail.put("present",o.isPresent());if(valid&&o.isPresent())OPTIONALS.get().put(o,o.get());}
        }
        if(s.mode.equals("optional-present"))valid=((Optional)recv).isPresent()&&result==((Optional)recv).get()&&s.detail.get("selected_object").equals(PlannedServiceAgent.Recorder.id(result));
        s.detail.put("result_object",PlannedServiceAgent.Recorder.id(result));
        List<Map> effectFields=new ArrayList<>(s.before);effectFields.addAll(ResponseBindingHooks.snapshot(result,false));s.detail.put("effect_fields",effectFields);
        if(((List)ResponseBindingHooks.binding().get("source_calls")).contains(call))ResponseBindingHooks.mark("binding-source",call,result);
        if(!valid)fail(s,result);
        s.detail.put("completion","normal");emit("binding-call-exit",s,valid);
    }
    static void exceptional(String call,Object recv,Object[] args,Throwable error)throws Exception{
        if(STACK.get().isEmpty()||!STACK.get().peek().call.equals(call)||STACK.get().peek().recv!=recv)throw new IllegalStateException("Read-effect exceptional completion has no matching invocation");
        State s=STACK.get().pop();s.detail.put("completion","exceptional");
        s.detail.put("exception_object",PlannedServiceAgent.Recorder.id(error));s.detail.put("exception_type",error.getClass().getName());
        s.detail.put("effect_fields",s.before);fail(s,null);emit("binding-call-throw",s,false);
    }
    static void exit(Object result)throws Exception{
        finish(result,"normal");
    }
    static void abort()throws Exception{finish(null,"exceptional");}
    static void finish(Object result,String completion)throws Exception{
        if(!STACK.get().isEmpty()||COUNTS.get()[2]>0){COUNTS.get()[0]++;ResponseBindingHooks.mark("binding-opaque-result","unpaired-executed-call",result);}
        boolean rootVerified=((List)config().get("composed_methods")).contains(PlannedServiceAgent.plan.get("entry"));
        if(TemporalDateHooks.config()!=null&&COUNTS.get()[0]>0)rootVerified=false;
        if(!rootVerified)ResponseBindingHooks.mark("binding-opaque-result","root-effects-including-constructors-not-proved",result);
        Map r=ResponseBindingHooks.row();r.put("completion",completion);r.put("calls",COUNTS.get()[1]);r.put("unpaired",STACK.get().size()+COUNTS.get()[2]);r.put("root_effects_verified",rootVerified);r.put("fields",ResponseBindingHooks.snapshot(result,false));ResponseBindingHooks.emit("binding-call-summary",r);STACK.get().clear();COUNTS.remove();STREAMS.get().clear();OPTIONALS.get().clear();
    }
}
