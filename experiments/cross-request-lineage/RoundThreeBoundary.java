import java.util.*;
import lineage.web.Server;

/** Real carrier/bytes evidence; no labels, field maps or fabricated executions. */
public final class RoundThreeBoundary implements RoundThreeObserver {
    final TraceBoundary boundary=new TraceBoundary();
    public void enter(String role,String parent,String uri){boundary.enter(role,parent,uri);}
    public String client(String uri,String parent){return boundary.client(uri,parent);}
    public void clientEnd(){boundary.clientEnd();}
    static String hash(Class<?> c)throws Exception {try(java.io.InputStream in=c.getResourceAsStream("/"+c.getName().replace('.','/')+".class")){java.io.ByteArrayOutputStream b=new java.io.ByteArrayOutputStream();byte[] x=new byte[4096];for(int n;(n=in.read(x))>=0;)b.write(x,0,n);return PlannedServiceAgent.Recorder.hash(b.toByteArray());}}
    public void wire(Object carrier,Object dto,byte[] bytes,String[] connection,String parent,String direction,String phase,int status)throws Exception {
        synchronized(PlannedServiceAgent.Recorder.class){
            Map<String,Object> r=boundary.rpc==null?boundary.current.fields():new LinkedHashMap<>(boundary.rpc);
            r.put("uri",boundary.uri);r.put("direction",direction);r.put("phase",phase);r.put("carrier",PlannedServiceAgent.Recorder.id(carrier));r.put("connection",Arrays.asList(connection));
            r.put("wire_traceparent",parent);r.put("wire_sha256",PlannedServiceAgent.Recorder.hash(bytes));r.put("wire_utf8",new String(bytes,java.nio.charset.StandardCharsets.UTF_8));
            r.put("method","POST");r.put("path","/call");r.put("status",status);r.put("normal_complete",true);r.put("http_exchange_version",1);
            r.put("adapter_sha256",hash(RoundThreeBoundary.class));r.put("server_sha256",hash(RoundThreeServer.class));
            PlannedServiceAgent.Recorder.emit("http-exchange",new LinkedHashMap<>(r));
            r.remove("wire_utf8");r.put("fields",SpringTransportAgent.Transport.snapshot(dto));
            if(direction.equals("response")&&phase.equals("write"))ResponseBindingHooks.verifySerialization(dto,Server.JSON);
            PlannedServiceAgent.Recorder.emit("http-json",r);
        }
    }
    public void leave(){Map<String,Object> r=new LinkedHashMap<>();r.put("message",boundary.server.message());r.put("monitor",MonitorSafety.inspect());PlannedServiceAgent.Recorder.emit("session-request-cleanup",r);boundary.leave();}
}
