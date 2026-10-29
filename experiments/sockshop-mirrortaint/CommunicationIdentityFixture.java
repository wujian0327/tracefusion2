import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.net.*;
import java.io.*;
import com.sun.net.httpserver.*;
import feign.*;
import feign.codec.Decoder;
import org.springframework.cloud.openfeign.support.SpringDecoder;
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Real incoming HTTP, repeated/retried/nested Feign calls, one root worker. */
public class CommunicationIdentityFixture {
    public static class Box {public String text;public Box(){}public String getText(){return text;}}
    public interface Remote {@RequestLine("GET /data?key={key}") Box get(@Param("key") String key);}
    public Remote api;
    public Box root(String key){api.get("first");return api.get(key);}
    static Remote nested;static boolean observe;static final AtomicBoolean retried=new AtomicBoolean();static final IOException ORIGINAL=new IOException("original-client-failure");
    static final ThreadLocal<IOException> NETWORK_ERROR=new ThreadLocal<>();
    static class RetryableRequestPath extends org.springframework.cloud.openfeign.loadbalancer.RetryableFeignBlockingLoadBalancerClient {
        RetryableRequestPath(Client delegate){super(delegate,null,null,(org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory)null);}
        Request actualRequest(Request input){return buildRequest(input,input.url());}
    }
    static Remote client(String url,Decoder decoder,boolean negative){
        Client delegate=Boolean.getBoolean("fixture.okhttp")?new feign.okhttp.OkHttpClient():new Client.Default(null,null);
        RetryableRequestPath retryable=Boolean.getBoolean("fixture.retryable.lb")?new RetryableRequestPath(delegate):null;
        Client client=(request,options)->{
            if(request.url().contains("key=retry")&&!retried.getAndSet(true))throw ORIGINAL;
            if(request.url().contains("key=error"))throw ORIGINAL;
            if(request.url().contains("key=nested"))nested.get("inner");
            Response response;try{response=delegate.execute(retryable==null?request:retryable.actualRequest(request),options);}catch(IOException error){NETWORK_ERROR.set(error);throw error;}
            if(negative&&request.url().contains("key=wrong")){
                Request other=Request.create(request.httpMethod(),request.url(),request.headers(),request.body(),request.charset(),request.requestTemplate());
                return response.toBuilder().request(other).build();
            }
            return response;
        };
        return Feign.builder().client(client).decoder(decoder).retryer(new Retryer.Default(1,1,2)).target(Remote.class,url);
    }
    public static void main(String[] args)throws Exception{
        observe=Boolean.getBoolean("fixture.observe");boolean negative=Boolean.getBoolean("fixture.wrong.response");
        ObjectMapper mapper=new ObjectMapper();HttpServer backend=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);ExecutorService backendPool=Executors.newFixedThreadPool(4);backend.setExecutor(backendPool);
        List<Map> wire=Collections.synchronizedList(new ArrayList<>());
        backend.createContext("/data",exchange->{try{Map r=new LinkedHashMap();r.put("path",exchange.getRequestURI().toString());r.put("traceparent",exchange.getRequestHeaders().getFirst("traceparent"));wire.add(r);if(exchange.getRequestURI().toString().contains("key=disconnect"))return;byte[] body="{\"text\":\"SAME\"}".getBytes("UTF-8");exchange.getResponseHeaders().set("Content-Type","application/json");exchange.sendResponseHeaders(200,body.length);exchange.getResponseBody().write(body);}finally{exchange.close();}});backend.start();
        Decoder decoder=new SpringDecoder(()->new HttpMessageConverters(new MappingJackson2HttpMessageConverter(mapper)));
        String url="http://127.0.0.1:"+backend.getAddress().getPort();nested=client(url,decoder,false);CommunicationIdentityFixture fixture=new CommunicationIdentityFixture();fixture.api=client(url,decoder,negative);
        HttpServer root=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);ExecutorService rootPool=Executors.newSingleThreadExecutor();root.setExecutor(rootPool);List<Map> cases=new ArrayList<>();
        root.createContext("/root",exchange->{String key=exchange.getRequestURI().getQuery();Map row=new LinkedHashMap();W3CTraceContext context=W3CTraceContext.server(exchange.getRequestHeaders().getFirst("traceparent"),null);
            row.put("key",key);row.put("message",context.message());if(observe)SpringTransportAgent.Transport.ASYNC.set(context);
            try{Box result=fixture.root(key);row.put("value",result.text);row.put("status","normal");}
            catch(RetryableException expected){row.put("status","business-exception");row.put("same_cause",expected.getCause()==(key.equals("disconnect")?NETWORK_ERROR.get():ORIGINAL));}
            finally{if(observe){Map state=MonitorSafety.inspect();row.put("clean_frames",((Number)state.get("frames")).intValue()==0);row.put("clean_calls",((Number)state.get("calls")).intValue()==0);row.put("clean_rpc",SpringTransportAgent.Transport.RPC.get().isEmpty()&&SpringTransportAgent.Transport.SPANS.get().isEmpty()&&SpringTransportAgent.Communication.ACTIVE.get().isEmpty());SpringTransportAgent.Transport.ASYNC.remove();}cases.add(row);try{byte[] data=mapper.writeValueAsBytes(row);exchange.sendResponseHeaders(200,data.length);exchange.getResponseBody().write(data);}finally{exchange.close();}}
        });root.start();
        try{int n=0;for(String key:negative?new String[]{"same","wrong","same"}:Boolean.getBoolean("fixture.network.failure")?new String[]{"same","retry","nested","error","disconnect","same"}:new String[]{"same","retry","nested","error","same"}){
            HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:"+root.getAddress().getPort()+"/root?"+key).openConnection();c.setRequestProperty("traceparent","00-44444444444444444444444444444444-"+String.format("%016x",++n)+"-01");try(InputStream input=c.getInputStream()){while(input.read()!=-1){}}c.disconnect();
        }}finally{root.stop(0);backend.stop(0);rootPool.shutdownNow();backendPool.shutdownNow();}
        Map result=new LinkedHashMap();result.put("cases",cases);result.put("wire",wire);System.out.println(mapper.writeValueAsString(result));
    }
}
