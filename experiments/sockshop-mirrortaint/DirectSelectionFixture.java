import java.util.*;
import java.util.function.Predicate;
import com.fasterxml.jackson.databind.ObjectMapper;

public class DirectSelectionFixture {
    public static class Box {
        public int id; public String text;
        public Box(int id, String text) { this.id=id; this.text=text; }
        public int getId(){ return id; } public String getText(){ return text; }
    }
    public static class Flag {public boolean drop;public Flag(boolean drop){this.drop=drop;}public boolean isDrop(){return drop;}}
    public static class Choice {public List<Flag> flags;public Choice(List<Flag> flags){this.flags=flags;}public List<Flag> getFlags(){return flags;}}
    public static class Store { public Box read(int n){return new Box(n,"SAME");} }
    public static class Gate { public Choice read(int n){List<Flag> flags=new ArrayList<>();flags.add(new Flag(n==1));flags.add(new Flag(n!=1));return new Choice(flags);} }
    public static class Out { public List<Box> items; public Out(List<Box> items){this.items=items;} public List<Box> getItems(){return items;} }
    public List<Box> last;
    public Out root(Store store, Gate gate, int mode, Predicate<Box> opaque) {
        List<Box> items=new ArrayList<>(); items.add(store.read(0)); items.add(store.read(1));
        Choice choice=gate.read(mode==1?1:0);
        Iterator<Flag> decisions=choice.flags.iterator();
        if(mode==2) items.removeIf(opaque);
        else items.removeIf(b -> decisions.next().drop);
        last=items; return new Out(items);
    }
    public static void main(String[] args) throws Exception {
        boolean observe=Boolean.getBoolean("fixture.observe");
        ObjectMapper mapper=new ObjectMapper(); List<Map> results=new ArrayList<>();
        DirectSelectionFixture fixture=new DirectSelectionFixture();
        for(int mode:new int[]{0,1,2}) {
            W3CTraceContext ctx=W3CTraceContext.server(null,null);
            if(observe) SpringTransportAgent.Transport.ASYNC.set(ctx);
            Out result=fixture.root(new Store(),new Gate(),mode,new Predicate<Box>(){public boolean test(Box b){return false;}});
            if(observe) {
                ResponseBindingHooks.verifySerialization(result,mapper);
                Map wire=ctx.fields(); wire.put("uri",null); wire.put("direction","response");wire.put("phase","write");
                wire.put("fields",SpringTransportAgent.Transport.snapshot(result));PlannedServiceAgent.Recorder.emit("http-json",wire);
            }
            Map r=new LinkedHashMap();r.put("case",mode);r.put("message",ctx.message());
            r.put("items",mapper.readValue(mapper.writeValueAsString(result.items),List.class));results.add(r);
            if(observe)SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(mapper.writeValueAsString(results));
    }
}
