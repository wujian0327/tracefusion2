import java.net.*;
import java.util.*;
import java.util.concurrent.*;
import org.springframework.aop.interceptor.AsyncExecutionInterceptor;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.*;
import org.springframework.hateoas.Resource;
import org.springframework.scheduling.annotation.AsyncResult;
import org.springframework.web.client.RestTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;

public class RequestAsyncFixture {
    public static class Item {private String text,id;public Item(){}public String getId(){return id;}public void setId(String x){id=x;}public String getText(){return text;}public void setText(String x){text=x;}public String toString(){return text;}}
    public static class Out {private String text;public Out(){}public String getText(){return text;}public void setText(String x){text=x;}}
    public static class Worker {
        private RestTemplate rest=new RestTemplate();public Item leaked;public Object[] slot=new Object[1];
        public Future<Resource<Item>> load(URI uri,ParameterizedTypeReference<Resource<Item>> type){
            RequestEntity<Void> req=RequestEntity.get(uri).accept(MediaType.APPLICATION_JSON).build();
            String requestRendering=req.toString();ResponseEntity<Resource<Item>> response=rest.exchange(req,type);String resourceRendering=response.getBody().toString();
            return new AsyncResult<Resource<Item>>(response.getBody());
        }
    }
    public static Out root(Worker w,URI uri,URI secondUri,ParameterizedTypeReference<Resource<Item>> type,int mode)throws Exception{
        Future<Resource<Item>> first=w.load(uri,type);Future<Resource<Item>> second=w.load(secondUri,type);
        Resource<Item> one=first.get();Resource<Item> two=second.get();if(mode==3)opaqueTouch(two.getContent());if(mode==4)opaqueGlobal();if(mode==7){w.leaked=two.getContent();opaqueGlobal();}if(mode==8){w.slot[0]=two.getContent();opaqueGlobal();}Out out=new Out();if(mode==6)out.setText("SAME");else if(mode==2)out.setText(two.getContent().getId());else out.setText((mode==1?one:two).getContent().getText());return out;
    }
    public static void opaqueTouch(Item item){System.identityHashCode(item);}
    public static void opaqueGlobal(){System.nanoTime();}
    public static void main(String[] args)throws Exception{
        ExecutorService pool=Executors.newFixedThreadPool(2);Worker altered=new Worker();for(org.springframework.http.converter.HttpMessageConverter converter:altered.rest.getMessageConverters())if(converter.getClass()==org.springframework.http.converter.json.MappingJackson2HttpMessageConverter.class)((org.springframework.http.converter.json.MappingJackson2HttpMessageConverter)converter).getObjectMapper().setPropertyNamingStrategy(com.fasterxml.jackson.databind.PropertyNamingStrategy.SNAKE_CASE);ProxyFactory badFactory=new ProxyFactory(altered);badFactory.setProxyTargetClass(true);badFactory.addAdvice(new AsyncExecutionInterceptor(pool));Worker bad=(Worker)badFactory.getProxy();ProxyFactory factory=new ProxyFactory(new Worker());factory.setProxyTargetClass(true);factory.addAdvice(new AsyncExecutionInterceptor(pool));Worker worker=(Worker)factory.getProxy();worker.slot=new Object[1];bad.slot=new Object[1];List cases=new ArrayList();
        try{for(int n=0;n<24;n++){
            String span=String.format("%016x",n+1);SpringTransportAgent.Transport.ASYNC.set(W3CTraceContext.server("00-11111111111111111111111111111111-"+span+"-01",null));
            int mode=n%12;Out out=root(mode==5?bad:worker,new URI(args[0]+"/first"),new URI(args[0]+(mode==9?"/missing":mode==10?"/null":mode==11?"/duplicate":"/second")),new ParameterizedTypeReference<Resource<Item>>(){},mode);SpringTransportAgent.Transport.writeEnd(SpringTransportAgent.Transport.writeStart(out,null),out);
            Map c=new LinkedHashMap();c.put("message","11111111111111111111111111111111/"+span);c.put("text",out.getText());c.put("mode",mode);cases.add(c);
        }}finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}System.out.println(new ObjectMapper().writeValueAsString(cases));
    }
}
