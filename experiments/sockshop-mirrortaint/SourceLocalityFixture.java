import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.cloud.openfeign.support.SpringDecoder;
import feign.*;
public class SourceLocalityFixture {
 public static class Result {private long code;private String message;private Object data;public Result(){}public long getCode(){return code;}public void setCode(long v){code=v;}public String getMessage(){return message;}public void setMessage(String v){message=v;}public Object getData(){return data;}public void setData(Object v){data=v;}}
 public static class Wrapper {Result result;public Wrapper(Result x){result=x;}}
 public interface API {@RequestLine("GET /fetch")Result fetch();}
 API api;public Wrapper shared;
 public Result root(int mode){Result r=api.fetch();
  if(mode==1)OpaqueLocality.touch(r);
  else if(mode==2)OpaqueLocality.wrapper(new Wrapper(r));
  else if(mode==3){OpaqueLocality.publish(r);OpaqueLocality.global();}
  else if(mode==4)r.setMessage("same");
  else if(mode==5){Object[] a=new Object[]{r};OpaqueLocality.array(a);}
  else if(mode==6){List<Object> list=new ArrayList<>();list.add(r);OpaqueLocality.list(list);}
  else if(mode==7){final Result captured=r;Runnable callback=()->captured.setMessage("same");OpaqueLocality.callback(callback);}
  else if(mode==8)OpaqueLocality.global();
  else if(mode==9){try{OpaqueLocality.fail();}catch(IllegalArgumentException x){if(x!=OpaqueLocality.failure)throw x;}}
  else if(mode==10){shared=new Wrapper(r);OpaqueLocality.receiver(this);}
  else if(mode==11)r=OpaqueLocality.result();
  else OpaqueLocality.other();
  return r;
 }
 public static class LeakyDecoder implements feign.codec.Decoder {final feign.codec.Decoder delegate;LeakyDecoder(feign.codec.Decoder d){delegate=d;}public Object decode(Response r,java.lang.reflect.Type t)throws java.io.IOException{Object result=delegate.decode(r,t);OpaqueLocality.published=(Result)result;return result;}}
 static ObjectMapper mapper(int mode){ObjectMapper m=new ObjectMapper();if(mode==12)m.findAndRegisterModules();
  if(mode==13){com.fasterxml.jackson.databind.module.SimpleModule module=new com.fasterxml.jackson.databind.module.SimpleModule();module.setDeserializerModifier(new com.fasterxml.jackson.databind.deser.BeanDeserializerModifier(){});m.registerModule(module);}
  if(mode==14)m.setAnnotationIntrospector(new com.fasterxml.jackson.databind.introspect.JacksonAnnotationIntrospector(){});return m;}
 static feign.InvocationHandlerFactory cacheFactory(boolean enabled){
  org.springframework.cache.interceptor.CacheInterceptor c=new org.springframework.cache.interceptor.CacheInterceptor();
  org.springframework.cache.interceptor.CacheableOperation.Builder b=new org.springframework.cache.interceptor.CacheableOperation.Builder();b.setCacheName("results");org.springframework.cache.interceptor.CacheableOperation op=b.build();
  c.setCacheOperationSource((method,target)->enabled?Collections.singletonList(op):Collections.emptyList());c.setCacheManager(new org.springframework.cache.concurrent.ConcurrentMapCacheManager("results"));c.afterPropertiesSet();c.afterSingletonsInstantiated();
  return new org.springframework.cloud.openfeign.FeignCachingInvocationHandlerFactory(new feign.InvocationHandlerFactory.Default(),c);
 }
 public static void main(String[] args)throws Exception{List<Map> output=new ArrayList<>();int n=0;
  for(int repeat=0;repeat<2;repeat++)for(int mode=0;mode<=16;mode++){MappingJackson2HttpMessageConverter c=new MappingJackson2HttpMessageConverter(mapper(mode));HttpMessageConverters converters=new HttpMessageConverters(false,Collections.singletonList(c));feign.codec.Decoder d=new SpringDecoder(()->converters);if(mode==8)d=new LeakyDecoder(d);
   Feign.Builder builder=Feign.builder();if(mode>=15)builder.invocationHandlerFactory(cacheFactory(mode==16));API api=builder.client((request,options)->Response.builder().status(200).reason("OK").request(request).headers(Collections.singletonMap("Content-Type",Collections.singletonList("application/json"))).body("{\"code\":200,\"message\":\"same\",\"data\":{\"token\":\"same\"}}",java.nio.charset.StandardCharsets.UTF_8).build()).decoder(d).target(API.class,"http://fixture.invalid");SourceLocalityFixture f=new SourceLocalityFixture();f.api=api;
   W3CTraceContext context=W3CTraceContext.server("00-77777777777777777777777777777777-"+String.format("%016x",++n)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(context);Result result;try{result=f.root(mode);}finally{SpringTransportAgent.Transport.ASYNC.remove();}
   Map row=new LinkedHashMap();row.put("mode",mode);row.put("repeat",repeat);row.put("message",context.message());row.put("text",result.getMessage());row.put("side_effect",OpaqueLocality.saved);output.add(row);
  }System.out.println(new ObjectMapper().writeValueAsString(output));
 }
}
class OpaqueLocality {static SourceLocalityFixture.Result published;static int saved;static final IllegalArgumentException failure=new IllegalArgumentException("original");static void other(){saved++;}static void receiver(SourceLocalityFixture f){touch(f.shared.result);}static SourceLocalityFixture.Result result(){SourceLocalityFixture.Result r=new SourceLocalityFixture.Result();r.setMessage("same");return r;}static void touch(SourceLocalityFixture.Result r){r.setMessage("same");}static void wrapper(SourceLocalityFixture.Wrapper w){touch(w.result);}static void publish(SourceLocalityFixture.Result r){published=r;}static void global(){if(published!=null)touch(published);}static void array(Object[] a){touch((SourceLocalityFixture.Result)a[0]);}static void list(List<Object> a){touch((SourceLocalityFixture.Result)a.get(0));}static void callback(Runnable r){r.run();}static void fail(){throw failure;}}
