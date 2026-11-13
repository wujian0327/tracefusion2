import java.util.*;
import java.security.MessageDigest;
import lineage.web.Observer;

/** JDK HTTP codec adapter; delegates all IDs, versions and snapshots to existing code. */
public final class TraceBoundary implements Observer {
    W3CTraceContext server, current;
    String uri;
    Map<String,Object> rpc;
    public void enter(String role, String parent, String uri) {
        this.uri = uri; server = W3CTraceContext.server(parent, null); current = server;
        SpringTransportAgent.Transport.ASYNC.set(server);
    }
    public String client(String uri, String unused) {
        current = W3CTraceContext.client(server); this.uri = uri;
        rpc = current.fields(); rpc.put("uri", uri); rpc.put("method", "POST"); rpc.put("parent_message", server.message());
        PlannedServiceAgent.Recorder.emit("http-rpc-enter", new LinkedHashMap<>(rpc));
        return current.wire();
    }
    public void json(Object body, String direction, String phase, byte[] bytes) throws Exception {
        synchronized (PlannedServiceAgent.Recorder.class) {
            Map<String,Object> row = rpc == null ? current.fields() : new LinkedHashMap<>(rpc);
            row.put("uri", uri); row.put("direction", direction); row.put("phase", phase);
            row.put("fields", SpringTransportAgent.Transport.snapshot(body));
            row.put("wire_sha256", PlannedServiceAgent.Recorder.hash(bytes));
            if (phase.equals("write") && direction.equals("response")) ResponseBindingHooks.verifySerialization(body, lineage.web.Server.JSON);
            PlannedServiceAgent.Recorder.emit("http-json", row);
        }
    }
    public void clientEnd() {
        PlannedServiceAgent.Recorder.emit("http-rpc-exit", new LinkedHashMap<>(rpc));
        rpc = null; current = server; uri = "/call";
    }
    public void leave() { SpringTransportAgent.Transport.ASYNC.remove(); }
}
