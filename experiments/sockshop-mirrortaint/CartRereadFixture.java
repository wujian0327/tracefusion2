import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Independent literal cases; source boundary is Repo.read, never save. */
public class CartRereadFixture {
    public static class Item {
        public String text;
        public Item(String text){List<Object> local=new ArrayList<>();this.text=text;}
        public String getText(){return text;}
    }
    public static class Repo {
        public Item read(Item old,int kind){return kind==0?new Item("SAME"):old;}
    }
    static void opaque(Item x){int[] unmodeled=new int[1];x.text="SAME";}
    static Item cycle(Item x,int count){if(count==0)return x;return cycle(x,count-1);}
    public static Item root(Item left,Repo repo,int mode){
        if(mode==0){opaque(left);return repo.read(left,0);}
        if(mode==1){opaque(left);return repo.read(left,1);}
        if(mode==2){Item early=new Item("SAME");opaque(left);return repo.read(early,1);}
        if(mode==3){Item x=repo.read(left,0);opaque(x);return x;}
        if(mode==4)return cycle(repo.read(left,0),3);
        if(mode==5){Item x=repo.read(left,0);opaque(left);return repo.read(x,1);}
        if(mode==6){opaque(left);return cycle(repo.read(left,0),3);}
        return new Item("constant");
    }
    public static void main(String[] args)throws Exception{
        ObjectMapper json=new ObjectMapper();List<Map<String,Object>> cases=new ArrayList<>();Repo repo=new Repo();
        for(int i=0;i<16;i++){
            W3CTraceContext c=W3CTraceContext.server("00-33333333333333333333333333333333-"+String.format("%016x",i+1)+"-01","fixture=reread");SpringTransportAgent.Transport.ASYNC.set(c);
            Item left=new Item("SAME");Item result=root(left,repo,i%8);ResponseBindingHooks.verifySerialization(result,json);
            Map row=new LinkedHashMap();row.put("mode",i%8);row.put("message",c.fields().get("message"));row.put("response",json.readValue(json.writeValueAsString(result),Map.class));cases.add(row);
            Map wire=c.fields();wire.put("uri","fixture:reread");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(json.writeValueAsString(cases));
    }
}
