import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.cloud.openfeign.support.SpringDecoder;
import feign.*;
public class SourceLocalityFixture {
 public static class Result {private long code;public String message;private Object data;public Result(){}public long getCode(){return code;}public void setCode(long v){code=v;}public String getMessage(){return message;}public void setMessage(String v){message=v;}public Object getData(){return data;}public void setData(Object v){data=v;}}
 public static class Wrapper {Result result;public Wrapper(Result x){result=x;}}
 public interface API {@RequestLine("GET /fetch")Result fetch();}
 API api;public Wrapper shared;
 public Result root(int mode){Result r;try{r=api.fetch();}catch(IllegalArgumentException error){if(error!=OpaqueLocality.failure)throw error;r=new Result();r.setMessage("same");return r;}
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
  else if(mode==19)OpaqueLocality.globalDirect();
  else if(mode==24||mode==25){List<Result> local=new ArrayList<>();local.add(r);java.util.stream.Collector<Result,?,List<Result>> collector=java.util.stream.Collectors.toList();if(mode==24)OpaqueLocality.replaceCollector(collector);local.stream().collect(collector);OpaqueLocality.other();}
  else OpaqueLocality.other();
  return r;
 }
 public static class LeakyDecoder implements feign.codec.Decoder {final feign.codec.Decoder delegate;LeakyDecoder(feign.codec.Decoder d){delegate=d;}public Object decode(Response r,java.lang.reflect.Type t)throws java.io.IOException{Object result=delegate.decode(r,t);OpaqueLocality.published=(Result)result;return result;}}
 static ObjectMapper mapper(int mode){ObjectMapper m=new ObjectMapper();if(mode==12)m.findAndRegisterModules();
  if(mode==13){com.fasterxml.jackson.databind.module.SimpleModule module=new com.fasterxml.jackson.databind.module.SimpleModule();module.setDeserializerModifier(new com.fasterxml.jackson.databind.deser.BeanDeserializerModifier(){});m.registerModule(module);}
  if(mode==22)m.addMixIn(java.time.LocalDate.class,EmptyMixin.class);if(mode==23)m.addMixIn(Result.class,EmptyMixin.class);
  if(mode==20||mode==21)m.setHandlerInstantiator(new org.springframework.http.converter.json.SpringHandlerInstantiator(new org.springframework.beans.factory.support.DefaultListableBeanFactory()));
  if(mode==19){com.fasterxml.jackson.databind.module.SimpleModule module=new com.fasterxml.jackson.databind.module.SimpleModule();module.addDeserializer(Number.class,new NumberLeak());m.registerModule(module);}
  if(mode==14)m.setAnnotationIntrospector(new com.fasterxml.jackson.databind.introspect.JacksonAnnotationIntrospector(){});return m;}
 public static class EmptyMixin {}
 public static class NoPrefetchConverter extends MappingJackson2HttpMessageConverter{NoPrefetchConverter(ObjectMapper m){super(m);}public boolean canRead(java.lang.reflect.Type t,Class<?> c,org.springframework.http.MediaType m){return true;}public boolean canRead(Class<?> c,org.springframework.http.MediaType m){return true;}}
 public static class ForcingHandlerConverter extends NoPrefetchConverter{ForcingHandlerConverter(ObjectMapper m){super(m);}public boolean canRead(java.lang.reflect.Type t,Class<?> c,org.springframework.http.MediaType media){ObjectMapper m=getObjectMapper();m.getDeserializationConfig().getHandlerInstantiator().deserializerInstance(m.getDeserializationConfig(),null,com.fasterxml.jackson.databind.deser.std.StringDeserializer.class);return true;}}
 @com.fasterxml.jackson.databind.annotation.JacksonStdImpl
 public static class NumberLeak extends com.fasterxml.jackson.databind.JsonDeserializer<Number> implements com.fasterxml.jackson.databind.deser.ResolvableDeserializer{
  public void resolve(com.fasterxml.jackson.databind.DeserializationContext context){OpaqueLocality.context=context;}
  public Number deserialize(com.fasterxml.jackson.core.JsonParser p,com.fasterxml.jackson.databind.DeserializationContext c)throws java.io.IOException{return p.getNumberValue();}
 }
 public static class LeakingStream extends java.io.ByteArrayInputStream{LeakingStream(String s){super(s.getBytes(java.nio.charset.StandardCharsets.UTF_8));}public synchronized int read(byte[] b,int off,int len){if(OpaqueLocality.context!=null&&OpaqueLocality.context.getParser()!=null){Object current=OpaqueLocality.context.getParser().getCurrentValue();if(current instanceof Result)OpaqueLocality.published=(Result)current;}return super.read(b,off,Math.min(len,1));}}
 static Response response(feign.Request request,int mode){Response.Builder builder=Response.builder().status(200).reason("OK").request(request).headers(Collections.singletonMap("Content-Type",Collections.singletonList("application/json")));String body="{\"code\":200,\"message\":\"same\",\"data\":{\"token\":\"same\"}}";return mode==19?builder.body(new LeakingStream(body),null).build():builder.body(body,java.nio.charset.StandardCharsets.UTF_8).build();}
 public static class CountingEmpty extends AbstractCollection<org.springframework.cache.interceptor.CacheOperation>{public int size(){return 0;}public Iterator<org.springframework.cache.interceptor.CacheOperation> iterator(){return Collections.emptyIterator();}public boolean isEmpty(){OpaqueLocality.cacheChecks++;return true;}}
 static feign.InvocationHandlerFactory cacheFactory(int mode){
  org.springframework.cache.interceptor.CacheInterceptor c=new org.springframework.cache.interceptor.CacheInterceptor();
  org.springframework.cache.interceptor.CacheableOperation.Builder b=new org.springframework.cache.interceptor.CacheableOperation.Builder();b.setCacheName("results");org.springframework.cache.interceptor.CacheableOperation op=b.build();
  c.setCacheOperationSource((method,target)->mode==16?Collections.singletonList(op):mode==17?new CountingEmpty():Collections.emptyList());c.setCacheManager(new org.springframework.cache.concurrent.ConcurrentMapCacheManager("results"));c.afterPropertiesSet();c.afterSingletonsInstantiated();
  return new org.springframework.cloud.openfeign.FeignCachingInvocationHandlerFactory(new feign.InvocationHandlerFactory.Default(),c);
 }
 public static void main(String[] args)throws Exception{List<Map> output=new ArrayList<>();int n=0;
  for(int repeat=0;repeat<2;repeat++)for(int mode=0;mode<=25;mode++){final int fixtureMode=mode;MappingJackson2HttpMessageConverter c=mode==21?new ForcingHandlerConverter(mapper(mode)):mode==19?new NoPrefetchConverter(mapper(mode)):new MappingJackson2HttpMessageConverter(mapper(mode));HttpMessageConverters converters=new HttpMessageConverters(false,Collections.singletonList(c));feign.codec.Decoder d=new SpringDecoder(()->converters);if(mode==8)d=new LeakyDecoder(d);
   Feign.Builder builder=Feign.builder();if(mode>=15)builder.invocationHandlerFactory(cacheFactory(mode));API api=builder.client((request,options)->{if(fixtureMode==18)throw OpaqueLocality.failure;return response(request,fixtureMode);}).decoder(d).target(API.class,"http://fixture.invalid");SourceLocalityFixture f=new SourceLocalityFixture();f.api=api;if(fixtureMode==19)OpaqueLocality.published=null;
   W3CTraceContext context=W3CTraceContext.server("00-77777777777777777777777777777777-"+String.format("%016x",++n)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(context);Result result;try{result=f.root(mode);}finally{SpringTransportAgent.Transport.ASYNC.remove();}
   if(mode==19&&OpaqueLocality.published!=result)throw new IllegalStateException("Wrong published object");Map row=new LinkedHashMap();row.put("mode",mode);row.put("repeat",repeat);row.put("message",context.message());row.put("text",result.getMessage());row.put("side_effect",OpaqueLocality.saved);row.put("cache_checks",OpaqueLocality.cacheChecks);output.add(row);
  }System.out.println(new ObjectMapper().writeValueAsString(output));
 }
}
class OpaqueLocality {static SourceLocalityFixture.Result published;static int saved,cacheChecks;static com.fasterxml.jackson.databind.DeserializationContext context;static final IllegalArgumentException failure=new IllegalArgumentException("original");static void replaceCollector(Object collector){try{java.lang.reflect.Field f=collector.getClass().getDeclaredField("accumulator");f.setAccessible(true);f.set(collector,(java.util.function.BiConsumer<List<SourceLocalityFixture.Result>,SourceLocalityFixture.Result>)(list,row)->{row.message=row.message;saved++;list.add(row);});}catch(Exception error){throw new IllegalStateException(error);}}static void other(){saved++;}static void receiver(SourceLocalityFixture f){touch(f.shared.result);}static SourceLocalityFixture.Result result(){SourceLocalityFixture.Result r=new SourceLocalityFixture.Result();r.setMessage("same");return r;}static void touch(SourceLocalityFixture.Result r){r.setMessage("same");}static void wrapper(SourceLocalityFixture.Wrapper w){touch(w.result);}static void publish(SourceLocalityFixture.Result r){published=r;}static void globalDirect(){if(published==null)throw new IllegalStateException("Context escape absent");published.message="same";}static void global(){if(published!=null)touch(published);}static void array(Object[] a){touch((SourceLocalityFixture.Result)a[0]);}static void list(List<Object> a){touch((SourceLocalityFixture.Result)a.get(0));}static void callback(Runnable r){r.run();}static void fail(){throw failure;}}
