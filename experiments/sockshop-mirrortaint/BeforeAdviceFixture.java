import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.aop.framework.ProxyFactory;
import org.aopalliance.intercept.MethodInterceptor;

public class BeforeAdviceFixture {
    public static class Box {public String text;public Box(String s){text=s;}public String getText(){return text;}}
    public interface Service {Box fetch(int mode);Box forward(Box b);}
    public static final IllegalArgumentException ERROR=new IllegalArgumentException("original");
    public static class Store {public static Box read(){return new Box("SAME");}}
    public static class Target implements Service {
        public Box fetch(int mode){System.gc();if(mode==2)throw ERROR;Box b=Store.read();return b;}public Box forward(Box b){return b;}
    }
    public Service service;
    public Box root(int mode){if(mode==4)return service.forward(Store.read());return service.fetch(mode);}
    public static void main(String[] args)throws Exception{
        boolean observe=Boolean.getBoolean("fixture.observe");ObjectMapper mapper=new ObjectMapper();List<Map> results=new ArrayList<>();
        for(int i=0;i<10;i++){
            int mode=i%5;ProxyFactory factory=new ProxyFactory(new Target());factory.setProxyTargetClass(true);
            if(Boolean.getBoolean("fixture.expose"))factory.addAdvice(org.springframework.aop.interceptor.ExposeInvocationInterceptor.INSTANCE);
            factory.addAdvice(org.springframework.aop.interceptor.ExposeInvocationInterceptor.INSTANCE);
            final int currentMode=mode;
            org.springframework.aop.support.DynamicMethodMatcherPointcut pointcut=new org.springframework.aop.support.DynamicMethodMatcherPointcut(){public boolean matches(java.lang.reflect.Method m,Class<?> type,Object... arguments){return currentMode!=1;}};
            factory.addAdvisor(new org.springframework.aop.support.DefaultPointcutAdvisor(pointcut,(org.springframework.aop.MethodBeforeAdvice)(method,arguments,target)->{if(arguments.length>0&&arguments[0] instanceof Box)((Box)arguments[0]).text="SAME";}));
            if(mode==3)factory.addAdvice((MethodInterceptor)invocation->{Box b=(Box)invocation.proceed();b.text="SAME";return b;});
            BeforeAdviceFixture fixture=new BeforeAdviceFixture();fixture.service=(Service)factory.getProxy();
            W3CTraceContext context=W3CTraceContext.server("00-33333333333333333333333333333333-"+String.format("%016x",i+1)+"-01","fixture=dispatch");
            if(observe)SpringTransportAgent.Transport.ASYNC.set(context);
            Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",context.fields().get("message"));row.put("callback",((org.springframework.cglib.proxy.Factory)fixture.service).getCallback(0).getClass().getName());
            try{
                Box value=fixture.root(mode);row.put("response",value.text);row.put("status","normal");
                if(observe)ResponseBindingHooks.verifySerialization(value,mapper); // Invocation-only control; no synthetic HTTP identity.
            }catch(IllegalArgumentException original){row.put("status","exceptional");row.put("same_exception",original==ERROR);}
            finally{if(observe)SpringTransportAgent.Transport.ASYNC.remove();}
            results.add(row);
        }
        System.out.println(mapper.writeValueAsString(results));
    }
}
