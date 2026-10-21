import java.util.*;
import java.util.concurrent.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.interceptor.AsyncExecutionInterceptor;
import org.springframework.scheduling.annotation.AsyncResult;
import org.springframework.core.task.support.TaskExecutorAdapter;

/** Independent literal input-source cases; real pinned Spring asynchronous execution. */
public class AsyncDependencyFixture {
    public static class Out {public String text;public Out(String v){text=v;}public String getText(){return text;}public void setText(String v){text=v;}}
    public interface Worker {Future<Out> work(String text,int mode);Future<Out> echo(Out input,int mode);Future<String> text(String input);}
    public static class Service implements Worker {
        public Out leaked;
        Out copy(String text){return new Out(text);}
        void opaque(Object value){int[] unsupported=new int[1];((Out)value).setText("SAME");}
        public Future<Out> work(String text,int mode){
            if(mode==11)throw new IllegalArgumentException("expected");
            Out out=mode==1?copy(text):new Out(mode==2?"constant":text);
            if(mode==12)out=new Out(new StringBuilder().append("pre:").append(text).toString());
            if(mode==4)opaque(out);
            if(mode==7)leaked=out;
            return new AsyncResult<Out>(out);
        }
        public Future<Out> echo(Out input,int mode){return new AsyncResult<Out>(mode==6?input:new Out(input.getText()));}
        public Future<String> text(String input){return new AsyncResult<String>(input);}
    }
    static void opaque(Out value){int[] unsupported=new int[1];value.setText("SAME");}
    public static Out root(Worker worker,String left,String right,Out shared,int mode)throws Exception{
        if(mode==3){Future<Out> a=worker.work(left,0),b=worker.work(right,0);a.get();return b.get();}
        if(mode==5||mode==6)return worker.echo(shared,mode).get();
        if(mode==10)return new Out(worker.text(left).get());
        Future<Out> future=worker.work(left,mode);
        try{Out result=future.get();if(mode==8)result.setText("SAME");if(mode==13)result.setText(right);if(mode==9)opaque(result);return future.get();}
        catch(ExecutionException expected){return new Out("fallback");}
    }
    public static void main(String[] args)throws Exception{
        ExecutorService pool=Executors.newFixedThreadPool(2);ProxyFactory factory=new ProxyFactory(new Service());factory.setInterfaces(Worker.class);factory.addAdvice(new AsyncExecutionInterceptor(new TaskExecutorAdapter(pool)));Worker worker=(Worker)factory.getProxy();ObjectMapper json=new ObjectMapper();List<Map> cases=new ArrayList<>();
        try{for(int i=0;i<28;i++){int mode=i%14;W3CTraceContext c=W3CTraceContext.server("00-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb-"+String.format("%016x",i+1)+"-01","fixture=async-dependencies");SpringTransportAgent.Transport.ASYNC.set(c);Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",c.message());Out out=root(worker,new String("SAME"),new String("SAME"),new Out("SAME"),mode);ResponseBindingHooks.verifySerialization(out,json);row.put("response",json.readValue(json.writeValueAsString(out),Map.class));Map wire=c.fields();wire.put("uri","fixture:async-dependencies");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(out));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();}}
        finally{pool.shutdown();if(!pool.awaitTermination(10,TimeUnit.SECONDS))throw new AssertionError("workers incomplete");}
        System.out.println(json.writeValueAsString(cases));
    }
}
