import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public class LongRenderFixture {
 public static class Source{public Long value;public Source(long n){value=n;}}
 public static class Store{public Source read(long n){return new Source(n);}}
 public static class Out{public String value;public Out(String n){value=n;}public String getValue(){return value;}}
 public Out root(Store store,long n,int opaque){Source s=store.read(n);if(opaque!=0)System.gc();return new Out(new StringBuilder().append((Object)s.value).toString());}
 public static void main(String[]args)throws Exception{long[]values={Long.MIN_VALUE,-2147483649L,-2147483648L,-1,0,2147483647L,2147483648L,Long.MAX_VALUE,0,0};boolean observe=Boolean.getBoolean("fixture.observe");ObjectMapper json=new ObjectMapper();List<Map> result=new ArrayList<>();for(int i=0;i<values.length;i++){W3CTraceContext c=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(c);Out out=new LongRenderFixture().root(new Store(),values[i],i==9?1:0);Map row=new LinkedHashMap();row.put("case",i);row.put("input",values[i]);row.put("response",out.value);if(observe){ResponseBindingHooks.verifySerialization(out,json);row.put("message",c.message());SpringTransportAgent.Transport.ASYNC.remove();}result.add(row);}System.out.println(json.writeValueAsString(result));}
}
