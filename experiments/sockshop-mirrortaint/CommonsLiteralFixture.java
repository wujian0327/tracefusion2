import java.util.*;
import org.apache.commons.lang3.StringUtils;
import org.apache.commons.lang3.ArrayUtils;
import com.fasterxml.jackson.databind.ObjectMapper;
public class CommonsLiteralFixture {
 public static class Init{static boolean alias;}
 public static class Alias extends StringUtils{static{Init.alias=true;}}
 public static class Source{public String text;public Source(String x){text=x;}}
 public static class Store{public Source read(int mode){String[]texts={"A,SAME,B","A,,B,",",SAME,,SAME,","","SAME"," A, SAME","SAME","SAME::B"};return new Source(texts[mode]);}}
 public static class Out{public boolean flag;public Out(boolean b){flag=b;}public boolean isFlag(){return flag;}}
 public static class Evil{static int calls;public boolean equals(Object x){calls++;return true;}}
 public Out root(Store s,int mode){Source input=s.read(mode);if(mode==6)return new Out(ArrayUtils.contains(new Object[]{new Evil()},new Evil()));String[]parts=Alias.split(input.text,mode==7?"::":",");return new Out(ArrayUtils.contains(parts,"SAME"));}
 public static void main(String[]args)throws Exception{boolean observe=Boolean.getBoolean("fixture.observe"),late=Boolean.getBoolean("fixture.late");ObjectMapper json=new ObjectMapper();if(!late){StringUtils.split("a,b",",");ArrayUtils.contains(new String[]{"a"},"a");}List<Map> rows=new ArrayList<>();for(int i=0;i<8;i++){W3CTraceContext c=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(c);Out value=new CommonsLiteralFixture().root(new Store(),i);Map row=new LinkedHashMap();row.put("case",i);row.put("response",value.flag);row.put("equals_calls",Evil.calls);row.put("alias_initialized",Init.alias);if(observe){ResponseBindingHooks.verifySerialization(value,json);row.put("message",c.message());SpringTransportAgent.Transport.ASYNC.remove();}rows.add(row);}System.out.println(json.writeValueAsString(rows));}
}
