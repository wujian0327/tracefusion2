package tracefusion.service;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.lang.reflect.*;

/** Identity/version boundary observations only. Offline code constructs dependencies. */
public final class ServiceRecorder {
    private static Path directory;
    private static BufferedWriter output;
    private static long sequence, frames;
    private static final IdentityHashMap<Object,String> IDS = new IdentityHashMap<>();
    private static final Map<String,Integer> VERSIONS = new HashMap<>();
    private static final ThreadLocal<Deque<Map<String,Object>>> STACK = new ThreadLocal<Deque<Map<String,Object>>>() {
        protected Deque<Map<String,Object>> initialValue() { return new ArrayDeque<>(); }
    };
    private static final ThreadLocal<Deque<Map<String,Object>>> RPC = new ThreadLocal<Deque<Map<String,Object>>>() {
        protected Deque<Map<String,Object>> initialValue() { return new ArrayDeque<>(); }
    };
    public static synchronized void start() throws Exception {
        directory = Paths.get(System.getProperty("tracefusion.service.output")); Files.createDirectories(directory);
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
            if (method.contains(".calculateTotal(")) {
                if (args.length != 1 || !(args[0] instanceof Collection)) throw new IllegalStateException("Unsupported reduction input");
                List<String> members = new ArrayList<>();
                for (Object member : (Collection<?>)args[0]) {
                    if (members.size() >= 10000) throw new IllegalStateException("Collection snapshot limit");
                    members.add(id(member));
                }
                event.put("collection_argument", members);
            }
            STACK.get().push(event); emit("enter", event);
        } catch (Throwable error) { problem("enter:" + error); }
    }
    public static synchronized void exit(Object result) {
        try {
            Map<String,Object> entry = STACK.get().pop();
            Map<String,Object> event = new LinkedHashMap<>(); event.put("frame", entry.get("frame")); event.put("result", value(result));
            if (((String)entry.get("method")).contains(".newOrder(")) event.put("fields", snapshot(result, "arg"));
            emit("exit", event); if (STACK.get().isEmpty()) STACK.remove();
        } catch (Throwable error) { problem("exit:" + error); }
    }
    public static synchronized void abort(String kind) {
        try {
            Map<String,Object> entry = (kind.equals("rpc") ? RPC : STACK).get().pop();
            Map<String,Object> event = new LinkedHashMap<>(); event.put("scope", kind);
            event.put("instance", kind.equals("rpc") ? entry.get("rpc") : entry.get("frame")); emit("abort", event);
        } catch (Throwable error) { problem("abort:" + error); }
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
        for (Class<?> clazz=object.getClass();clazz!=null&&clazz!=Object.class;clazz=clazz.getSuperclass()) {
            for (Field field : clazz.getDeclaredFields()) {
                if (Modifier.isStatic(field.getModifiers()) || field.isSynthetic()) continue;
                field.setAccessible(true); Object observed=field.get(object); String location=owner+":"+field.getName();
                Map<String,Object> entry = new LinkedHashMap<>(); entry.put("path",path+"#"+field.getName());
                entry.put("owner",owner); entry.put("field",field.getName());
                entry.put("version",VERSIONS.containsKey(location)?VERSIONS.get(location):0); entry.put("observed",value(observed));
                entry.put("primitive",field.getType().isPrimitive()); fields.add(entry);
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
        System.err.println("TF2_SERVICE_FRONTEND error="+reason);
    }
    private static void emit(String kind,Map<String,Object> original) {
        try {
            if (sequence >= 1000000) throw new IllegalStateException("Event limit");
            Map<String,Object> event=new LinkedHashMap<>(original); event.put("seq",++sequence);
            event.put("thread",Thread.currentThread().getId()); event.put("kind",kind);
            output.write(json(event)); output.newLine(); output.flush();
        } catch (Throwable error) { System.err.println("TF2_SERVICE_FRONTEND error=write:"+error); }
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
