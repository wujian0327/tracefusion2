import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Raw source slots include null and equal scalars; no provenance oracle code. */
public class MemberIdentityRuleFixture {
    public static class Out { public String text; public Out(String s){text=s;} public String getText(){return text;} }
    public static class Store { public Out read(int slot){return new Out(slot==0?null:"SAME");} }
    public static Out root(Store store,int mode){
        List<String> values=new ArrayList<>();
        values.add(store.read(0).getText());values.add(store.read(1).getText());values.add(store.read(2).getText());
        return new Out(mode==3?null:values.get(mode));
    }
    public static void main(String[] args)throws Exception {
        ObjectMapper json=new ObjectMapper();List<Map> results=new ArrayList<>();
        for(int mode=0;mode<4;mode++){
            W3CTraceContext c=W3CTraceContext.server("00-11111111111111111111111111111111-"+String.format("%016x",mode+1)+"-01",null);
            SpringTransportAgent.Transport.ASYNC.set(c);
            try {Out out=root(new Store(),mode);Map row=new LinkedHashMap();row.put("case",mode);row.put("value",out.text);row.put("message",c.message());results.add(row);}
            finally {SpringTransportAgent.Transport.ASYNC.remove();}
        }
        System.out.println(json.writeValueAsString(results));
    }
}
