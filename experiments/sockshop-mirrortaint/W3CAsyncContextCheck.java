import java.util.concurrent.*;

/** Reused worker, failure and absent-parent checks against the real wrapper. */
public final class W3CAsyncContextCheck {
    static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);}
    public static void main(String[] args)throws Exception{
        final W3CTraceContext caller=W3CTraceContext.server("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01","v=x");
        final W3CTraceContext previous=W3CTraceContext.server(null,null);
        ExecutorService worker=Executors.newSingleThreadExecutor();
        try{
            worker.submit(()->SpringTransportAgent.Transport.ASYNC.set(previous)).get();
            SpringTransportAgent.Transport.ASYNC.set(caller);
            Callable<Object> success=SpringTransportAgent.Transport.wrap(()->{
                check(SpringTransportAgent.Transport.current()==caller,"Parent lost on worker");return "ok";
            });
            check(worker.submit(success).get().equals("ok"),"Result changed");
            check(worker.submit(()->SpringTransportAgent.Transport.current()==previous).get(),"Worker context not restored after success");
            Callable<Object> failure=SpringTransportAgent.Transport.wrap(()->{throw new IllegalArgumentException("expected-task-failure");});
            try{worker.submit(failure).get();throw new AssertionError("Failure swallowed");}catch(ExecutionException expected){check(expected.getCause() instanceof IllegalArgumentException,"Failure changed");}
            check(worker.submit(()->SpringTransportAgent.Transport.current()==previous).get(),"Worker context not restored after failure");
            SpringTransportAgent.Transport.ASYNC.remove();
            Callable<Object> absent=SpringTransportAgent.Transport.wrap(()->{check(SpringTransportAgent.Transport.current()==null,"Foreign context leaked into root task");return null;});
            worker.submit(absent).get();
            check(worker.submit(()->SpringTransportAgent.Transport.current()==previous).get(),"Worker context not restored after root task");
            System.out.println("Async context capture, worker reuse, exception and absent-parent restoration checks passed");
        }finally{SpringTransportAgent.Transport.ASYNC.remove();worker.shutdownNow();}
    }
}
