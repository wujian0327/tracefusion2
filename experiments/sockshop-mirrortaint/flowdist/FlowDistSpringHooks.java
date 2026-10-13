package disttaint.http;

import disttaint.OTMonitor;
import java.io.File;
import java.io.FileWriter;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import org.aopalliance.intercept.MethodInterceptor;
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.client.ClientHttpRequestInterceptor;

/** Disclosed Spring boundary hooks; no static statement/branch instrumentation.
 * Preserve Spring's async advisor and insert the call hook inside it. */
public final class FlowDistSpringHooks implements BeanPostProcessor, Ordered {
    private static final AtomicBoolean INITIALIZED = new AtomicBoolean();
    private static final Object AUDIT_LOCK = new Object();
    private static final String ORDERS = "works.weave.socks.orders.controllers.OrdersController";
    private static final String CLIENT = "works.weave.socks.orders.services.AsyncGetService";
    private static final String SHIPPING = "works.weave.socks.shipping.controllers.ShippingController";
    private static final URI PEER = URI.create(System.getProperty("flowdist.http.peer", "http://shipping/shipping"));
    public static void initialize() {
        if (INITIALIZED.compareAndSet(false, true)) {
            try { if (!Boolean.getBoolean("flowdist.method.instrumented")) OTMonitor.initialize(); }
            catch (Exception e) { throw new IllegalStateException("FlowDist initialization failed", e); }
        }
    }
    public int getOrder() { return Ordered.LOWEST_PRECEDENCE; }
    public Object postProcessBeforeInitialization(Object bean, String name) { return bean; }
    public Object postProcessAfterInitialization(Object bean, String name) throws BeansException {
        final Class<?> type = AopUtils.getTargetClass(bean);
        final String className = type.getName();
        if (!className.equals(ORDERS) && !className.equals(CLIENT) && !className.equals(SHIPPING)) return bean;
        initialize();
        if (className.equals(CLIENT)) {
            try {
                Object target = bean instanceof Advised ? ((Advised)bean).getTargetSource().getTarget() : bean;
                Field hal = type.getDeclaredField("halTemplate"); hal.setAccessible(true);
                install((RestTemplate)hal.get(target));
                Field proxy = type.getDeclaredField("restProxyTemplate"); proxy.setAccessible(true);
                Object owner = proxy.get(target);
                install((RestTemplate)owner.getClass().getMethod("getRestTemplate").invoke(owner));
            } catch (Exception e) { throw new IllegalStateException("Cannot install original async HTTP clock interceptor", e); }
        }
        MethodInterceptor advice = new MethodInterceptor() {
            public Object invoke(MethodInvocation invocation) throws Throwable {
                String method = invocation.getMethod().getName();
                boolean selected = className.equals(ORDERS) && method.equals("newOrder")
                    || className.equals(SHIPPING) && method.equals("postShipping")
                    || className.equals(CLIENT) && method.equals("postResource")
                        && invocation.getArguments().length > 0 && PEER.equals(invocation.getArguments()[0]);
                if (!selected) return invocation.proceed();
                String signature = signature(type, invocation.getMethod());
                synchronized (OTMonitor.class) {
                    if (!Boolean.getBoolean("flowdist.method.instrumented")) OTMonitor.enter(signature);
                    audit("enter", signature);
                }
                try {
                    Object result = invocation.proceed();
                    audit("return", signature);
                    return result;
                } catch (Throwable error) { audit("throw", signature); throw error; }
            }
        };
        if (bean instanceof Advised) {
            // AsyncExecutionInterceptor submits the remaining chain to its worker.
            ((Advised)bean).addAdvice(advice);
            return bean;
        }
        ProxyFactory factory = new ProxyFactory(bean);
        factory.setProxyTargetClass(true);
        factory.addAdvice(advice);
        return factory.getProxy();
    }
    private static void install(RestTemplate template) {
        if (template == null) throw new IllegalStateException("Missing original RestTemplate");
        List<ClientHttpRequestInterceptor> chain = new ArrayList<>(template.getInterceptors());
        chain.add(FlowDistHttpConfiguration.client(PEER));
        template.setInterceptors(chain);
    }
    private static String signature(Class<?> type, Method method) {
        StringBuilder text = new StringBuilder("<").append(type.getName()).append(": ")
            .append(method.getReturnType().getTypeName()).append(' ').append(method.getName()).append('(');
        Class<?>[] parameters = method.getParameterTypes();
        for (int i = 0; i < parameters.length; i++) {
            if (i > 0) text.append(',');
            text.append(parameters[i].getTypeName());
        }
        return text.append(")>").toString();
    }
    private static String quote(String text) {
        return "\"" + text.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\"";
    }
    private static void audit(String phase, String method) {
        String output = System.getProperty("flowdist.audit", "/tf2/output/spring-events.jsonl");
        Thread thread = Thread.currentThread();
        int clock = OTMonitor.getlgclock().getLTS();
        synchronized (AUDIT_LOCK) { try (FileWriter writer = new FileWriter(output, true)) {
            writer.write("{\"phase\":" + quote(phase) + ",\"method\":" + quote(method)
                + ",\"thread\":" + quote(thread.getName()) + ",\"thread_id\":" + thread.getId()
                + ",\"clock\":" + clock + "}\n");
        } catch (Exception e) { throw new IllegalStateException("FlowDist audit write failed", e); } }
    }
}
