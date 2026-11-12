import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** New supplementary cases; never a replacement for PublicControlFixture. */
public class ConstructorScopeFixture {
    public static class Datum {public int value;public Datum(int v){value=v;}public int getValue(){return value;}}
    public static class Store {public Datum read(int key,int v){return new Datum(v);}}
    public static class Out {public int value;public Out(int v){value=v;}public int getValue(){return value;}}
    public static class Plain {public int value;public Datum external;public Plain(Datum d){external=d;value=d.value;}}
    public static class Parent {public int value;public Parent(Datum d){value=d.value;}}
    public static class Child extends Parent {public Datum external;public Child(Datum d,Datum b){super(d);external=d;value=b.value;}}
    public static class Mutating {public int local;public Mutating(Datum d,int v){local=v;d.value=v;}}
    public static class PublishThis {public static Object saved;public Datum external;public PublishThis(Datum d){external=d;saved=this;}}
    public static class PublishArgument {public static Datum saved;public PublishArgument(Datum d){saved=d;}}
    public static class Callback {public Callback(Datum d,int v){touch(d,v);}public void touch(Datum d,int v){d.value=v;}}
    public static class OpaqueCallback extends Callback {public OpaqueCallback(Datum d,int v){super(d,v);}public void touch(Datum d,int v){int[] unmodeled=new int[1];d.value=v;}}
    public static class ThrowsAfter {public int local;public ThrowsAfter(Datum d,int v,int flag,IllegalArgumentException original){local=v;d.value=v;if(flag>0)throw original;}}
    public Out root(Store store,int scenario,int input,IllegalArgumentException original){
        Datum a=store.read(10,7),b=store.read(11,7),g=store.read(20,input);int result;
        if(scenario==0){Plain p=new Plain(a);result=p.value;}
        else if(scenario==1){Child p=new Child(a,b);result=p.value;}
        else if(scenario==2){new Mutating(a,b.value);result=a.value;}
        else if(scenario==3){new PublishThis(a);result=a.value;}
        else if(scenario==4){new PublishArgument(a);result=a.value;}
        else if(scenario==5){new OpaqueCallback(a,b.value);result=a.value;}
        else if(scenario==6){if(g.value>0)new Plain(a);result=a.value;}
        else if(scenario==7){if(g.value>0)new Mutating(a,b.value);result=a.value;}
        else if(scenario==8){try{new ThrowsAfter(a,b.value,g.value,original);result=a.value;}catch(IllegalArgumentException e){if(e!=original)throw e;result=b.value;}finally{int scratch=3;}}
        else{new Callback(a,b.value);result=a.value;}
        return new Out(result);
    }
    public static void main(String[] args)throws Exception{
        boolean observe=Boolean.getBoolean("fixture.observe");ObjectMapper mapper=new ObjectMapper();ConstructorScopeFixture f=new ConstructorScopeFixture();List<Map> all=new ArrayList<>();
        // Supplemental original-object exception comparison only. The old66
        // root keeps its own in-query IllegalArgumentException construction.
        IllegalArgumentException original=new IllegalArgumentException("supplement-only");
        for(int s=0;s<10;s++)for(int n=0;n<2;n++){
            if(args.length>0&&s!=Integer.parseInt(args[0]))continue;
            W3CTraceContext ctx=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(ctx);
            Out result=f.root(new Store(),s,n,original);
            if(observe){ResponseBindingHooks.verifySerialization(result,mapper);Map wire=ctx.fields();wire.put("uri",null);wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));PlannedServiceAgent.Recorder.emit("http-json",wire);}
            Map row=new LinkedHashMap();row.put("scenario",s);row.put("input",n);row.put("value",result.value);row.put("message",ctx.message());all.add(row);
            if(observe)SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(mapper.writeValueAsString(all));
    }
}
