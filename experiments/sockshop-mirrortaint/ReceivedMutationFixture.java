import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public class ReceivedMutationFixture {
 public static class Input {public List<String> items;public Input(List<String> x){items=x;}public List<String> getItems(){return items;}}
 public static class Out {public String text;public Out(String x){text=x;}public String getText(){return text;}}
 public static Out root(Input x,int mode){
  if(mode==0){List<String> local=new ArrayList<>();local.add(x.getItems().get(0));return new Out(local.get(0));}
  if(mode==1){x.getItems().add(x.getItems().get(0));return new Out(x.getItems().get(0));}
  x.getItems().add("SAME");return new Out(x.getItems().get(1));
 }
 public static void main(String[] args)throws Exception{
  ObjectMapper mapper=new ObjectMapper();List<Map> cases=new ArrayList<>();
  for(int i=0;i<6;i++){
   Input x=new Input(new ArrayList<String>(Arrays.asList(new String("SAME"))));int mode=i%3;
   W3CTraceContext ctx=W3CTraceContext.server("00-44444444444444444444444444444444-"+String.format("%016x",i+1)+"-01","fixture=mutation");SpringTransportAgent.Transport.ASYNC.set(ctx);
   Out result=root(x,mode);if(x.items.size()!=(mode==0?1:2))throw new AssertionError("Business mutation blocked");ResponseBindingHooks.verifySerialization(result,mapper);Map wire=ctx.fields();wire.put("uri","fixture:mutation");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}
   Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",ctx.fields().get("message"));row.put("size",x.items.size());row.put("text",result.text);cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();
  }System.out.println(mapper.writeValueAsString(cases));
 }
}
