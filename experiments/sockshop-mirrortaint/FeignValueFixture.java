import java.util.*;
import java.io.*;
import java.net.*;
import java.lang.reflect.Type;
import com.sun.net.httpserver.HttpServer;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.core.JsonGenerator;
import feign.*;
import feign.hystrix.HystrixFeign;
import feign.codec.Encoder;
import org.springframework.cloud.openfeign.support.SpringEncoder;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
public class FeignValueFixture {
 public static class Input {private String text,other;public Input(String t,String o){text=t;other=o;}public String getText(){return text;}public String getOther(){return other;}public void setText(String t){text=t;}}
 public static class Result {public String text;public Result(String t){text=t;}public String getText(){return text;}}
 public interface Api {@RequestLine("POST /")@Headers("Content-Type: application/json")void send(Input input);}
 private final Api client;private final int repeats;public FeignValueFixture(Api c,int n){client=c;repeats=n;}
 public Result root(Input input){client.send(input);if(repeats==2)client.send(input);return new Result(input.getText());}
 public static void main(String[] args)throws Exception{
  HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);List<String> received=Collections.synchronizedList(new ArrayList<>());server.createContext("/",e->{ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] v=new byte[1024];int n;while((n=e.getRequestBody().read(v))!=-1)b.write(v,0,n);received.add(new String(b.toByteArray(),"UTF-8"));boolean fail=e.getRequestURI().getPath().startsWith("/fail");e.sendResponseHeaders(fail?500:204,-1);e.close();});server.start();
  List<Map> cases=new ArrayList<>();int serial=0;
  try{for(String kind:new String[]{"normal","normal","custom-encoder","normal","custom-serializer","normal","worker-failure","normal","fallback","normal","repeat"}){
   ObjectMapper mapper=new ObjectMapper();if(kind.equals("custom-serializer")){SimpleModule mod=new SimpleModule();mod.addSerializer(Input.class,new JsonSerializer<Input>(){public void serialize(Input input,JsonGenerator g,SerializerProvider p)throws IOException{g.writeStartObject();g.writeStringField("text",input.getText());g.writeStringField("other",input.getOther());g.writeEndObject();}});mapper.registerModule(mod);}
   Encoder encoder=new SpringEncoder(()->new HttpMessageConverters(new MappingJackson2HttpMessageConverter(mapper)));if(kind.equals("custom-encoder")){final Encoder inner=encoder;encoder=(body,type,template)->{Input input=(Input)body;input.setText(input.getText());inner.encode(body,type,template);};}
   String endpoint="http://127.0.0.1:"+server.getAddress().getPort()+(kind.equals("worker-failure")||kind.equals("fallback")?"/fail":"");Api client=kind.equals("fallback")?HystrixFeign.builder().encoder(encoder).target(Api.class,endpoint,new Api(){public void send(Input input){input.setText(input.getText());}}):HystrixFeign.builder().encoder(encoder).target(Api.class,endpoint);FeignValueFixture service=new FeignValueFixture(client,kind.equals("repeat")?2:1);Input input=new Input("SAME","SAME");String span=String.format("%016x",++serial);W3CTraceContext ctx=W3CTraceContext.server("00-11111111111111111111111111111111-"+span+"-01","fixture=feign");SpringTransportAgent.Transport.ASYNC.set(ctx);Map row=new LinkedHashMap();row.put("kind",kind);row.put("message",ctx.message());
   try{row.put("value",service.root(input).text);row.put("aborted",false);}catch(com.netflix.hystrix.exception.HystrixRuntimeException original){if(!kind.equals("worker-failure"))throw original;row.put("aborted",true);}finally{SpringTransportAgent.Transport.ASYNC.remove();}for(Object raw:MonitorSafety.inspect().values())if(raw instanceof Integer&&((Integer)raw)!=0)throw new IllegalStateException("Monitor state leaked: "+MonitorSafety.inspect());cases.add(row);
  }}finally{server.stop(0);com.netflix.hystrix.Hystrix.reset();}
  System.out.println(new ObjectMapper().writeValueAsString(cases));
 }
}
