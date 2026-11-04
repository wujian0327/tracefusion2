import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

public class MapConstructorEffectsFixture {
 public static class Box{public String text;public Box(String s){text=s;}public String getText(){return text;}}
 public static class Store{public Box read(){return new Box(new String("same"));}}
 public static class Pure{static boolean yes(Object v){return v!=null;}}
 public static class Wrap extends HashMap<String,Object>{public Wrap(int n,String msg,Object data){super();super.put("code",Integer.valueOf(n));super.put("message",msg);if(Pure.yes(data))super.put("data",data);}}
 public static class Mutating extends Wrap{public Mutating(Box data){super(200,"same",data);data.text=new String("same");}}
 static Object published;
 static void publish(Wrap w){published=w;((Box)w.get("data")).text=new String("same");}
 public static class Parent{public Wrap wrap(Box b){return new Wrap(200,"same",b);}}
 public static class Child extends Parent{}
 public Wrap root(Store s,int mode){Box b=s.read();if(mode==1)return new Mutating(b);if(mode==2){Box copy=new Box(b.text);Wrap w=new Wrap(200,"same",copy);publish(w);return w;}if(mode==3)return new Child().wrap(b);return new Wrap(200,"same",b);}
 public static void main(String[] args)throws Exception{if(!Boolean.getBoolean("fixture.late"))Pure.yes(null);ObjectMapper json=new ObjectMapper();List<Map> results=new ArrayList<>();MapConstructorEffectsFixture fixture=new MapConstructorEffectsFixture();boolean observe=Boolean.getBoolean("fixture.observe");for(int mode=0;mode<4;mode++){
  W3CTraceContext c=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(c);HashMap result=fixture.root(new Store(),mode);Map row=new LinkedHashMap();row.put("mode",mode);row.put("response",json.readValue(json.writeValueAsString(result),Map.class));
  if(observe){ResponseBindingHooks.verifySerialization(result,json);Map wire=c.fields();wire.put("uri",null);wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result,true));PlannedServiceAgent.Recorder.emit("http-json",wire);SpringTransportAgent.Transport.ASYNC.remove();row.put("message",c.message());}results.add(row);
 }System.out.println(json.writeValueAsString(results));}
}
