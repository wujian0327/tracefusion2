import java.util.*;
import com.alibaba.fastjson2.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public class JsonListCopyFixture {
 public static class Box {public String text;public Box(){}public Box(String s){text=s;}public String getText(){return text;}}
 static Box published;static int callbacks;
 static void setup(int kind,Box box){try{published=box;if(kind==7){java.lang.reflect.Field f=JSONFactory.getDefaultObjectReaderProvider().getClass().getDeclaredField("cache");f.setAccessible(true);((Map)f.get(JSONFactory.getDefaultObjectReaderProvider())).remove(Box.class);}}catch(Exception e){throw new IllegalStateException(e);}}
 public static class Store {
  public JSONArray read(int kind){JSONArray a=new JSONArray();a.add(kind==2?null:new Box("SAME"));a.add(new Box("SAME"));if(kind==3)a.clear();if(kind==7)setup(kind,(Box)a.get(0));if(kind==4){JSONObject x=new JSONObject();x.put("text","SAME");a.set(0,x);}return a;}
 }
 public static class Out {public String text;public Out(String s){text=s;}public String getText(){return text;}}
 public Out root(Store store,int kind){JSONArray raw=store.read(kind);List<Box> list=raw.toList(Box.class,kind==5?new JSONReader.Feature[]{JSONReader.Feature.FieldBased}:new JSONReader.Feature[0]);Box box=((Collection<Box>)list).isEmpty()?null:list.get(kind==1?1:0);if(kind==6&&box!=null)box.text="SAME";return new Out(box==null?null:box.text);}
 public static void main(String[]args)throws Exception{boolean observe=Boolean.getBoolean("fixture.observe");new JSONArray().toList(Box.class);ObjectMapper mapper=new ObjectMapper();List<Map> output=new ArrayList<>();for(int kind=0;kind<8;kind++){W3CTraceContext ctx=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(ctx);Out out=new JsonListCopyFixture().root(new Store(),kind);Map row=new LinkedHashMap();row.put("callbacks",callbacks);row.put("case",kind);row.put("text",out.text);if(observe){ResponseBindingHooks.verifySerialization(out,mapper);row.put("message",ctx.message());SpringTransportAgent.Transport.ASYNC.remove();}output.add(row);}System.out.println(mapper.writeValueAsString(output));}
}
