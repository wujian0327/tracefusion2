import java.util.*;
import com.alibaba.fastjson2.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public class JsonTreeObservationFixture {
 public static class BadArray extends JSONArray {static int calls;public Object get(int i){calls++;return super.get(i);}public Iterator<Object> iterator(){calls++;return super.iterator();}}
 public static class BadObject extends JSONObject {static int calls;public Object get(Object key){calls++;return super.get(key);}}
 public static class Store {
  static Object last;static Object[] members;
  public Object read(int kind){JSONObject a=new JSONObject();a.put("v","SAME");a.put("n",null);JSONObject b=new JSONObject();b.put("v","SAME");b.put("n",null);members=new Object[]{a,b};JSONArray list=kind==4?new BadArray():new JSONArray();list.add(a);list.add(b);if(kind==1)list.clear();if(kind==2)last=null;else if(kind==3)last=a;else if(kind==5){JSONObject bad=new BadObject();bad.put("v","SAME");last=bad;}else last=list;return last;}
 }
 public static class Out{public String text;public Out(String x){text=x;}public String getText(){return text;}}
 public Out root(Store store,int kind){Object value=store.read(kind);Object[] box=new Object[]{value};return new Out(box[0]==null?"EMPTY":"OK");}
 public static void main(String[]args)throws Exception{boolean observe=Boolean.getBoolean("fixture.observe");ObjectMapper json=new ObjectMapper();List<Map> results=new ArrayList<>();int first=args.length==0?0:Integer.parseInt(args[0]),last=args.length==0?4:first+1;
  for(int kind=first;kind<last;kind++){W3CTraceContext c=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(c);Out out=new JsonTreeObservationFixture().root(new Store(),kind);Map row=new LinkedHashMap();row.put("case",kind);row.put("response",out.text);row.put("array_overrides",BadArray.calls);row.put("map_overrides",BadObject.calls);if(observe){ResponseBindingHooks.verifySerialization(out,json);row.put("message",c.message());List ids=new ArrayList();for(Object m:Store.members)ids.add(PlannedServiceAgent.Recorder.id(m));row.put("members",ids);SpringTransportAgent.Transport.ASYNC.remove();}results.add(row);}System.out.println(json.writeValueAsString(results));}
}
