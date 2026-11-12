import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Same-valued independent reads. Source labels are never inferred from 7. */
public class CallWriteFootprintFixture {
    public static class Datum {public int value; public Datum(int v){value=v;} public int getValue(){return value;}}
    public static class Store {public Datum read(int key,int v){return new Datum(v);}}
    public static class Holder {public Datum child;public Holder(Datum v){child=v;}public Datum getChild(){return child;}}
    public static class Out {public int value;public Out(int v){value=v;}public int getValue(){return value;}}
    public interface Worker {void apply(Holder h,Holder unused,int v);}
    public static class First implements Worker {public void apply(Holder h,Holder unused,int v){h.child.value=v;}}
    public static class Second implements Worker {public void apply(Holder h,Holder unused,int v){Holder alias=h;alias.child.value=v;}}
    public void direct(Datum d,int v){d.value=v;}
    public void nested(Holder h,int v){h.child.value=v;}
    public void alias(Holder h,int v){Holder a=h;a.child.value=v;}
    public void permuted(Holder unused,int v,Holder h){nested(h,v);}
    public void two(Holder x,Holder y,int v){y.child.value=v;}
    public void forward(Holder unused,Holder h,int v){permuted(unused,v,h);}
    public void replace(Holder h,Datum v){h.child=v;h.child.value=7;}
    public Out root(Store store,Worker worker,int scenario,int input){
        Datum a=store.read(10,7),b=store.read(11,7),g=store.read(20,input);
        Holder h=new Holder(a),other=new Holder(b);
        if(scenario==0){if(g.value!=0)direct(a,b.value);}
        else if(scenario==1){if(g.value!=0)nested(h,b.value);}
        else if(scenario==2){if(g.value!=0)alias(h,b.value);}
        else if(scenario==3){if(g.value!=0)permuted(other,b.value,h);}
        else if(scenario==4){if(g.value!=0)two(h,h,b.value);}
        else if(scenario==5){if(g.value!=0)forward(other,h,b.value);}
        else if(scenario==6||scenario==7){if(g.value!=0)worker.apply(h,other,b.value);}
        else if(scenario==8){if(g.value!=0)nested(h,b.value);return new Out(other.child.value);}
        else if(scenario==9){if(g.value!=0)nested(h,b.value);h.child=b;}
        else if(scenario==10){if(g.value!=0)nested(h,b.value);h.child=new Datum(9);}
        return new Out(h.child.value);
    }
    // The untouched branch has a path that can be changed by this very call.
    public Out unclosed(Store store,int input){
        Datum a=store.read(10,7),b=store.read(11,7),g=store.read(20,input);
        Holder h=new Holder(a);if(g.value!=0)replace(h,b);return new Out(h.child.value);
    }
    public static void main(String[] args)throws Exception{
        boolean observe=Boolean.getBoolean("fixture.observe"),limited=args.length>0;
        ObjectMapper mapper=new ObjectMapper();CallWriteFootprintFixture fixture=new CallWriteFootprintFixture();List<Map> results=new ArrayList<>();
        for(int scenario=0;scenario<(limited?1:11);scenario++)for(int input=0;input<2;input++){
            W3CTraceContext ctx=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(ctx);
            Out out=limited?fixture.unclosed(new Store(),input):fixture.root(new Store(),scenario==7?new Second():new First(),scenario,input);
            if(observe){ResponseBindingHooks.verifySerialization(out,mapper);Map wire=ctx.fields();wire.put("uri",null);wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(out));PlannedServiceAgent.Recorder.emit("http-json",wire);}
            Map row=new LinkedHashMap();row.put("scenario",scenario);row.put("input",input);row.put("value",out.value);row.put("message",ctx.message());results.add(row);
            if(observe)SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(mapper.writeValueAsString(results));
    }
}
