import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.cloud.openfeign.support.SpringDecoder;
import feign.*;

public class FutureStateObservationFixture {
 public static class Result {private long code;private String message;private Object data;private String spare;public Result(){}public String getSpare(){return spare;}public void setSpare(String x){spare=x;}public long getCode(){return code;}public void setCode(long x){code=x;}public String getMessage(){return message;}public void setMessage(String x){message=x;}public Object getData(){return data;}public void setData(Object x){data=x;}}
 public static class Wrapper {Result value;public Wrapper(Result x){value=x;}}
 public interface API {@RequestLine("GET /fetch")Result fetch();}
 static final IllegalArgumentException ORIGINAL=new IllegalArgumentException("business-original");
 API api;int seed=2,count;String later="same";List<String> futureValues;
 public Result root(int mode){Result r=api.fetch();audit(mode);r.setMessage(later);return r;}
 public Result containerFuture(int mode){Result r=api.fetch();containerAudit();r.setMessage(futureValues.get(0));return r;}
 private void containerAudit(){futureValues=new ArrayList<String>();futureValues.add("same");}
 public Result forward(int mode){Result r=api.fetch();audit(mode);return r;}
 public Result guarded(int mode){Result r=api.fetch();
  if(mode==1)r.setMessage("same");
  else if(mode==2){Wrapper wrapper=new Wrapper(r);}
  else if(mode==3)OpaqueFutureStateObservation.publish(r);
  else if(mode==4){final Result captured=r;Runnable callback=()->captured.setMessage("same");}
  opaqueAudit(mode);return r;
 }
 private void opaqueAudit(int mode){int x=seed;count=count+x;OpaqueFutureStateObservation.unrelated();}
 private void audit(int mode){later="same";count=count+1;}
 public static class LeakingDecoder implements feign.codec.Decoder {final feign.codec.Decoder d;LeakingDecoder(feign.codec.Decoder value){d=value;}public Object decode(Response r,java.lang.reflect.Type type)throws java.io.IOException{Object value=d.decode(r,type);OpaqueFutureStateObservation.leaked=(Result)value;return value;}}
 public static void main(String[] args)throws Exception{List<Map> output=new ArrayList<>();for(int mode=0;mode<=(Boolean.getBoolean("fixture.guarded")?7:1);mode++){
  MappingJackson2HttpMessageConverter converter=new MappingJackson2HttpMessageConverter(new ObjectMapper());HttpMessageConverters converters=new HttpMessageConverters(false,Collections.singletonList(converter));feign.codec.Decoder decoder=new SpringDecoder(()->converters);if(mode==7)decoder=new LeakingDecoder(decoder);
  API api=Feign.builder().client((request,options)->Response.builder().status(200).reason("OK").request(request).headers(Collections.singletonMap("Content-Type",Collections.singletonList("application/json"))).body("{\"code\":200,\"message\":\"same\",\"data\":{\"item\":\"same\"},\"spare\":\"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\"}",java.nio.charset.StandardCharsets.UTF_8).build()).decoder(decoder).target(API.class,"http://fixture.invalid");
  FutureStateObservationFixture f=new FutureStateObservationFixture();f.api=api;OpaqueFutureStateObservation.leaked=null;W3CTraceContext context=W3CTraceContext.server("00-dddddddddddddddddddddddddddddddd-"+String.format("%016x",mode+1)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(context);Result result;try{result=Boolean.getBoolean("fixture.containerFuture")?f.containerFuture(mode):Boolean.getBoolean("fixture.guarded")?f.guarded(mode):Boolean.getBoolean("fixture.forward")?f.forward(mode):f.root(mode);}finally{SpringTransportAgent.Transport.ASYNC.remove();}
  if(mode==7&&OpaqueFutureStateObservation.leaked!=result)throw new IllegalStateException("Actual same-object leak missing");
  for(String key:new String[]{"frames","scopes","calls","body_roots","body_modes"})if(((Number)MonitorSafety.inspect().get(key)).intValue()!=0)throw new IllegalStateException("State retained: "+key);
  Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",context.message());row.put("text",result.message);row.put("count",f.count);row.put("other",OpaqueFutureStateObservation.count);output.add(row);
 }System.out.println(new ObjectMapper().writeValueAsString(output));}
}
// Excluded from the model. The opaque effect is real, including same-value writes.
class OpaqueFutureStateObservation {static FutureStateObservationFixture.Result leaked;static int count;static void publish(FutureStateObservationFixture.Result r){leaked=r;}static void unrelated(){count++;if(leaked!=null)leaked.setMessage("same");}}
