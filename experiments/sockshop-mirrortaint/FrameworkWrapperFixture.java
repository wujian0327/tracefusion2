import java.util.*;
import java.net.*;
import java.io.*;
import com.sun.net.httpserver.*;
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Actual original Spring/Jackson, HTTP and Map identities; oracle lives outside. */
public class FrameworkWrapperFixture {
    public static class Input {public String text;public Input(String t){text=t;}public String getText(){return text;}}
    public static class Reply {public Object data;public Reply(){}public Object getData(){return data;}public void setData(Object d){data=d;}}
    public static class CustomTemplate extends RestTemplate {}
    static RestTemplate normal=new RestTemplate(),custom=new CustomTemplate();
    static HttpHeaders nonnullHeaders=new HttpHeaders();
    public static Reply root(Input in,String url,int mode){
        HttpHeaders headers=null;if(mode==2)headers=nonnullHeaders;
        HttpEntity<Input> request=new HttpEntity<>(in,headers);
        RestTemplate template=mode==3?custom:normal;
        if(mode==1)template.exchange(url,HttpMethod.POST,request,Reply.class,new Object[0]);
        Reply result=template.exchange(url,HttpMethod.POST,request,Reply.class,new Object[0]).getBody();
        if(mode==4)result=opaque(result);
        return result;
    }
    static Reply opaque(Reply reply){int[] unsupported=new int[1];return reply;}
    public static void main(String[] args)throws Exception{
        HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/reply",exchange->{byte[] request=read(exchange.getRequestBody());String path=exchange.getRequestURI().getPath();String body=path.endsWith("/empty")?"{\"data\":{}}":path.endsWith("/null")?"{\"data\":{\"text\":null}}":"{\"data\":{\"text\":\"SAME\",\"other\":\"SAME\"}}";exchange.getResponseHeaders().set("Content-Type","application/json");byte[] bytes=body.getBytes("UTF-8");exchange.sendResponseHeaders(path.endsWith("/fail")?500:200,bytes.length);exchange.getResponseBody().write(bytes);exchange.close();});server.start();
        ObjectMapper json=new ObjectMapper();List<Map> cases=new ArrayList<>();String base="http://127.0.0.1:"+server.getAddress().getPort()+"/reply";
        try{for(int i=0;i<16;i++){
            int mode=i%8;W3CTraceContext c=W3CTraceContext.server("00-66666666666666666666666666666666-"+String.format("%016x",i+1)+"-01","fixture=framework");SpringTransportAgent.Transport.ASYNC.set(c);Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",c.fields().get("message"));
            try{Reply result=root(new Input("SAME"),base+(mode==5?"/fail":mode==6?"/empty":mode==7?"/null":""),mode);ResponseBindingHooks.verifySerialization(result,json);row.put("response",json.readValue(json.writeValueAsString(result),Map.class));row.put("status","normal");Map wire=c.fields();wire.put("uri","fixture:framework");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}}
            catch(org.springframework.web.client.HttpServerErrorException expected){row.put("status","aborted");}cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();
        }}finally{server.stop(0);}System.out.println(json.writeValueAsString(cases));
    }
    static byte[] read(InputStream in)throws IOException{ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[1024];int n;while((n=in.read(b))!=-1)out.write(b,0,n);return out.toByteArray();}
}
