import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.core.JsonGenerator;
import java.io.IOException;

/** Standalone serializer/identity controls; never substituted for a business JAR. */
public class BindingSemanticFixture {
    public static class Input {
        public String text;public Map<String,String> cells=new HashMap<>();
        public Input(String text){this.text=text;cells.put("k",text);cells.put("other",text);}
        public String getText(){return text;}public void setText(String x){text=x;}
        public Map<String,String> getCells(){return cells;}
    }
    public static class Box {public Object data;public Box(Object data){this.data=data;}public Object getData(){return data;}}
    public static class Output {public boolean flag;public void setFlag(boolean f){flag=f;}public boolean isFlag(){return flag;}}
    public static Input direct(Input x){return x;}
    public static Box nested(Input x){return new Box(x);}
    public static Box choose(Input left,Input right,boolean pick){return new Box(pick?left:right);}
    public static Input opaqueIdentity(Input x){return x;}
    public static Input opaque(Input x){return opaqueIdentity(x);}
    public static Input overwrite(Input x){x.setText("SAME");return x;}
    public static Box map(Input x){return new Box(x.getCells());}
    public static Output constant(Input x){Output r=new Output();r.setFlag(true);return r;}
    static void publish(Object result,W3CTraceContext context)throws Exception{
        Map row=context.fields();row.put("uri","fixture:actual-jackson-serialization");row.put("direction","response");row.put("phase","write");
        row.put("fields",SpringTransportAgent.Transport.snapshot(result));
        ObjectMapper mapper=new ObjectMapper();ResponseBindingHooks.verifySerialization(result,mapper);
        String actual=mapper.writeValueAsString(result);System.out.println(actual);
        synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",row);}
    }
    static class SameValueSerializer extends JsonSerializer<String>{public void serialize(String value,JsonGenerator generator,SerializerProvider provider)throws IOException{generator.writeString("SAME");}}
    public static void main(String[] args)throws Exception{
        Input left=new Input("SAME"),right=new Input("SAME");
        for(int i=0;i<6;i++){
            String span=String.format("%016x",i+1);W3CTraceContext context=W3CTraceContext.server("00-11111111111111111111111111111111-"+span+"-01","fixture=serialization");
            SpringTransportAgent.Transport.ASYNC.set(context);Object result;
            if(args[0].equals("custom-serializer")){
                result=nested(left);ObjectMapper mapper=new ObjectMapper();SimpleModule module=new SimpleModule();module.addSerializer(String.class,new SameValueSerializer());mapper.registerModule(module);
                if(!mapper.writeValueAsString(result).contains("SAME"))throw new AssertionError();
                try{ResponseBindingHooks.verifySerialization(result,mapper);throw new AssertionError("Custom equal-value serializer accepted");}
                catch(IllegalStateException expected){System.out.println("CUSTOM_SERIALIZER_REJECTED="+expected.getMessage());}return;
            }
            switch(args[0]){
                case "direct":result=direct(i%2==0?left:right);break;
                case "nested":result=nested(i%2==0?left:right);break;
                case "choose":result=choose(left,right,i%2==0);break;
                case "opaque":result=opaque(left);break;
                case "overwrite":result=overwrite(left);break;
                case "map":result=map(left);break;
                case "constant":result=constant(left);break;
                default:throw new IllegalArgumentException(args[0]);
            }
            publish(result,context);SpringTransportAgent.Transport.ASYNC.remove();
        }
    }
}
