import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.cloud.openfeign.support.SpringDecoder;
import feign.*;

public class BodyObservationFixture {
 public static class Result {private long code;private String message;private Object data;public Result(){}public long getCode(){return code;}public void setCode(long x){code=x;}public String getMessage(){return message;}public void setMessage(String x){message=x;}public Object getData(){return data;}public void setData(Object x){data=x;}}
 public static class Wrapper {Result value;public Wrapper(Result x){value=x;}}
 public interface API {@RequestLine("GET /fetch")Result fetch();}
 static final IllegalArgumentException ORIGINAL=new IllegalArgumentException("business-original");
 API api;int seed=2,count;
 public Result root(int mode){Result r=api.fetch();
  if(mode==1)r.setMessage("same");
  else if(mode==2){Wrapper wrapper=new Wrapper(r);}
  else if(mode==3)OpaqueBodyObservation.publish(r);
  else if(mode==4){final Result captured=r;Runnable callback=()->captured.setMessage("same");}
  try{audit(mode);}catch(IllegalArgumentException error){if(error!=ORIGINAL)throw error;count=count+1;}finally{count=count+1;}
  return r;
 }
 private void audit(int mode){int x=seed;count=count+x;if(mode==6)throw ORIGINAL;OpaqueBodyObservation.unrelated();}
 public static class LeakingDecoder implements feign.codec.Decoder {final feign.codec.Decoder d;LeakingDecoder(feign.codec.Decoder value){d=value;}public Object decode(Response r,java.lang.reflect.Type type)throws java.io.IOException{Object value=d.decode(r,type);OpaqueBodyObservation.leaked=(Result)value;return value;}}
 public static void main(String[] args)throws Exception{List<Map> output=new ArrayList<>();for(int mode=0;mode<=7;mode++){
  MappingJackson2HttpMessageConverter converter=new MappingJackson2HttpMessageConverter(new ObjectMapper());HttpMessageConverters converters=new HttpMessageConverters(false,Collections.singletonList(converter));feign.codec.Decoder decoder=new SpringDecoder(()->converters);if(mode==7)decoder=new LeakingDecoder(decoder);
  API api=Feign.builder().client((request,options)->Response.builder().status(200).reason("OK").request(request).headers(Collections.singletonMap("Content-Type",Collections.singletonList("application/json"))).body("{\"code\":200,\"message\":\"same\",\"data\":{\"item\":\"same\"}}",java.nio.charset.StandardCharsets.UTF_8).build()).decoder(decoder).target(API.class,"http://fixture.invalid");
  BodyObservationFixture f=new BodyObservationFixture();f.api=api;OpaqueBodyObservation.leaked=null;W3CTraceContext context=W3CTraceContext.server("00-dddddddddddddddddddddddddddddddd-"+String.format("%016x",mode+1)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(context);Result result;try{result=f.root(mode);}finally{SpringTransportAgent.Transport.ASYNC.remove();}
  if(mode==7&&OpaqueBodyObservation.leaked!=result)throw new IllegalStateException("Actual same-object leak missing");
  for(String key:new String[]{"frames","scopes","calls","body_roots","body_modes"})if(((Number)MonitorSafety.inspect().get(key)).intValue()!=0)throw new IllegalStateException("State retained: "+key);
  Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",context.message());row.put("text",result.message);row.put("count",f.count);row.put("other",OpaqueBodyObservation.count);output.add(row);
 }System.out.println(new ObjectMapper().writeValueAsString(output));}
}
// Excluded from the model. The opaque effect is real, including same-value writes.
class OpaqueBodyObservation {static BodyObservationFixture.Result leaked;static int count;static void publish(BodyObservationFixture.Result r){leaked=r;}static void unrelated(){count++;if(leaked!=null)leaked.setMessage("same");}}
