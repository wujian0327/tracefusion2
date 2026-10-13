package tracefusion.boundary;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.lang.reflect.*;

/** Identity/version boundary observations only. Offline code constructs dependencies. */
public final class BoundaryRecorder {
    private static Path directory;
    private static BufferedWriter output;
    private static long sequence, frames;
    private static final String MODE = System.getProperty("tracefusion.boundary.mode", "metrics");
    public static boolean metricsOnly() { return MODE.equals("metrics"); }
    public static boolean mirror() { return MODE.equals("mirrortaint"); }
    private static final com.sun.management.ThreadMXBean ALLOCATION = (com.sun.management.ThreadMXBean)java.lang.management.ManagementFactory.getThreadMXBean();
    private static long rssKb() throws Exception {
        for(String line:Files.readAllLines(Paths.get("/proc/self/status"),StandardCharsets.US_ASCII))
            if(line.startsWith("VmRSS:")) return Long.parseLong(line.trim().split("\\s+")[1]);
        throw new IllegalStateException("VmRSS unavailable");
    }
    private static long processAllocated() {
        long total=0; for(long bytes:ALLOCATION.getThreadAllocatedBytes(ALLOCATION.getAllThreadIds())) if(bytes>=0) total+=bytes; return total;
    }
    private static long allocated() { return ALLOCATION.isThreadAllocatedMemorySupported() ? ALLOCATION.getThreadAllocatedBytes(Thread.currentThread().getId()) : -1; }

    private static final IdentityHashMap<Object,String> IDS = new IdentityHashMap<>();
    private static final Map<String,Integer> VERSIONS = new HashMap<>();
    private static final ThreadLocal<Deque<Map<String,Object>>> STACK = new ThreadLocal<Deque<Map<String,Object>>>() {
        protected Deque<Map<String,Object>> initialValue() { return new ArrayDeque<>(); }
    };
    private static final ThreadLocal<Deque<Map<String,Object>>> RPC = new ThreadLocal<Deque<Map<String,Object>>>() {
        protected Deque<Map<String,Object>> initialValue() { return new ArrayDeque<>(); }
    };
    public static synchronized void start() throws Exception {
        directory = Paths.get(System.getProperty("tracefusion.boundary.output")); Files.createDirectories(directory);
        output = Files.newBufferedWriter(directory.resolve("events.jsonl"), StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        emit("start", new LinkedHashMap<String,Object>());
    }
    private static String id(Object value) {
        if (value == null) return "o0";
        String id = IDS.get(value);
        if (id == null) {
            if (IDS.size() >= 100000) throw new IllegalStateException("Object limit");
            id = "o" + (IDS.size() + 1); IDS.put(value,id);
        }
        return id;
    }
    private static Object value(Object value) {
        Map<String,Object> observation = new LinkedHashMap<>();
        observation.put("object", id(value));
        if (value == null || value instanceof Number || value instanceof String || value instanceof Boolean)
            observation.put("value", value);
        return observation;
    }
    private static Map<String,Object> context() {
        Map<String,Object> event = new LinkedHashMap<>();
        event.put("frame", STACK.get().isEmpty() ? 0L : STACK.get().peek().get("frame"));
        return event;
    }
    public static synchronized void enter(String method, Object self, Object[] args) {
        try {
            Map<String,Object> event = context(); event.put("parent", event.get("frame")); event.put("frame", ++frames);
            event.put("method", method); event.put("receiver", id(self));
            List<Object> arguments = new ArrayList<>(); for (Object arg : args) arguments.add(value(arg));
            event.put("args", arguments); event.put("trace_id", mdc("X-B3-TraceId"));
            if (method.contains(".postShipping(")) event.put("message_id", requestMessage());
            event.put("begin_ns", System.nanoTime()); event.put("begin_allocated", allocated()); event.put("begin_process_allocated",processAllocated());
            if (!metricsOnly()) {
                List<Object> inputs = new ArrayList<>();
                for (int i=0;i<args.length;i++) inputs.addAll(snapshot(args[i], "args["+i+"]"));
                event.put("fields", inputs);
            }
            STACK.get().push(event); emit("enter", event);
            if (!metricsOnly() && method.contains(".postShipping(")) source(args[0], "http-request-body");
        } catch (Throwable error) { problem("enter:" + error); }
    }
    public static synchronized void exit(Object result) {
        try {
            long end = System.nanoTime(), allocatedEnd = allocated(), processEnd=processAllocated();
            Map<String,Object> entry = STACK.get().peek();
            Map<String,Object> event = new LinkedHashMap<>(); event.put("frame", entry.get("frame")); event.put("result", value(result));
            event.put("rss_kb",rssKb()); event.put("method", entry.get("method")); event.put("parent", entry.get("parent"));
            event.put("trace_id", entry.get("trace_id"));
            event.put("runtime_ns", end - (Long)entry.get("begin_ns")); event.put("process_allocated_bytes",processEnd-(Long)entry.get("begin_process_allocated"));
            long beginAllocated=(Long)entry.get("begin_allocated");
            event.put("thread_allocated_bytes", beginAllocated < 0 || allocatedEnd < 0 ? -1 : allocatedEnd - beginAllocated);
            if (!metricsOnly()) event.put("fields", snapshot(result, "result"));
            emit("exit", event); STACK.get().pop(); if (STACK.get().isEmpty()) STACK.remove();
        } catch (Throwable error) { problem("exit:" + error); }
    }
    public static synchronized void abort(String kind) {
        try {
            Map<String,Object> entry = (kind.equals("rpc") ? RPC : STACK).get().pop();
            Map<String,Object> event = new LinkedHashMap<>(); event.put("scope", kind);
            event.put("instance", kind.equals("rpc") ? entry.get("rpc") : entry.get("frame")); emit("abort", event);
        } catch (Throwable error) { problem("abort:" + error); }
    }
    public static synchronized void source(Object result, String boundary) {
        if (STACK.get().isEmpty() || metricsOnly()) return;
        try {
            Map<String,Object> event=context(); event.put("boundary", boundary); event.put("instance", UUID.randomUUID().toString());
            if (boundary.equals("http-request-body")) event.put("message_id", STACK.get().peek().get("message_id"));
            List<Object> fields=snapshot(result,"source"); event.put("fields",fields);
            if (mirror()) {
                Class<?> heap=Class.forName("com.shadow.taint.agent.runtime.TaintHeap");
                if (!(Boolean)heap.getMethod("available").invoke(null)) heap.getMethod("startup").invoke(null);
                for (Object row:fields) {
                    Map<String,Object> f=(Map<String,Object>)row;
                    Map<String,Object> observed=(Map<String,Object>)f.get("observed");
                    if (!observed.containsKey("value") || observed.get("value")==null) continue;
                    String token="tf2boundary:"+event.get("instance")+":"+f.get("path"); f.put("token",token);
                    Object object=null; for(Map.Entry<Object,String> identity:IDS.entrySet()) if(identity.getValue().equals(f.get("owner"))) { object=identity.getKey(); break; }
                    Class<?> c=Class.forName("com.shadow.taint.agent.model.C"), a=Class.forName("com.shadow.taint.agent.model.A");
                    Object provenance=c.getConstructor(String.class,String.class,StackTraceElement[].class).newInstance(token,"boundary",new StackTraceElement[0]);
                    Object tag=a.getConstructor(c,int.class).newInstance(provenance,1);
                    if ((Boolean)f.get("primitive")) heap.getMethod("recordPrimitiveFieldTaint",Object.class,String.class,a).invoke(null,object,f.get("field"),tag);
                    else {
                        Object value=fieldValue(object,(String)f.get("field"));
                        heap.getMethod("recordTaint",Object.class,a).invoke(null,value,tag);
                    }
                }
            }
            emit("source",event);
        } catch(Throwable error) { problem("source:"+error); }
    }
    private static String requestMessage() throws Exception {
        ClassLoader loader=Thread.currentThread().getContextClassLoader();
        Class<?> holder=Class.forName("org.springframework.web.context.request.RequestContextHolder",false,loader);
        Object attributes=holder.getMethod("currentRequestAttributes").invoke(null);
        Object request=Class.forName("org.springframework.web.context.request.ServletRequestAttributes",false,loader)
            .getMethod("getRequest").invoke(attributes);
        String message=(String)Class.forName("javax.servlet.http.HttpServletRequest",false,loader)
            .getMethod("getHeader",String.class).invoke(request,"X-TraceFusion-Message");
        if (message!=null && !message.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"))
            throw new IllegalArgumentException("Invalid HTTP message identity");
        return message;
    }
    private static Object fieldValue(Object object,String field) throws Exception {
        for(Class<?> c=object.getClass();c!=null;c=c.getSuperclass()) try { Field f=c.getDeclaredField(field);f.setAccessible(true);return f.get(object); } catch(NoSuchFieldException ignored) {}
        throw new NoSuchFieldException(field);
    }
    public static synchronized void sink(Object result,String boundary) {
        if (STACK.get().isEmpty() || metricsOnly()) return;
        try { Map<String,Object> event=context();event.put("boundary",boundary);event.put("fields",snapshot(result,"sink"));emit("sink",event); }
        catch(Throwable error) { problem("sink:"+error); }
    }
    public static synchronized void read(Object object, String field, Object observed) { field("read",object,field,observed); }
    public static synchronized void write(Object object, String field, Object observed) { field("write",object,field,observed); }
    private static void field(String kind, Object object, String field, Object observed) {
        try {
            String owner = id(object), key = owner + ":" + field; int version = VERSIONS.containsKey(key) ? VERSIONS.get(key) : 0;
            if (kind.equals("write")) VERSIONS.put(key, ++version);
            Map<String,Object> event = context(); event.put("owner", owner); event.put("field",field);
            event.put("version",version); event.put("observed",value(observed)); emit(kind,event);
        } catch (Throwable error) { problem("field:" + error); }
    }
    public static synchronized void sumStart(Object stream) {
        Map<String,Object> event = context(); event.put("stream",id(stream));
        event.put("parallel",((java.util.stream.DoubleStream)stream).isParallel()); emit("sum-enter",event);
    }
    public static synchronized void sumEnd(double total) {
        Map<String,Object> event = context(); event.put("value",total); emit("sum-exit",event);
    }
    public static synchronized void rpcEnter(Object request) {
        try {
            Map<String,Object> event = new LinkedHashMap<>(); event.put("rpc",UUID.randomUUID().toString());
            event.put("uri",invoke(request,"getUrl").toString()); event.put("method",invoke(request,"getMethod").toString());
            event.put("trace_id",mdc("X-B3-TraceId")); event.put("span_id",mdc("X-B3-SpanId"));
            RPC.get().push(event); emit("rpc-enter",event);
        } catch (Throwable error) { problem("rpc-enter:" + error); }
    }
    public static synchronized void rpcExit(Object response) {
        try {
            Map<String,Object> event = new LinkedHashMap<>(RPC.get().pop());
            event.put("fields",snapshot(invoke(response,"getBody"),"result#body"));
            event.put("status",invoke(response,"getStatusCode").toString()); emit("rpc-exit",event);
            if (RPC.get().isEmpty()) RPC.remove();
        } catch (Throwable error) { problem("rpc-exit:" + error); }
    }
    private static Object invoke(Object object, String method) throws Exception { return object.getClass().getMethod(method).invoke(object); }
    private static String mdc(String key) {
        try { return (String)Class.forName("org.slf4j.MDC",false,Thread.currentThread().getContextClassLoader())
            .getMethod("get",String.class).invoke(null,key); } catch (Exception ignored) { return null; }
    }
    private static List<Object> snapshot(Object root, String path) throws Exception {
        List<Object> fields = new ArrayList<>(); walk(root,path,fields,new IdentityHashMap<Object,Boolean>(),0); return fields;
    }
    private static void walk(Object object, String path, List<Object> fields, IdentityHashMap<Object,Boolean> seen,int depth) throws Exception {
        if (depth > 12 || fields.size() > 10000) throw new IllegalStateException("Snapshot limit");
        if (object == null || seen.containsKey(object)) return;
        seen.put(object,true);
        if (object instanceof Collection) {
            int index = 0; for (Object item : (Collection<?>)object) walk(item,path+"["+index+++"]",fields,seen,depth+1);
            return;
        }
        if (object instanceof String || object instanceof Number || object.getClass().getName().startsWith("java.")) return;
        String owner = id(object);
        Object recordId=null; try { recordId=fieldValue(object,"id"); } catch(NoSuchFieldException ignored) {}
        for (Class<?> clazz=object.getClass();clazz!=null&&clazz!=Object.class;clazz=clazz.getSuperclass()) {
            for (Field field : clazz.getDeclaredFields()) {
                if (Modifier.isStatic(field.getModifiers()) || field.isSynthetic()) continue;
                field.setAccessible(true); Object observed=field.get(object); String location=owner+":"+field.getName();
                Map<String,Object> entry = new LinkedHashMap<>(); entry.put("path",path+"#"+field.getName());
                entry.put("owner",owner); entry.put("field",field.getName()); entry.put("record_id",recordId);
                entry.put("version",VERSIONS.containsKey(location)?VERSIONS.get(location):0); entry.put("observed",value(observed));
                entry.put("primitive",field.getType().isPrimitive());
                if (mirror() && (observed == null || observed instanceof String || observed instanceof Number || observed instanceof Boolean)) {
                    Class<?> heap=Class.forName("com.shadow.taint.agent.runtime.TaintHeap");
                    Object tag=field.getType().isPrimitive() ? heap.getMethod("queryPrimitiveFieldTaint",Object.class,String.class).invoke(null,object,field.getName())
                        : heap.getMethod("queryTaint",Object.class).invoke(null,observed);
                    List<String> tokens=new ArrayList<>();
                    if(tag!=null) for(Object source:(Set<?>)tag.getClass().getMethod("A").invoke(tag)) {
                        // C.C and C.B are recorded explicitly; decoding is evaluator-only.
                        tokens.add(String.valueOf(source.getClass().getMethod("C").invoke(source)));
                        tokens.add(String.valueOf(source.getClass().getMethod("B").invoke(source)));
                    }
                    entry.put("tags",tokens);
                }
                fields.add(entry);
                if (observed != null && !field.getType().isPrimitive()) walk(observed,path+"#"+field.getName(),fields,seen,depth+1);
            }
        }
    }
    public static synchronized void transformed(String name,byte[] bytes) throws Exception {
        Files.write(directory.resolve(name.replace('/','_')+".original.class"),bytes,StandardOpenOption.CREATE_NEW);
        Map<String,Object> event=new LinkedHashMap<>(); event.put("class",name); emit("class",event);
    }
    public static synchronized void problem(String reason) {
        Map<String,Object> event=new LinkedHashMap<>(); event.put("reason",reason); emit("problem",event);
        System.err.println("TF2_BOUNDARY error="+reason);
    }
    private static void emit(String kind,Map<String,Object> original) {
        try {
            if (sequence >= 1000000) throw new IllegalStateException("Event limit");
            Map<String,Object> event=new LinkedHashMap<>(original); event.put("seq",++sequence);
            event.put("thread",Thread.currentThread().getId()); event.put("kind",kind); event.put("nano_time",System.nanoTime());
            output.write(json(event)); output.newLine(); output.flush();
        } catch (Throwable error) { System.err.println("TF2_BOUNDARY error=write:"+error); }
    }
    private static String json(Object value) {
        if (value==null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map) { StringJoiner out=new StringJoiner(",","{","}");
            for (Map.Entry<?,?>e:((Map<?,?>)value).entrySet()) out.add(json(e.getKey())+":"+json(e.getValue())); return out.toString(); }
        if (value instanceof Iterable) { StringJoiner out=new StringJoiner(",","[","]"); for(Object e:(Iterable<?>)value)out.add(json(e));return out.toString(); }
        StringBuilder out=new StringBuilder("\""); for(char c:((String)value).toCharArray()) {
            if(c=='"'||c=='\\')out.append('\\').append(c);else if(c<32)out.append(String.format("\\u%04x",(int)c));else out.append(c); }
        return out.append('"').toString();
    }
}
