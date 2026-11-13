import java.util.*;
import lineage.web.Observer;

/** Same real HTTP/JSON adapter plus same-worker cleanup observations, no labels. */
public final class RoundTwoBoundary implements Observer {
    final TraceBoundary boundary = new TraceBoundary();
    boolean active;
    public void enter(String role,String parent,String uri)throws Exception { active=true; boundary.enter(role,parent,uri); }
    public void json(Object body,String direction,String phase,byte[] bytes)throws Exception { boundary.json(body,direction,phase,bytes); }
    public String client(String uri,String parent)throws Exception { return boundary.client(uri,parent); }
    public void clientEnd()throws Exception { boundary.clientEnd(); }
    public void leave()throws Exception {
        if(active){
            Map<String,Object> row=new LinkedHashMap<>(); row.put("message",boundary.server.message());
            row.put("monitor",MonitorSafety.inspect());
            PlannedServiceAgent.Recorder.emit("session-request-cleanup",row);
        }
        boundary.leave(); active=false;
    }
}
