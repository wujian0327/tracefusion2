import java.util.*;
import com.alibaba.fastjson2.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public class JsonListScalarFixture {
 public static class Store {public JSONArray read(String value){JSONArray a=new JSONArray();a.add(value);return a;}}
 public static class Out {public String text;public Out(String value){text=value;}public String getText(){return text;}}
 public static Class<String> type(){return String.class;}
 public Out root(Store store,String input){Class<String> type=type();List<String> values=store.read(input).toList(type,new JSONReader.Feature[0]);return new Out(values.get(0));}
 public static void main(String[]args)throws Exception{new JSONArray().toList(String.class);boolean observe=Boolean.getBoolean("fixture.observe");ObjectMapper mapper=new ObjectMapper();List<Map> output=new ArrayList<>();for(String input:new String[]{"SAME","SAME",null}){W3CTraceContext c=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(c);Out out=new JsonListScalarFixture().root(new Store(),input);Map r=new LinkedHashMap();r.put("text",out.text);if(observe){ResponseBindingHooks.verifySerialization(out,mapper);r.put("message",c.message());SpringTransportAgent.Transport.ASYNC.remove();}output.add(r);}System.out.println(mapper.writeValueAsString(output));}
}
