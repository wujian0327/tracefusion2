import java.util.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.core.JsonGenerator;

public class UuidProjectionFixture {
    public static class Box {public UUID id;public Box(UUID v){id=v;}public UUID getId(){return id;}public void setId(UUID v){id=v;}}
    static Box opaque(Box x){int[] unsupported=new int[1];return x;}
    public static Box root(Box a,Box b,int mode){
        if(mode==0)return a;
        if(mode==1||mode==3)return new Box(b.id);
        if(mode==2){Box out=new Box(a.id);out.setId(b.id);return out;}
        if(mode==4)return new Box(null);
        if(mode==5)return new Box(new UUID(1L,2L));
        if(mode==6)return opaque(a);
        if(mode==8){try{Box missing=null;return new Box(missing.getId());}catch(NullPointerException expected){return new Box(b.id);}}
        return b;
    }
    public static void main(String[] args)throws Exception{
        ObjectMapper normal=new ObjectMapper();List<Map> cases=new ArrayList<>();
        for(int i=0;i<20;i++){
            int mode=i%10;Box a=new Box(new UUID(11L,22L)),b=new Box(new UUID(11L,22L));W3CTraceContext c=W3CTraceContext.server("00-66666666666666666666666666666666-"+String.format("%016x",i+1)+"-01","fixture=uuid");SpringTransportAgent.Transport.ASYNC.set(c);Box value=root(a,b,mode);Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",c.fields().get("message"));
            ObjectMapper json=normal;if(mode==9){json=new ObjectMapper();SimpleModule custom=new SimpleModule();custom.addSerializer(UUID.class,new JsonSerializer<UUID>(){public void serialize(UUID x,JsonGenerator out,SerializerProvider p)throws java.io.IOException{out.writeString("SAME");}});json.registerModule(custom);}
            try{ResponseBindingHooks.verifySerialization(value,json);if(mode==9)throw new AssertionError("Custom UUID serializer accepted");row.put("status","normal");row.put("response",json.readValue(json.writeValueAsString(value),Map.class));Map wire=c.fields();wire.put("uri","fixture:uuid");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(value));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}}
            catch(IllegalStateException expected){if(mode!=9)throw expected;row.put("status","serialization-refused");}cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();
        }System.out.println(normal.writeValueAsString(cases));
    }
}
