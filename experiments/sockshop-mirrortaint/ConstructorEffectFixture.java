import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Constructor behavior only; expected input-instance sources are external. */
public class ConstructorEffectFixture {
    public static class Input {public String text,marker;public Input(String text,String marker){this.text=text;this.marker=marker;}public String getText(){return text;}public String getMarker(){return marker;}}
    static String field(Input x){return x.getText();}
    static String opaque(Input x){int[] unsupported=new int[1];return x.text;}
    public static class Out {
        public String text,other;public String getText(){return text;}public String getOther(){return other;}
        public Out(String text,String other){this.text=text;this.other=other;}
        public Out(String text){this(text,"constant");}
        public Out(Input left,Input right,int mode){this.text=field(left);this.other="constant";if(mode==1)this.other=field(right);if(mode==2)this.text=field(right);if(mode==7)this.text=opaque(left);}
    }
    public static Out root(Input left,Input right,int mode){
        if(mode==3){try{return new Out(null,right,0);}catch(NullPointerException e){return new Out(right,right,0);}}
        if(mode==4)return new Out(null,right,0);
        if(mode==5)return new Out(left.text);
        if(mode==6)return new Out(right.text,"constant");
        if(mode==9){List<Input> xs=new ArrayList<>();xs.add(left);xs.add(right);Input selected=xs.stream().filter(x->x.marker.equals(right.marker)).findFirst().orElseGet(()->left);return new Out(selected,right,0);}
        if(mode==10){List<Input> xs=new ArrayList<>();xs.add(left);xs.add(right);return new Out(xs.stream().filter(x->x.marker.equals("missing")).findFirst().orElseGet(()->left),right,0);}
        if(mode==11){List<Input> xs=new ArrayList<>();xs.add(left);xs.add(right);xs.add(left);return new Out(xs.stream().filter(x->x.marker.equals("left")).findFirst().orElseGet(()->right),right,0);}
        if(mode==12){List<Input> xs=new ArrayList<>();xs.add(left);return new Out(xs.stream().filter(x->opaque(x).equals("SAME")).findFirst().orElseGet(()->right),right,0);}
        return new Out(left,right,mode);
    }
    public static void main(String[] args)throws Exception{
        Input left=new Input("SAME","left"),right=new Input("SAME","right");ObjectMapper json=new ObjectMapper();List<Map> cases=new ArrayList<>();
        for(int i=0;i<26;i++){
            int mode=i%13;W3CTraceContext c=W3CTraceContext.server("00-44444444444444444444444444444444-"+String.format("%016x",i+1)+"-01","fixture=constructors");SpringTransportAgent.Transport.ASYNC.set(c);Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",c.fields().get("message"));
            try{Out result=root(left,right,mode);ResponseBindingHooks.verifySerialization(result,json);row.put("response",json.readValue(json.writeValueAsString(result),Map.class));row.put("status","normal");Map wire=c.fields();wire.put("uri","fixture:constructors");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}}
            catch(NullPointerException expected){row.put("status","aborted");}cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();
        }System.out.println(json.writeValueAsString(cases));
    }
}
