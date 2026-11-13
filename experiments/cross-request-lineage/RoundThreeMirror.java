import lineage.business.Cache;
import com.shadow.taint.agent.runtime.TaintTagger;
import java.util.*;

/** Public API boundary coordinates; no remote tags or local propagation models. */
public final class RoundThreeMirror implements RoundThreeObserver {
    W3CTraceContext server,client;
    final MirrorBoundary boundary=new MirrorBoundary(); String parent,role;
    public void enter(String role,String parent,String uri)throws Exception {boundary.enter(role,parent,uri);this.role=role;this.parent=parent;server=W3CTraceContext.server(parent,null);}
    public String client(String uri,String unused){client=W3CTraceContext.client(server);return client.wire();}
    public void clientEnd(){client=null;boundary.message=parent;}
    public void wire(Object carrier,Object dto,byte[] bytes,String[] connection,String actualParent,String direction,String phase,int status)throws Exception {
        boundary.message=actualParent;
        // A external labels are the original API's source definition.
        boundary.json(dto,direction,phase,bytes);
        boolean local=Boolean.getBoolean("lineage.mirror.local-boundaries")&&phase.equals("read")&&((role.equals("B")&&direction.equals("request"))||(role.equals("A")&&direction.equals("response")));
        for(String field:dto instanceof Cache.Request?Arrays.asList("value","fallback"):Arrays.asList("text")){
            Object value=dto.getClass().getField(field).get(dto);List<String> before=MirrorBoundary.ids(value);
            if(local){TaintTagger.tagManually(value,"intermediate/"+role+"/"+actualParent+"/"+direction+"/"+field);}
            Map<String,Object> r=new LinkedHashMap<>();r.put("kind","boundary");r.put("direction",direction);r.put("phase",phase);r.put("path","/"+field);r.put("connection",Arrays.asList(connection));r.put("wire_utf8",new String(bytes,java.nio.charset.StandardCharsets.UTF_8));r.put("native_ids",MirrorBoundary.ids(value));r.put("pre_native_ids",before);r.put("local_interface_token",local);boundary.emit(r);
        }
    }
}
