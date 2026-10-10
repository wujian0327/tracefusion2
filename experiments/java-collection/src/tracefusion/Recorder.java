package tracefusion;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Diagnostic collector, not a taint engine. No application equals/hashCode/toString calls. */
public final class Recorder {
    private static BufferedWriter out;
    private static long seq, frames, firstThread = -1;
    private static int limit;
    private static final IdentityHashMap<Object, Integer> objects = new IdentityHashMap<>();
    private static final Map<String, Integer> versions = new HashMap<>();
    private static final Map<Long, Deque<Long>> stacks = new HashMap<>();
    private static final Set<String> problems = new LinkedHashSet<>();
    private static int transformed;
    private static boolean ended;

    public static synchronized void start(Path file, int maxEvents) throws IOException {
        if (maxEvents < 2) throw new IllegalArgumentException("maxEvents must be at least 2");
        limit = maxEvents;
        // Never silently replace a previous capture.
        out = Files.newBufferedWriter(file, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        row("start", "", 0, new Object[]{"java-collection-v1", System.getProperty("java.runtime.version"),
            System.getProperty("tracefusion.mode", "full"), System.getProperty("tracefusion.scopeHash", "")});
        Runtime.getRuntime().addShutdownHook(new Thread(Recorder::finish, "tracefusion-finish"));
    }
    public static synchronized String ref(Object o) {
        if (o == null) return "o0";
        Integer id = objects.get(o);
        if (id == null) {
            if (objects.size() >= limit) { problem("object_limit"); return "unknown"; }
            id = objects.size() + 1;
            objects.put(o, id); // Strong references deliberately retain identity across moving GC.
        }
        return "o" + id;
    }
    private static Deque<Long> stack() {
        long t = Thread.currentThread().getId();
        if (firstThread < 0) firstThread = t;
        if (t != firstThread) problem("multiple_application_threads");
        return stacks.computeIfAbsent(t, k -> new ArrayDeque<>());
    }
    public static synchronized void enter(String method, Object[] args) {
        Deque<Long> s = stack();
        long parent = s.isEmpty() ? 0 : s.peek();
        long f = ++frames;
        s.push(f);
        Object[] a = new Object[args.length + 1];
        a[0] = parent;
        System.arraycopy(args, 0, a, 1, args.length);
        row("enter", method, f, a);
    }
    public static synchronized void event(String kind, String site, Object[] values) {
        Deque<Long> s = stack();
        if (s.isEmpty()) problem("event_outside_frame");
        row(kind, site, s.isEmpty() ? 0 : s.peek(), values);
    }
    public static synchronized void exit(String site, Object[] values) {
        event("exit", site, values);
        Deque<Long> s = stack();
        if (!s.isEmpty()) s.pop();
    }
    public static synchronized void field(String kind, String site, Object obj, int value, String key) {
        String id = ref(obj);
        String location = id + ":" + key;
        int version = versions.getOrDefault(location, 0);
        if (kind.equals("write")) versions.put(location, ++version);
        event(kind, site, new Object[]{id, key, value, version});
    }
    public static synchronized void transformed(String name, String sha) {
        transformed++;
        row("class", name, 0, new Object[]{sha});
    }
    public static synchronized void snapshot(String method, int arg, Object obj, String field, int value) {
        if (obj == null) problem("null_snapshot_argument");
        event("snapshot", method, new Object[]{arg, ref(obj), field, value});
    }
    public static synchronized void problem(String why) { problems.add(why); }
    public static synchronized void rejected(String name, String why) {
        problem("rejected_class:" + name + ":" + why);
        row("reject", name, 0, new Object[]{why});
    }
    private static void row(String kind, String site, long frame, Object[] values) {
        if (ended) return;
        if (seq >= limit && !kind.equals("finish")) { problem("event_limit"); return; }
        try {
            out.write("{\"seq\":" + (++seq) + ",\"thread\":" + Thread.currentThread().getId()
                + ",\"frame\":" + frame + ",\"kind\":" + json(kind)
                + ",\"site\":" + json(site) + ",\"values\":" + json(values) + "}\n");
        } catch (IOException e) {
            // No further collection claim is possible. Do not let business continue silently.
            System.err.println("TraceFusion trace write failed: " + e);
            Runtime.getRuntime().halt(74);
        }
    }
    private static synchronized void finish() {
        if (ended) return;
        if (frames == 0 || transformed == 0) problem("empty_capture");
        for (Deque<Long> s : stacks.values()) if (!s.isEmpty()) problem("incomplete_frames");
        row("finish", "", 0, new Object[]{problems.isEmpty() ? "complete" : "unknown",
            problems.toArray(), frames, objects.size(), transformed});
        ended = true;
        try { out.close(); } catch (IOException e) { Runtime.getRuntime().halt(74); }
    }
    public static String json(Object v) {
        if (v == null) return "null";
        if (v instanceof Number || v instanceof Boolean) return v.toString();
        if (v instanceof Object[]) {
            StringJoiner j = new StringJoiner(",", "[", "]");
            for (Object x : (Object[])v) j.add(json(x));
            return j.toString();
        }
        StringBuilder s = new StringBuilder("\"");
        for (char c : ((String)v).toCharArray()) {
            if (c == '"' || c == '\\') s.append('\\').append(c);
            else if (c < 32) s.append(String.format("\\u%04x", (int)c));
            else s.append(c);
        }
        return s.append('"').toString();
    }
}
