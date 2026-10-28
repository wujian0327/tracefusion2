import java.net.URI;
import java.util.*;
import java.util.concurrent.Callable;
/** Independent business oracle for framework-owned monitoring boundaries. */
public class MonitorFrameworkReliabilityFixture {
    static final Object RESULT=new Object();static final Exception ORIGINAL=new java.io.IOException("original-worker");static int business;
    static void fault(String name){System.setProperty("service.monitor.test.enabled","true");System.setProperty("service.monitor.test.method","");if(name==null)System.clearProperty("service.monitor.test.fault");else System.setProperty("service.monitor.test.fault",name);}
    static void task(String injected,boolean throwsBusiness,boolean observed)throws Exception{
        Callable<Object> work=()->{business++;if(throwsBusiness)throw ORIGINAL;return RESULT;};
        AsyncTaskHooks.Task previous=null;
        if(observed){previous=new AsyncTaskHooks.Task(work,work);AsyncTaskHooks.ACTIVE.set(previous);work=new AsyncTaskHooks.Task(work,work);}
        fault(injected);boolean same;
        try{same=work.call()==RESULT&&!throwsBusiness;}catch(Exception e){same=e==ORIGINAL&&throwsBusiness;}
        if(!same)throw new AssertionError("Worker result/exception identity changed");
        if(observed){if(AsyncTaskHooks.ACTIVE.get()!=previous)throw new AssertionError("Parent task lost");AsyncTaskHooks.ACTIVE.remove();}
        System.out.println("BUSINESS|"+injected+"|"+throwsBusiness+"|"+business+"|same="+same);
    }
    static void rpc(String injected){
        W3CTraceContext parent=W3CTraceContext.server(null,null);SpringTransportAgent.Transport.SPANS.get().push(parent);Map<String,Object> parentCall=new LinkedHashMap<>();parentCall.put("sentinel",true);SpringTransportAgent.Transport.RPC.get().push(parentCall);
        fault(injected);Object token=SpringTransportAgent.Transport.rpcEnter(URI.create("http://fixture.invalid/"),"GET");
        if("rpc-enter".equals(injected)){if(SpringTransportAgent.Transport.RPC.get().size()!=1)throw new AssertionError("Failed enter retained state");}
        else if(SpringTransportAgent.Transport.RPC.get().size()!=2)throw new AssertionError("RPC entry missing");
        if("rpc-abort".equals(injected))SpringTransportAgent.Transport.rpcAbort(token);else SpringTransportAgent.Transport.rpcExit(token);
        SpringTransportAgent.Transport.rpcExit(token);SpringTransportAgent.Transport.rpcAbort(token);
        if(SpringTransportAgent.Transport.RPC.get().size()!=1||SpringTransportAgent.Transport.RPC.get().peek()!=parentCall||SpringTransportAgent.Transport.SPANS.get().size()!=1||SpringTransportAgent.Transport.SPANS.get().peek()!=parent)throw new AssertionError("RPC parent lost or duplicate completion");
        SpringTransportAgent.Transport.RPC.remove();SpringTransportAgent.Transport.SPANS.remove();System.out.println("RPC|"+injected+"|parent-preserved");
    }
    public static void main(String[] args)throws Exception{
        boolean observed=System.getProperty("service.plan")!=null;
        for(String failure:new String[]{null,"async-worker-start","async-worker-end","async-worker-throw"}){task(failure,false,observed);task(failure,true,observed);}
        if(observed){
            Object input=new Object(),other=new Object();SourceEvidenceHooks.CAPTURES.put(input,new SourceEvidenceHooks.Capture(input));SourceEvidenceHooks.CAPTURES.put(other,new SourceEvidenceHooks.Capture(other));MonitorSafety.Scope scope=MonitorSafety.open("source-cleanup-fixture");scope.failed=true;
            SourceEvidenceHooks.read(null,input,null);if(SourceEvidenceHooks.CAPTURES.containsKey(input)||!SourceEvidenceHooks.CAPTURES.containsKey(other))throw new AssertionError("Failed scope retained input capture or removed another capture");SourceEvidenceHooks.abort(other);scope.close();if(!SourceEvidenceHooks.CAPTURES.isEmpty())throw new AssertionError("Capture cleanup failed");System.out.println("SOURCE|failed-scope-owned-cleanup");
            for(String failure:new String[]{null,"rpc-enter","rpc-exit","rpc-abort"})rpc(failure);System.out.println("FINAL|"+MonitorSafety.inspect());}
    }
}
