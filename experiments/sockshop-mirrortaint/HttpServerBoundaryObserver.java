import java.lang.instrument.*;
import java.security.ProtectionDomain;
import javassist.*;
import com.google.gson.GsonBuilder;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Independent HTTP entry/exit observer; never touches taint state or HTTP headers. */
public final class HttpServerBoundaryObserver implements ClassFileTransformer {
    private static final Object LOCK = new Object();
    private static final ThreadLocal<Deque<Map<String,Object>>> ACTIVE = new ThreadLocal<Deque<Map<String,Object>>>() {
        protected Deque<Map<String,Object>> initialValue() { return new ArrayDeque<>(); }
    };
    public static void premain(String args, Instrumentation instrumentation) {
        instrumentation.addTransformer(new HttpServerBoundaryObserver());
    }
    public byte[] transform(ClassLoader loader, String name, Class<?> type, ProtectionDomain domain, byte[] bytes) {
        boolean servlet = "org/springframework/web/servlet/FrameworkServlet".equals(name);
        boolean dispatch = "org/springframework/web/servlet/mvc/method/annotation/ServletInvocableHandlerMethod".equals(name);
        if (!servlet && !dispatch) return null;
        try {
            ClassPool pool = new ClassPool(true);
            pool.appendClassPath(new LoaderClassPath(loader));
            pool.appendClassPath(new ClassClassPath(HttpServerBoundaryObserver.class));
            CtClass transformed = pool.makeClass(new java.io.ByteArrayInputStream(bytes));
            CtMethod method = transformed.getDeclaredMethod(servlet ? "processRequest" : "invokeAndHandle");
            if (servlet) {
                method.insertBefore("HttpServerBoundaryObserver.enter($1);");
                method.insertAfter("HttpServerBoundaryObserver.exit($2);", true);
            } else method.insertBefore("HttpServerBoundaryObserver.handler($0);");
            byte[] output = transformed.toBytecode();
            transformed.detach();
            System.err.println("TF2_HTTP_OBSERVER instrumented=" + name + "." + method.getName());
            return output;
        } catch (Throwable error) {
            System.err.println("TF2_HTTP_OBSERVER error transform=" + error);
            return null;
        }
    }
    private static Object invoke(Object object, String iface, String method, Class<?>[] parameters, Object... arguments) throws Exception {
        Class<?> api = Class.forName(iface, false, Thread.currentThread().getContextClassLoader());
        return api.getMethod(method, parameters).invoke(object, arguments);
    }
    private static String mdc(String key) throws Exception {
        Class<?> api = Class.forName("org.slf4j.MDC", false, Thread.currentThread().getContextClassLoader());
        return (String) api.getMethod("get", String.class).invoke(null, key);
    }
    public static void enter(Object request) {
        Map<String,Object> event = new LinkedHashMap<>();
        ACTIVE.get().push(event); // Even a failed observation gets its own stack entry.
        try {
            String api = "javax.servlet.http.HttpServletRequest";
            event.put("invocation_id", UUID.randomUUID().toString());
            event.put("thread_id", Thread.currentThread().getId());
            event.put("method", invoke(request, api, "getMethod", new Class<?>[0]));
            event.put("uri", invoke(request, api, "getRequestURI", new Class<?>[0]));
            for (String header : new String[]{"X-B3-TraceId", "X-B3-SpanId", "X-B3-ParentSpanId"})
                event.put(header, invoke(request, api, "getHeader", new Class<?>[]{String.class}, header));
            event.put("trace_id", mdc("X-B3-TraceId"));
            event.put("server_span_id", mdc("X-B3-SpanId"));
            emit(event, "enter");
        } catch (Throwable error) {
            System.err.println("TF2_HTTP_OBSERVER error enter=" + error);
        }
    }
    public static void exit(Object response) {
        try {
            Deque<Map<String,Object>> active = ACTIVE.get();
            Map<String,Object> event = active.pop();
            if (active.isEmpty()) ACTIVE.remove();
            event.put("http_status", invoke(response, "javax.servlet.http.HttpServletResponse", "getStatus", new Class<?>[0]));
            emit(event, "exit");
        } catch (Throwable error) {
            System.err.println("TF2_HTTP_OBSERVER error exit=" + error);
        }
    }
    public static void handler(Object dispatch) {
        try {
            if (ACTIVE.get().isEmpty()) throw new IllegalStateException("No active HTTP invocation");
            java.lang.reflect.Method method = (java.lang.reflect.Method) invoke(dispatch,
                "org.springframework.web.method.HandlerMethod", "getMethod", new Class<?>[0]);
            Map<String,Object> event = new LinkedHashMap<>(ACTIVE.get().peek());
            event.put("controller_owner", method.getDeclaringClass().getName());
            event.put("controller_method", method.getName());
            event.put("dispatch_span_id", mdc("X-B3-SpanId"));
            emit(event, "handler");
        } catch (Throwable error) {
            System.err.println("TF2_HTTP_OBSERVER error handler=" + error);
        }
    }
    private static void emit(Map<String,Object> invocation, String phase) throws Exception {
        Map<String,Object> event = new LinkedHashMap<>(invocation);
        event.put("phase", phase);
        Path log = Paths.get(System.getProperty("tf2.http.observer.log"));
        byte[] bytes = (new GsonBuilder().serializeNulls().create().toJson(event) + "\n").getBytes(StandardCharsets.UTF_8);
        synchronized (LOCK) {
            Files.createDirectories(log.getParent());
            Files.write(log, bytes, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        }
    }
}
