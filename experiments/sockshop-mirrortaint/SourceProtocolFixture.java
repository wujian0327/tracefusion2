import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
/** Nested opaque callers, source failure, then same-thread recovery. */
public class SourceProtocolFixture {
 public static class Result {public long value;public long getValue(){return value;}}
 public static class Box {public long amount=7;public long getAmount(){return amount;}}
 public static class Source {static final IllegalArgumentException ERROR=new IllegalArgumentException("original");public static Box read(int fail){if(fail!=0)throw ERROR;return new Box();}}
 public static class Opaque {public static Box outer(int n){float unsupported=(float)n;Source.read(0);return inner(n);}public static Box inner(int n){float unsupported=(float)n;return Source.read(n);}}
 public Result root(int n){Result result=new Result();result.value=Opaque.outer(n).amount;return result;}
 public static void main(String[] args)throws Exception{List<Map> results=new ArrayList<>();int id=0;for(int n:new int[]{0,1,0}){W3CTraceContext c=W3CTraceContext.server("00-88888888888888888888888888888888-"+String.format("%016x",++id)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(c);Map row=new LinkedHashMap();row.put("message",c.message());try{row.put("value",new SourceProtocolFixture().root(n).value);}catch(IllegalArgumentException e){if(e!=Source.ERROR)throw new AssertionError("Exception replaced");row.put("original_exception",true);}finally{SpringTransportAgent.Transport.ASYNC.remove();}results.add(row);}System.out.println(new ObjectMapper().writeValueAsString(results));}
}
