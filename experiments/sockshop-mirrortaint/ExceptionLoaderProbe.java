import java.util.*;
import java.nio.file.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Two real defining loaders for the same binary name; dispatch must not use names. */
public class ExceptionLoaderProbe {
    static class LeafLoader extends ClassLoader {
        final byte[] bytes;
        LeafLoader(byte[] b){super(ExceptionDispatchFixture.class.getClassLoader());bytes=b;}
        protected Class<?> loadClass(String name,boolean resolve)throws ClassNotFoundException {
            if(!name.equals("ExceptionDispatchFixture$Leaf"))return super.loadClass(name,resolve);
            Class<?> c=findLoadedClass(name);if(c==null)c=defineClass(name,bytes,0,bytes.length);if(resolve)resolveClass(c);return c;
        }
    }
    public static void main(String[] args)throws Exception {
        ObjectMapper json=new ObjectMapper();PlannedServiceAgent.plan=json.readValue(Paths.get(args[0]).toFile(),Map.class);
        PlannedServiceAgent.Recorder.Frame frame=new PlannedServiceAgent.Recorder.Frame();frame.id="loader-probe";frame.method="ExceptionDispatchFixture.root(LExceptionDispatchFixture$Store;IILExceptionDispatchFixture$Base;)LExceptionDispatchFixture$Out;";PlannedServiceAgent.Recorder.STACK.get().push(frame);
        byte[] bytes=Files.readAllBytes(Paths.get(args[1]));List facts=new ArrayList();Class<?> previous=null;
        for(int i=0;i<2;i++){
            Class<?> c=new LeafLoader(bytes).loadClass("ExceptionDispatchFixture$Leaf");if(c==previous||c==ExceptionDispatchFixture.Leaf.class)throw new AssertionError();previous=c;
            facts.add(ExecutionKernelHooks.exceptionDispatch((Throwable)c.newInstance(),ExceptionDispatchFixture.class));
        }
        System.out.println(json.writeValueAsString(facts));
    }
}
