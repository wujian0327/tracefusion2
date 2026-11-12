import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Preallocated exceptions isolate dispatch from unclosed Throwable construction. */
public class ExceptionDispatchFixture {
    public static class Base extends RuntimeException {}
    public static class Mid extends Base {}
    public static class Leaf extends Mid {}
    public static class Other extends Base {}
    public static class Datum {public int value;public Datum(int v){value=v;}public int getValue(){return value;}}
    public static class Store {public Datum read(int key,int v){return new Datum(v);}}
    public static class Out {public int value;public Out(int v){value=v;}public int getValue(){return value;}}
    public void inner(int unused,int gate,Base error){if(gate>0)throw error;}
    public void middle(int unused,int gate,Base error){inner(unused,gate,error);}
    public Out root(Store store,int scenario,int input,Base original){
        Datum a=store.read(10,7),b=store.read(11,7),g=store.read(20,input);int result;
        if(scenario==0){try{inner(b.value,g.value,original);result=a.value;}catch(Base e){result=b.value;}}
        else if(scenario==1){try{middle(b.value,g.value,original);result=a.value;}catch(Base e){result=b.value;}}
        else if(scenario==2){try{middle(b.value,g.value,original);result=a.value;}catch(Other e){result=9;}catch(Mid e){result=b.value;}catch(Base e){result=11;}}
        else if(scenario==3){try{middle(b.value,g.value,original);result=a.value;}catch(Base e){result=b.value;}finally{int scratch=3;}}
        else if(scenario==4){try{try{middle(b.value,g.value,original);result=a.value;}catch(Base e){throw e;}}catch(RuntimeException e){result=b.value;}}
        else if(scenario==5){middle(b.value,g.value,original);result=a.value;}
        else {try{middle(b.value,g.value,original);}finally{return new Out(9);}}
        return new Out(result);
    }
    public static void main(String[] args)throws Exception{
        boolean observe=Boolean.getBoolean("fixture.observe");ObjectMapper mapper=new ObjectMapper();ExceptionDispatchFixture f=new ExceptionDispatchFixture();List<Map> all=new ArrayList<>();Base original=new Leaf();
        for(int s=0;s<7;s++)for(int n=0;n<2;n++){
            W3CTraceContext ctx=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(ctx);
            Out result=null;boolean aborted=false;try{result=f.root(new Store(),s,n,original);}catch(Base e){if(e!=original)throw new AssertionError();aborted=true;}
            if(observe&&!aborted){ResponseBindingHooks.verifySerialization(result,mapper);Map wire=ctx.fields();wire.put("uri",null);wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));PlannedServiceAgent.Recorder.emit("http-json",wire);}
            Map row=new LinkedHashMap();row.put("scenario",s);row.put("input",n);row.put("value",aborted?null:result.value);row.put("aborted",aborted);row.put("message",ctx.message());all.add(row);if(observe)SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(mapper.writeValueAsString(all));
    }
}
