import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Unknown constructors may legitimately change mutable argument state. */
public class OpaqueDateConstructorFixture {
    public static class Out {public Date date;public Out(Date d){date=d;}public Date getDate(){return date;}}
    public static class Base {public Base(Date date,boolean fail){date.setTime(2000);if(fail)throw new IllegalArgumentException("expected");}}
    public static class Mutator extends Base {public Mutator(Date date){super(date,false);}}
    public static class Throwing extends Base {public Throwing(Date date){super(date,true);}}
    public static Out root(Date date,int mode){
        if(mode==0)return new Out(date);
        if(mode==1){new Mutator(date);return new Out(date);}
        if(mode==2){long copied=date.getTime();new Mutator(date);return new Out(new Date(copied));}
        if(mode==3){try{new Throwing(date);}catch(IllegalArgumentException e){return new Out(date);}}
        if(mode==4){new Throwing(date);return new Out(date);}
        new Mutator(date);return new Out(new Date(date.getTime()));
    }
    public static void main(String[] args)throws Exception{
        ObjectMapper json=new ObjectMapper();List<Map<String,Object>> cases=new ArrayList<>();
        for(int i=0;i<12;i++){
            W3CTraceContext c=W3CTraceContext.server("00-66666666666666666666666666666666-"+String.format("%016x",i+1)+"-01","fixture=opaque-date-ctor");SpringTransportAgent.Transport.ASYNC.set(c);Map row=new LinkedHashMap();row.put("mode",i%6);row.put("message",c.fields().get("message"));
            try{Out result=root(new Date(1000),i%6);ResponseBindingHooks.verifySerialization(result,json);row.put("response",json.readValue(json.writeValueAsString(result),Map.class));row.put("status","normal");Map wire=c.fields();wire.put("uri","fixture:opaque-date-constructor");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}}
            catch(IllegalArgumentException expected){row.put("status","aborted");}
            cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(json.writeValueAsString(cases));
    }
}
