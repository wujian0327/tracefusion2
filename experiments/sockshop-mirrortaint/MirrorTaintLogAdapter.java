import com.google.gson.GsonBuilder;
import com.shadow.taint.agent.runtime.TaintHeap;
import com.shadow.taint.agent.model.A;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Bounded, identity-aware event channel. Explicit omissions; does not create source labels. */
public final class MirrorTaintLogAdapter {
    private static final Object LOCK = new Object();
    private static final ThreadLocal<Deque<String>> RPC = new ThreadLocal<Deque<String>>() {
        protected Deque<String> initialValue() { return new ArrayDeque<>(); }
    };
    private static final class Scan {
        final Map<String, Object> fields = new LinkedHashMap<>();
        final Map<Object, String> seen = new IdentityHashMap<>();
        final List<String> omissions = new ArrayList<>();
        int nodes;
        void walk(Object object, String path, A primitiveTag, boolean primitive, int depth) throws Exception {
            if (++nodes > 20000 || depth > 16) { omissions.add(path + ":capture-limit"); return; }
            Map<String, Object> data = new LinkedHashMap<>();
            if (object == null || primitive || object instanceof String || object instanceof Number
                || object instanceof Boolean || object instanceof Character || object instanceof Date
                || object instanceof java.net.URI || object.getClass().isEnum()) {
                data.put("value", object == null || object instanceof Number || object instanceof Boolean
                    || object instanceof String ? object : object.toString());
                data.put("tag", primitive ? primitiveTag : TaintHeap.queryTaint(object));
                fields.put(path, data); return;
            }
            if (object instanceof Class || object instanceof java.lang.reflect.Type || typeMetadata(object.getClass())) {
                data.put("metadata_type", object.getClass().getName());
                data.put("status", "opaque-type-metadata"); fields.put(path, data); return;
            }
            if (seen.containsKey(object)) {
                data.put("identity_ref", seen.get(object)); fields.put(path, data); return;
            }
            seen.put(object, path);
            Class<?> type = object.getClass();
            if (type.isArray()) {
                int length = java.lang.reflect.Array.getLength(object);
                data.put("container", "array"); data.put("size", length); fields.put(path, data);
                for (int i = 0; i < length; i++) {
                    if (nodes >= 20000) { omissions.add(path + ":capture-limit"); break; }
                    walk(java.lang.reflect.Array.get(object, i), path + "[" + i + "]",
                    TaintHeap.queryPrimitiveFieldTaint(object, String.valueOf(i)), type.getComponentType().isPrimitive(), depth + 1);
                }
            } else if (object instanceof Collection) {
                int index = 0;
                data.put("container", "collection"); data.put("size", ((Collection<?>) object).size()); fields.put(path, data);
                for (Object item : (Collection<?>) object) {
                    if (nodes >= 20000) { omissions.add(path + ":capture-limit"); break; }
                    walk(item, path + "[" + index++ + "]", null, false, depth + 1);
                }
            } else if (object instanceof Map) {
                int index = 0;
                data.put("container", "map"); data.put("size", ((Map<?, ?>) object).size()); fields.put(path, data);
                for (Map.Entry<?, ?> entry : ((Map<?, ?>) object).entrySet()) {
                    if (nodes >= 20000) { omissions.add(path + ":capture-limit"); break; }
                    walk(entry.getKey(), path + "[" + index + "]#key", null, false, depth + 1);
                    walk(entry.getValue(), path + "[" + index++ + "]#value", null, false, depth + 1);
                }
            } else if (type.getName().startsWith("java.")) {
                data.put("status", "opaque-jdk-object"); data.put("type", type.getName()); fields.put(path, data);
            } else {
                for (Class<?> current = type; current != null && current != Object.class; current = current.getSuperclass()) {
                    for (java.lang.reflect.Field field : current.getDeclaredFields()) {
                        if (nodes >= 20000) { omissions.add(path + ":capture-limit"); return; }
                        if (java.lang.reflect.Modifier.isStatic(field.getModifiers())) continue;
                        // Synthetic enclosing references are non-payload metadata, explicitly marked.
                        if (field.isSynthetic()) {
                            Map<String, Object> skipped = new LinkedHashMap<>();
                            skipped.put("status", "opaque-synthetic-reference"); fields.put(path + "#" + field.getName(), skipped);
                            continue;
                        }
                        field.setAccessible(true);
                        walk(field.get(object), path + "#" + field.getName(),
                            TaintHeap.queryPrimitiveFieldTaint(object, field.getName()), field.getType().isPrimitive(), depth + 1);
                        Map<String,Object> leaf=(Map<String,Object>)fields.get(path+"#"+field.getName());
                        if (leaf!=null) leaf.putAll(instance("fieldCoordinate",new Class[]{Object.class,String.class},object,
                            current.getName().replace('.','/')+"."+field.getName()));
                    }
                }
            }
        }
    }
    private static boolean typeMetadata(Class<?> type) {
        for (Class<?> current = type; current != null; current = current.getSuperclass())
            if (current.getName().equals("org.springframework.core.ParameterizedTypeReference")) return true;
        return false;
    }

    public static void collect(String owner, String method, Object value) {
        boolean rpc = owner.equals("org.springframework.web.client.RestTemplate") && method.startsWith("exchange:");
        String id = UUID.randomUUID().toString();
        if (rpc) RPC.get().push(id);
        if (rpc) instance("rpcStarted",new Class[]{String.class},id);
        emit(id, rpc ? "rpc-request" : "sink", owner, method, value, value instanceof Object[], null);
    }
    public static void sourceCompleted(String owner, String method, Object value) {
        if (!owner.equals("org.springframework.web.client.RestTemplate") || RPC.get().isEmpty()) return;
        String request = RPC.get().pop();
        if (RPC.get().isEmpty()) RPC.remove();
        emit(UUID.randomUUID().toString(), "rpc-response", owner, method, value, false, request);
    }
    public static Object beginTask() {
        Deque<String> previous = RPC.get();
        RPC.set(new ArrayDeque<String>());
        return previous;
    }
    @SuppressWarnings("unchecked")
    public static void endTask(Object previous) {
        Deque<String> pending = RPC.get();
        while (!pending.isEmpty()) emit(UUID.randomUUID().toString(), "rpc-aborted",
            "org.springframework.web.client.RestTemplate", "task-exit-without-response", null, false, pending.pop());
        Deque<String> prior = (Deque<String>) previous;
        if (prior.isEmpty()) RPC.remove(); else RPC.set(prior);
    }
    private static String mdc(String key) {
        try {
            Class<?> type = Class.forName("org.slf4j.MDC", false, Thread.currentThread().getContextClassLoader());
            return (String) type.getMethod("get", String.class).invoke(null, key);
        } catch (ReflectiveOperationException ignored) { return null; }
    }
    @SuppressWarnings("unchecked")
    private static Map<String,Object> instance(String name,Class<?>[] types,Object...args){
        if (!Boolean.getBoolean("tf2.mt.instances")) return Collections.emptyMap();
        try {
            Object value=Class.forName("CommonHttpInstanceAgent").getMethod(name,types).invoke(null,args);
            return value==null?Collections.emptyMap():(Map<String,Object>)value;
        } catch(Exception e){throw new IllegalStateException("Instance evidence failed: "+name,e);}
    }
    private static void emit(String id, String phase, String owner, String method, Object value, boolean arguments, String request) {
        try {
            Map<String, Object> event = new LinkedHashMap<>();
            event.put("schema_version", 1); event.put("event_id", id); event.put("phase", phase);
            event.put("owner", owner); event.put("method", method); event.put("rpc_request_event", request);
            event.put("thread_id", Thread.currentThread().getId()); event.put("thread_name", Thread.currentThread().getName());
            event.put("trace_id", mdc("X-B3-TraceId") != null ? mdc("X-B3-TraceId") : mdc("traceId"));
            event.put("span_id", mdc("X-B3-SpanId") != null ? mdc("X-B3-SpanId") : mdc("spanId"));
            event.put("available", TaintHeap.available());
            event.put("instance_context",instance("currentContext",new Class[0]));
            Scan scan = new Scan();
            if (arguments) {
                Object[] args = (Object[]) value;
                for (int i = 0; i < args.length; i++) scan.walk(args[i], "arg" + (i + 1), null, false, 0);
            } else scan.walk(value, phase.equals("rpc-response") ? "result" : "arg", null, false, 0);
            Map<String,Object> exported=scan.fields;
            if (Boolean.getBoolean("tf2.mt.sourceIdsOnly")) {
                String target=System.getProperty("tf2.mt.export.target");
                if(target==null||target.isEmpty())throw new IllegalStateException("Explicit query target required");
                exported=new LinkedHashMap<>();
                for(Map.Entry<String,Object> entry:scan.fields.entrySet()) {
                    Map<String,Object> leaf=(Map<String,Object>)entry.getValue();
                    // Keep every candidate source field, not a list of expected
                    // origins. Only the requested sink field is projected.
                    boolean keep=phase.equals("rpc-response")&&leaf.containsKey("owner")&&leaf.containsKey("field")&&leaf.containsKey("tag")
                        ||phase.equals("sink")&&target.equals(leaf.get("field"));
                    if(!keep)continue;
                    Object raw=leaf.get("tag");
                    if(raw instanceof A) {
                        A tag=(A)raw;Map<String,Object> compact=new LinkedHashMap<>();
                        List<Map<String,Object>> ids=new ArrayList<>();
                        if(tag.A()!=null)for(com.shadow.taint.agent.model.C source:tag.A()) {
                            Map<String,Object> tokenId=new LinkedHashMap<>();tokenId.put("A",source.C());ids.add(tokenId);
                        }
                        compact.put("A",tag.A()==null?null:ids);leaf.put("tag",compact);
                    }
                    exported.put(entry.getKey(),leaf);
                }
                event.put("export_profile","native-source-ids-query-target-v1");
                event.put("export_target",target);
            }
            event.put("fields", exported); event.put("omissions", scan.omissions);
            event.put("capture_complete", scan.omissions.isEmpty());
            Path log = Paths.get(System.getProperty("user.home"), "AgentLogs", "ShadowTaint",
                System.getProperty("taint.version"), "adapted-events.jsonl");
            byte[] bytes = (new GsonBuilder().serializeNulls().create().toJson(event) + "\n").getBytes(StandardCharsets.UTF_8);
            synchronized (LOCK) {
                Files.createDirectories(log.getParent());
                Files.write(log, bytes, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            }
        } catch (Throwable error) {
            System.err.println("TF2_MT_ADAPTER error mode=logging cause=" + error);
        }
    }
}
