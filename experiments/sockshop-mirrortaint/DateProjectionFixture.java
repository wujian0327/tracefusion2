import java.util.*;
import com.fasterxml.jackson.databind.*;

/** Independent literal field-instance expectations live in the experiment driver. */
public class DateProjectionFixture {
    public static class Input {public Date date;public long millis;public Input(){date=new Date(1700000000123L);millis=1700000000123L;}public Date getDate(){return date;}public long getMillis(){return millis;}}
    public static class Out {public Date date;public String other;public Out(Date d){date=d;}public Date getDate(){return date;}public String getOther(){return other;}}
    static Date opaque(Date d){int[] unsupported=new int[1];return d;}
    static Out save(Out d){int[] unsupported=new int[1];return d;}
    public static Out direct(Date date,long millis,boolean useDate){return new Out(useDate?date:new Date(millis));}
    public static Out forward(Out in,int mode){if(mode==1)in.getDate().setTime(1700000000123L);if(mode==2)in.getDate().setTime(1800000000123L);if(mode==3)return save(in);return in;}
    public static Out root(Input left,Input right,int mode){
        if(mode==0)return new Out(left.getDate());
        if(mode==1)return new Out(right.getDate());
        if(mode==2)return new Out(new Date(left.getMillis()));
        if(mode==3)return new Out(Calendar.getInstance().getTime());
        if(mode==4)return new Out(new Date());
        if(mode==5)return new Out(new Date(left.getDate().getTime()));
        if(mode==6){Out out=new Out(left.getDate());out.other="unrelated";return out;}
        if(mode==7)return new Out(opaque(left.getDate()));
        if(mode==8){Date d=left.getDate();d.setTime(d.getTime());return new Out(d);}
        if(mode==9){Date d=left.getDate();d.setTime(1800000000123L);return new Out(d);}
        if(mode==10)return save(new Out(left.getDate()));
        if(mode==11){try{Date d=null;return new Out(new Date(d.getTime()));}catch(NullPointerException e){return new Out(new Date(right.getMillis()));}}
        if(mode==12){Date d=null;return new Out(new Date(d.getTime()));}
        if(mode==13)return new Out(null);
        if(mode==14)return new Out(new Date(1700000000123L));
        if(mode==15){Calendar c=Calendar.getInstance();c.setTime(left.getDate());return new Out(c.getTime());}
        Out out=new Out(left.getDate());out.date=new Date(1700000000123L);return out;
    }
    public static void main(String[] args)throws Exception{
        ObjectMapper json=new ObjectMapper();if(args.length==0)json.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        if(args.length>0&&args[0].equals("forward")){
            json.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);List<Map> cases=new ArrayList<>();for(int i=0;i<8;i++){
                W3CTraceContext c=W3CTraceContext.server("00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-"+String.format("%016x",i+1)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(c);Out out=forward(new Out(new Date(1700000000123L)),i%4);ResponseBindingHooks.verifySerialization(out,json);Map row=new LinkedHashMap();row.put("message",c.fields().get("message"));row.put("mode",i%4);row.put("response",json.readValue(json.writeValueAsString(out),Map.class));cases.add(row);Map wire=c.fields();wire.put("uri","fixture:forward-date");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(out));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}
            }System.out.println(json.writeValueAsString(cases));return;
        }
        if(args.length>0&&args[0].equals("direct")){
            json.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);List<Map> cases=new ArrayList<>();for(int i=0;i<4;i++){
                W3CTraceContext c=W3CTraceContext.server("00-99999999999999999999999999999999-"+String.format("%016x",i+1)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(c);Out out=direct(new Date(1700000000123L),1700000000123L,i%2==0);ResponseBindingHooks.verifySerialization(out,json);Map row=new LinkedHashMap();row.put("message",c.fields().get("message"));row.put("argument",i%2==0?0:1);row.put("response",json.readValue(json.writeValueAsString(out),Map.class));cases.add(row);Map wire=c.fields();wire.put("uri","fixture:direct-date");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(out));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}
            }System.out.println(json.writeValueAsString(cases));return;
        }
        if(args.length>0&&args[0].startsWith("custom")){
            if(args[0].equals("custom-format"))json.setDateFormat(new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ"));
            else {com.fasterxml.jackson.databind.module.SimpleModule module=new com.fasterxml.jackson.databind.module.SimpleModule();module.addSerializer(Date.class,new JsonSerializer<Date>(){public void serialize(Date value,com.fasterxml.jackson.core.JsonGenerator writer,SerializerProvider provider)throws java.io.IOException{writer.writeNumber(value.getTime());}});json.registerModule(module);}
            SpringTransportAgent.Transport.ASYNC.set(W3CTraceContext.server("00-88888888888888888888888888888888-1111111111111111-01",null));Out out=root(new Input(),new Input(),0);try{ResponseBindingHooks.verifySerialization(out,json);throw new AssertionError("Custom Date serializer accepted");}catch(IllegalStateException expected){System.out.println("DATE_SERIALIZER_REJECTED="+expected.getMessage());}return;
        }
        List<Map> cases=new ArrayList<>();
        for(int i=0;i<34;i++){
            Input left=new Input(),right=new Input();int mode=i%17;W3CTraceContext c=W3CTraceContext.server("00-77777777777777777777777777777777-"+String.format("%016x",i+1)+"-01","fixture=dates");SpringTransportAgent.Transport.ASYNC.set(c);Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",c.fields().get("message"));
            try{Out out=root(left,right,mode);ResponseBindingHooks.verifySerialization(out,json);row.put("response",json.readValue(json.writeValueAsString(out),Map.class));row.put("status","normal");Map wire=c.fields();wire.put("uri","fixture:date");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(out));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}}
            catch(NullPointerException expected){row.put("status","aborted");}cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();
        }System.out.println(json.writeValueAsString(cases));
    }
}
