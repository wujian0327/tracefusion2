import java.util.*;
import java.util.stream.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public class SequenceCallbackFixture {
 public static class Row {public String text,other;public Row(String s){text=s;}public String getText(){return text;}public String getOther(){return other;}public void setOther(String s){other=s;}}
 public static class Result {public List<Row> rows;public List<Row> getRows(){return rows;}}
 public static class Store {public static List<Row> read(){List<Row> rows=new ArrayList<>();rows.add(new Row("same"));rows.add(new Row("same"));return rows;}}
 public static class Service {
  static final Object initialized=new Object();static final IllegalArgumentException ORIGINAL=new IllegalArgumentException("sequence-original");
  public Result run(int mode){List<Row> rows=Store.read();List<String> names=rows.stream().map(Row::getText).collect(Collectors.toList());rows.forEach(row->{if(mode==3)throw ORIGINAL;row.setOther(names.get(0));});List<Row> selected=rows.stream().filter(row->row.getText()!=null).collect(Collectors.toList());Result result=new Result();result.rows=selected;return result;}
 }
 public Service service=new Service();
 public Result root(int mode){return service.run(mode);}
 public static void main(String[] args)throws Exception{List<Map> out=new ArrayList<>();SequenceCallbackFixture f=new SequenceCallbackFixture();int number=0;for(int i:new int[]{1,3,1}){W3CTraceContext c=W3CTraceContext.server("00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-"+String.format("%016x",++number)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(c);Result r=null;boolean exceptional=false;try{r=f.root(i);}catch(IllegalArgumentException error){if(error!=Service.ORIGINAL)throw error;exceptional=true;}finally{SpringTransportAgent.Transport.ASYNC.remove();}for(String key:new String[]{"frames","calls","scopes","sequence_pipes","sequence_collectors"})if(((Number)MonitorSafety.inspect().get(key)).intValue()!=0)throw new IllegalStateException("Sequence state retained: "+key);Map x=new LinkedHashMap();x.put("message",c.message());x.put("exceptional",exceptional);if(!exceptional){x.put("values",Arrays.asList(r.rows.get(0).text,r.rows.get(1).text));x.put("other",r.rows.get(0).other);}out.add(x);}System.out.println(new ObjectMapper().writeValueAsString(out));}
}
