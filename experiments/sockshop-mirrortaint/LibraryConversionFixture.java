import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.core.JsonGenerator;
import edu.fudan.common.util.JsonUtils;

public class LibraryConversionFixture {
    public static class Input {public String text;public int count;Input(String s,int c){text=s;count=c;}}
    public static class Box {private String text;private int count;public Box(){text="FALLBACK";}public String getText(){return text;}public void setText(String s){text=s;}public int getCount(){return count;}public void setCount(int n){count=n;}}
    @JsonSerialize(using=ForgedSerializer.class) public static class Forged {}
    public static class ForgedSerializer extends JsonSerializer<Forged>{public void serialize(Forged x,JsonGenerator out,SerializerProvider p)throws java.io.IOException{out.writeString("SAME");}}
    static Map opaque(Map map){int[] unsupported=new int[1];return map;}
    public static Box root(Input a,Input b,int mode){
        HashMap<String,Object> m=new HashMap<>();m.put("text",a.text);m.put("count",a.count);
        if(mode==1||mode==2)m.put("text",b.text);
        if(mode==3)m.put("text","SAME");
        if(mode==4)m.put("text",new Forged());
        if(mode==5)m=null;
        if(mode==6){Box direct=new Box();direct.setText((String)m.get("text"));return direct;}
        if(mode==7)opaque(m);
        Box result=(Box)JsonUtils.conveterObject(m,Box.class);return result==null?new Box():result;
    }
    public static void main(String[] ignored)throws Exception{
        ObjectMapper json=new ObjectMapper();List<Map> cases=new ArrayList<>();
        for(int i=0;i<16;i++){
            int mode=i%8;Input a=new Input("SAME",10),b=new Input("SAME",20);W3CTraceContext c=W3CTraceContext.server("00-55555555555555555555555555555555-"+String.format("%016x",i+1)+"-01","fixture=conversion");SpringTransportAgent.Transport.ASYNC.set(c);
            Box result=root(a,b,mode);ResponseBindingHooks.verifySerialization(result,json);Map row=new LinkedHashMap();row.put("message",c.fields().get("message"));row.put("mode",mode);row.put("text",result.getText());cases.add(row);Map wire=c.fields();wire.put("uri","fixture:conversion");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}SpringTransportAgent.Transport.ASYNC.remove();
        }System.out.println(json.writeValueAsString(cases));
    }
}
