import java.util.*;
import java.util.function.Predicate;
import com.fasterxml.jackson.databind.ObjectMapper;

public class NonemptySelectionFixture {
    public static class Box {
        public int id; public String text;
        public Box(int id, String text) { this.id=id; this.text=text; }
        public int getId(){ return id; } public String getText(){ return text; }
    }
    public static class Choice { public int index; public Choice(int index){this.index=index;} public int getIndex(){return index;} }
    public static class Store { public Box read(int n){return new Box(n,"SAME");} }
    public static class Gate { public Choice read(int n){return new Choice(n);} }
    public static class Out { public List<Box> items; public Out(List<Box> items){this.items=items;} public List<Box> getItems(){return items;} }
    public List<Box> last;
    public Out root(Store store, Gate gate, int mode, Predicate<Box> opaque) {
        List<Box> items=new ArrayList<>(); items.add(store.read(0)); items.add(store.read(1));
        Choice choice=gate.read(mode==1?1:0);
        if(mode==2) items.removeIf(opaque);
        else items.removeIf(b -> b.id!=choice.index);
        last=items; return new Out(items);
    }
    public static void main(String[] args) throws Exception {
        boolean observe=Boolean.getBoolean("fixture.observe");
        ObjectMapper mapper=new ObjectMapper(); List<Map> results=new ArrayList<>();
        NonemptySelectionFixture fixture=new NonemptySelectionFixture();
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
