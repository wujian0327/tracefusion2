import lineage.web.Observer;
import lineage.business.Cache;
import com.shadow.taint.agent.runtime.*;
import com.shadow.taint.agent.model.A;
import com.shadow.taint.agent.model.C;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Public source/sink API only. No transport labels, propagation rules or inferred links. */
public final class MirrorBoundary implements Observer {
    String role, message;
    static final ObjectMapper JSON = new ObjectMapper();
    void emit(Map<String,Object> row) throws Exception {
        row.put("role", role); row.put("message", message); row.put("thread", Thread.currentThread().getId());
        Files.write(Paths.get(System.getProperty("lineage.native")), (JSON.writeValueAsString(row)+"\n").getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }
    static List<String> ids(Object value) {
        A tag = TaintHeap.queryTaint(value); List<String> result = new ArrayList<>();
        if (tag != null && tag.A() != null) for (C source : tag.A()) result.add(source.C());
        return result;
    }
    public void enter(String role, String parent, String uri) throws Exception {
        this.role = role; this.message = parent;
        // Keep the same thread-local heap across every request in this service.
        if (!TaintHeap.available()) { TaintHeap.startup(); Map<String,Object> r = new LinkedHashMap<>(); r.put("kind", "startup"); emit(r); }
    }
    public void json(Object body, String direction, String phase, byte[] bytes) throws Exception {
        if (body instanceof Cache.Request && direction.equals("request") && phase.equals("read") && role.equals(System.getProperty("lineage.source.role", "A"))) {
            Cache.Request input = (Cache.Request)body;
            for (String field : Arrays.asList("value", "fallback")) {
                Object value = Cache.Request.class.getField(field).get(input);
                String label = "external/"+message+"/"+field;
                TaintTagger.tagManually(value, label);
                Map<String,Object> r = new LinkedHashMap<>(); r.put("kind", "source"); r.put("path", "/"+field); r.put("configured_label", label); r.put("native_ids", ids(value)); emit(r);
            }
        }
        if (body instanceof Cache.Reply && direction.equals("response") && phase.equals("write")) {
            Map<String,Object> r = new LinkedHashMap<>(); r.put("kind", "sink"); r.put("path", "/text");
            r.put("native_ids", ids(((Cache.Reply)body).text)); emit(r);
        }
    }
}
