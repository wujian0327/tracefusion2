import java.util.*;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.ObjectMapper;
public class PageValueFixture {
 public static class Row {public String text;public String getText(){return text;}}
 public static class Result {public List<Row> data;public Long count;public List<Row> getData(){return data;}public Long getCount(){return count;}}
 public static class Store {public static List<Row> read(Page<Row> page){page.setTotal(1);Row row=new Row();row.text="same";List<Row> rows=new ArrayList<>();rows.add(row);return rows;}}
 public Result root(int size){Page<Row> page=new Page<>(1L,(long)size);List<Row> data=Store.read(page);page.setRecords(data);Result result=new Result();result.data=data;result.count=Long.valueOf(page.getTotal());return result;}
 public static void main(String[] args)throws Exception{List<Map> values=new ArrayList<>();int id=0;for(int size:new int[]{1,Integer.MAX_VALUE}){W3CTraceContext c=W3CTraceContext.server("00-99999999999999999999999999999999-"+String.format("%016x",++id)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(c);Result result;try{result=new PageValueFixture().root(size);}finally{SpringTransportAgent.Transport.ASYNC.remove();}Map value=new LinkedHashMap();value.put("message",c.message());value.put("text",result.data.get(0).text);value.put("count",result.count);values.add(value);}System.out.println(new ObjectMapper().writeValueAsString(values));}
}
