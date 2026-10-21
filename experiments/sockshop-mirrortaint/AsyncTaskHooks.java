import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;

/** Observational task protocol. Identity checks here never manufacture provenance. */
public final class AsyncTaskHooks {
    static final ThreadLocal<Task> ACTIVE=new ThreadLocal<>();
    static final IdentityHashMap<Object,Task> FUTURES=new IdentityHashMap<>();
    static long next;static boolean runtimeEmitted;
    static Map config(){return (Map)PlannedServiceAgent.plan.get("async_protocol");}
    static boolean enabled(){return config()!=null;}
    static Map value(Object o){return PlannedServiceAgent.Recorder.value(o);}
    static void emit(String kind,Map r){PlannedServiceAgent.Recorder.emit(kind,r);}
    static Map row(Task t){Map r=PlannedServiceAgent.Recorder.row();r.put("task_id",t.id);return r;}
    static Field field(Class c,String name)throws Exception{Field f=c.getDeclaredField(name);f.setAccessible(true);return f;}
    static void runtime()throws Exception{
        if(runtimeEmitted)return;Map r=new LinkedHashMap();r.put("java_runtime_version",System.getProperty("java.runtime.version"));r.put("class_sha256",JdkContractProbe.selected(new String[]{"java/util/concurrent/FutureTask","java/util/concurrent/ExecutionException","java/util/concurrent/CancellationException"}));emit("async-runtime",r);runtimeEmitted=true;
    }
    static void framework(String owner,byte[] bytes)throws Exception{
        if(!enabled())return;Object expected=((Map)config().get("class_sha256")).get(owner);
        if(!Objects.equals(expected,PlannedServiceAgent.Recorder.hash(bytes)))throw new IllegalStateException("Async framework hash differs: "+owner);
        synchronized(PlannedServiceAgent.Recorder.class){Map r=PlannedServiceAgent.Recorder.row();r.put("class",owner);r.put("sha256",expected);emit("async-framework",r);}
    }
    static Callable<Object> wrap(Callable<?> original,Callable<Object> contextual)throws Exception{
        synchronized(PlannedServiceAgent.Recorder.class){runtime();Task t=new Task(original,contextual);Map r=row(t);r.put("callable",value(original));r.put("wrapper",value(t));
            Map current=CollectionServiceHooks.CALLS.get().peek();r.put("parent_call_id",current==null?null:current.get("call_id"));r.put("caller_frame",r.get("frame"));
            String cls=original.getClass().getName().replace('.','/');r.put("callable_class",cls);
            boolean supported=cls.equals("org/springframework/aop/interceptor/AsyncExecutionInterceptor$1");r.put("supported",supported);
            if(supported){Object invocation=field(original.getClass(),"val$invocation").get(original);Method m=(Method)field(original.getClass(),"val$userDeclaredMethod").get(original);Class api=Class.forName("org.aopalliance.intercept.MethodInvocation",false,original.getClass().getClassLoader());Object receiver=api.getMethod("getThis").invoke(invocation);Object[] args=(Object[])api.getMethod("getArguments").invoke(invocation);
                r.put("method",m.getDeclaringClass().getName().replace('.','/')+"."+m.getName()+org.objectweb.asm.Type.getMethodDescriptor(m));r.put("receiver",value(receiver));List observed=new ArrayList();for(Object a:args)observed.add(value(a));r.put("args",observed);r.put("future_return",m.getReturnType()==Future.class);
            }
            emit("async-submit-begin",r);return t;
        }
    }
    public static void submitted(Callable<?> work,Object future){if(!enabled())return;synchronized(PlannedServiceAgent.Recorder.class){try{Task t=(Task)work;Map r=row(t);r.put("future",value(future));r.put("future_class",future==null?null:future.getClass().getName());if(future!=null){if(FUTURES.put(future,t)!=null)throw new IllegalStateException("Future reused by submissions");}emit("async-submit-end",r);}catch(Throwable e){fail(e);}}}
    public static void rejected(Callable<?> work,Throwable error){if(!enabled())return;synchronized(PlannedServiceAgent.Recorder.class){try{Map r=row((Task)work);r.put("exception",value(error));r.put("exception_type",error.getClass().getName());emit("async-submit-throw",r);}catch(Throwable e){fail(e);}}}
    public static void inner(Object result){Task t=ACTIVE.get();if(t==null)return;synchronized(PlannedServiceAgent.Recorder.class){Map r=row(t);r.put("inner",value(result));r.put("inner_class",result==null?null:result.getClass().getName());emit("async-worker-inner",r);}}
    public static void unwrapped(Object result){Task t=ACTIVE.get();if(t==null)return;synchronized(PlannedServiceAgent.Recorder.class){Map r=row(t);r.put("result",value(result));emit("async-worker-unwrapped",r);}}
    static void frame(Map r){Task t=ACTIVE.get();if(t!=null)r.put("async_task_id",t.id);}
    static void completed(Map start,Object result,Throwable error,Map r){
        if(!enabled()||!(start.get("_receiver_ref") instanceof Future))return;String c=(String)start.get("callee");boolean get=c.contains(".get("),cancel=c.contains(".cancel(");if(!get&&!cancel)return;
        Task task=FUTURES.get(start.get("_receiver_ref"));Map a=new LinkedHashMap();a.put("task_id",task==null?null:task.id);a.put("future",value(start.get("_receiver_ref")));a.put("operation",get?"get":"cancel");a.put("completion",error==null?"normal":"exceptional");
        if(error==null)a.put("result",value(result));else{a.put("exception_type",error.getClass().getName());a.put("exception",value(error));if(error instanceof ExecutionException)a.put("cause",value(error.getCause()));}r.put("async_future",a);
    }
    static void fail(Throwable e){PlannedServiceAgent.Recorder.problem("async-protocol:"+e);throw new IllegalStateException(e);}
    static final class Task implements Callable<Object>{
        final long id;final Callable<Object> delegate;
        Task(Callable<?> original,Callable<Object> delegate){id=++next;this.delegate=delegate;}
        public Object call()throws Exception{Task previous=ACTIVE.get();ACTIVE.set(this);synchronized(PlannedServiceAgent.Recorder.class){emit("async-worker-start",row(this));}
            try{Object result=delegate.call();synchronized(PlannedServiceAgent.Recorder.class){Map r=row(this);r.put("result",value(result));emit("async-worker-end",r);}return result;}
            catch(Throwable error){synchronized(PlannedServiceAgent.Recorder.class){Map r=row(this);r.put("exception",value(error));r.put("exception_type",error.getClass().getName());emit("async-worker-throw",r);}if(error instanceof Exception)throw (Exception)error;if(error instanceof Error)throw (Error)error;throw new IllegalStateException(error);}
            finally{if(previous==null)ACTIVE.remove();else ACTIVE.set(previous);}
        }
    }
}
