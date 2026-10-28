import java.util.*;
import java.math.BigDecimal;
import com.fasterxml.jackson.databind.*;
public class ScalarProjectionFixture {
 public enum Plain {ALPHA,BETA;}
 public static class Input {public int number;public Plain enumeration;public Date date;public Input(){number=19;enumeration=Plain.ALPHA;date=new Date(1700000000123L);}public int getNumber(){return number;}public Plain getEnumeration(){return enumeration;}public Date getDate(){return date;}}
 public static class Out {public BigDecimal amount;public Plain enumeration;public Date date;public Out(){}public BigDecimal getAmount(){return amount;}public Plain getEnumeration(){return enumeration;}public Date getDate(){return date;}}
 public static Out root(Input left,Input right,int mode){Out r=new Out();if(mode==0)r.amount=new BigDecimal(left.getNumber());else if(mode==1)r.amount=new BigDecimal(right.getNumber());else if(mode==2)r.amount=new BigDecimal(0);else if(mode==4)r.enumeration=left.getEnumeration();else if(mode==5)r.enumeration=right.getEnumeration();else if(mode==6)r.enumeration=Plain.BETA;else if(mode==8)r.date=left.getDate();else if(mode==9)r.date=new Date(1700000000123L);else if(mode==10)r.date=new Date();return r;}
 public static void main(String[] args)throws Exception{
  String group=args[0],encoding=args.length>1?args[1]:"default";ObjectMapper json=new ObjectMapper();json.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);if(encoding.equals("timestamp"))json.enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);if(encoding.equals("enum-index"))json.enable(SerializationFeature.WRITE_ENUMS_USING_INDEX);if(encoding.equals("enum-string"))json.enable(SerializationFeature.WRITE_ENUMS_USING_TO_STRING);
  if(encoding.equals("number-string"))json.getFactory().enable(com.fasterxml.jackson.core.JsonGenerator.Feature.WRITE_NUMBERS_AS_STRINGS);
  if(encoding.equals("custom-number")){com.fasterxml.jackson.databind.module.SimpleModule module=new com.fasterxml.jackson.databind.module.SimpleModule();module.addSerializer(BigDecimal.class,new JsonSerializer<BigDecimal>(){public void serialize(BigDecimal value,com.fasterxml.jackson.core.JsonGenerator g,SerializerProvider p)throws java.io.IOException{g.writeNumber(value);}});json.registerModule(module);}
  List<Map> cases=new ArrayList<>();int serial=0;int[] modes=group.equals("amount")?new int[]{0,1,2,3}:group.equals("enumeration")?new int[]{4,5,6,7}:new int[]{8,9,10,11};
  for(int pass=0;pass<2;pass++)for(int mode:modes){Input left=new Input(),right=new Input();if(pass==1){left.number=-19;right.number=-19;}W3CTraceContext c=W3CTraceContext.server("00-22222222222222222222222222222222-"+String.format("%016x",++serial)+"-01","fixture=scalar");SpringTransportAgent.Transport.ASYNC.set(c);Out out=root(left,right,mode);boolean refused=false;
   if(PlannedServiceAgent.plan!=null){try{ResponseBindingHooks.verifySerialization(out,json);}catch(IllegalStateException expected){if(encoding.equals("default")||encoding.equals("timestamp"))throw expected;refused=true;}}
   Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",c.message());row.put("response",json.readValue(json.writeValueAsString(out),Map.class));row.put("refused",refused);cases.add(row);
   if(PlannedServiceAgent.plan!=null&&!refused){Map wire=c.fields();wire.put("uri","fixture:scalar");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(out));PlannedServiceAgent.Recorder.emit("http-json",wire);}SpringTransportAgent.Transport.ASYNC.remove();
  }System.out.println(json.writeValueAsString(cases));
 }
}
