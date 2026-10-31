import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public class LongValueFixture {
 public static class Result {public Long first,second;public long unboxed;public Long getFirst(){return first;}public Long getSecond(){return second;}public long getUnboxed(){return unboxed;}}
 public Result root(long left,long right){Long a=Long.valueOf(left),b=Long.valueOf(right);Result r=new Result();r.first=a;r.second=b;r.unboxed=b.longValue();return r;}
 public static void main(String[] args)throws Exception{List<Map> output=new ArrayList<>();long[][] cases={{1,1},{-1,-1},{0,0},{127,127},{128,128},{Long.MIN_VALUE,Long.MAX_VALUE}};int n=0;for(long[] values:cases){W3CTraceContext context=W3CTraceContext.server("00-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee-"+String.format("%016x",++n)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(context);Result r;try{r=new LongValueFixture().root(values[0],values[1]);}finally{SpringTransportAgent.Transport.ASYNC.remove();}Map row=new LinkedHashMap();row.put("message",context.message());row.put("left",r.first);row.put("right",r.second);row.put("unboxed",r.unboxed);row.put("same_box",r.first==r.second);output.add(row);}System.out.println(new ObjectMapper().writeValueAsString(output));}
}
