import java.util.*;
import java.util.concurrent.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.interceptor.AsyncExecutionInterceptor;
import org.springframework.scheduling.annotation.AsyncResult;
import org.springframework.core.task.support.TaskExecutorAdapter;

/** Real pinned Spring interceptor, executor and FutureTask; no dependency oracle. */
public class AsyncTaskFixture {
    static CountDownLatch gate;static boolean reject;
    static ExecutorService pool=Executors.newSingleThreadExecutor();
    static Executor executor=new Executor(){public void execute(Runnable r){if(reject)throw new RejectedExecutionException("fixture rejected");pool.execute(r);}};
    public static class Item {public String text;public Item(String text){this.text=text;}public String getText(){return text;}}
    public static class Out {public String text;public Out(String text){this.text=text;}public String getText(){return text;}}
    public interface Worker {Future<Item> work(Item item,int mode)throws Exception;}
    public static class Service implements Worker {
        public Future<Item> work(Item item,int mode)throws Exception{
            if(mode==1)throw new IllegalArgumentException("worker failure");
            if(mode==2)gate.await();
            return new AsyncResult<Item>(item);
        }
    }
    public static Out root(Worker worker,Item left,Item right,int mode)throws Exception{
        if(mode==0){Future<Item> a=worker.work(left,0),b=worker.work(right,0);Item x=a.get();Item y=b.get();Item again=a.get();return new Out(again.getText());}
        if(mode==1)return new Out(worker.work(left,1).get().getText());
        if(mode==2){Future<Item> a=worker.work(left,2);try{a.get(1,TimeUnit.MILLISECONDS);}catch(TimeoutException expected){gate.countDown();}return new Out(a.get().getText());}
        if(mode==3){Future<Item> a=worker.work(left,2);Future<Item> b=worker.work(right,0);b.cancel(false);gate.countDown();a.get();return new Out(b.get().getText());}
        return new Out(worker.work(left,0).get().getText());
    }
    public static void main(String[] args)throws Exception{
        ProxyFactory factory=new ProxyFactory(new Service());factory.setInterfaces(Worker.class);factory.addAdvice(new AsyncExecutionInterceptor(new TaskExecutorAdapter(executor)));Worker worker=(Worker)factory.getProxy();ObjectMapper json=new ObjectMapper();List<Map> cases=new ArrayList<>();
        int[] modes={0,1,0,2,0,3,0,4,0};
        try{for(int i=0;i<modes.length;i++){int mode=modes[i];reject=mode==4;gate=new CountDownLatch(1);Map c=new LinkedHashMap();c.put("mode",mode);W3CTraceContext context=W3CTraceContext.server("00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-"+String.format("%016x",i+1)+"-01","fixture=async");SpringTransportAgent.Transport.ASYNC.set(context);c.put("message",context.message());try{Out out=root(worker,new Item(new String("SAME")),new Item(new String("SAME")),mode);c.put("status","normal");c.put("text",out.text);}catch(Exception expected){c.put("status","exceptional");c.put("exception",expected.getClass().getName());}finally{reject=false;SpringTransportAgent.Transport.ASYNC.remove();}cases.add(c);}}
        finally{pool.shutdown();if(!pool.awaitTermination(10,TimeUnit.SECONDS))throw new AssertionError("worker not closed");}
        System.out.println(json.writeValueAsString(cases));
    }
}
