import java.util.*;

/** Finite original-library witnesses. Never computes provenance or expected sources. */
public final class FrameworkCallHooks {
    static final String EXCHANGE="org/springframework/web/client/RestTemplate.exchange(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;";
    static Map config(){return ExecutionKernelHooks.enabled()?(Map)((Map)PlannedServiceAgent.plan.get("execution_kernel")).get("framework_contracts"):null;}
    static Object invoke(Object o,String method)throws Exception{return o.getClass().getMethod(method).invoke(o);}
    static Map hashes()throws Exception{
        Map result=new TreeMap();ClassLoader loader=Thread.currentThread().getContextClassLoader();
        for(Object raw:((Map)config().get("class_sha256")).keySet()){
            String name=(String)raw;result.put(name,ExecutionKernelHooks.classHash(Class.forName(name.replace('/','.'),false,loader)));
        }return result;
    }
    static Map entity(Object receiver,Object[] args)throws Exception{
        Map f=new LinkedHashMap();f.put("kind","http-entity-null-headers");f.put("class_sha256",hashes());
        boolean valid=receiver.getClass().getName().equals("org.springframework.http.HttpEntity")&&args.length==2&&args[1]==null&&invoke(receiver,"getBody")==args[0]&&((Map)invoke(receiver,"getHeaders")).isEmpty();
        f.put("valid",valid);f.put("body",PlannedServiceAgent.Recorder.value(invoke(receiver,"getBody")));return f;
    }
    static void end(Map start,Object result,Map row)throws Exception{
        if(config()==null)return;String call=(String)start.get("callee");Object recv=start.get("_receiver_ref");Object[] args=(Object[])start.get("_args_ref");Map f=new LinkedHashMap();
        if(EXCHANGE.equals(call)){
            f.put("kind","rest-exchange");f.put("class_sha256",hashes());
            boolean valid=recv!=null&&recv.getClass().getName().equals("org.springframework.web.client.RestTemplate")&&((List)invoke(recv,"getInterceptors")).isEmpty()&&invoke(recv,"getRequestFactory").getClass().getName().equals("org.springframework.http.client.SimpleClientHttpRequestFactory")&&result!=null&&result.getClass().getName().equals("org.springframework.http.ResponseEntity")&&args[2]!=null&&args[2].getClass().getName().equals("org.springframework.http.HttpEntity")&&args[3] instanceof Class&&args[4] instanceof Object[]&&((Object[])args[4]).length==0;
            List converters=new ArrayList();if(recv!=null&&recv.getClass().getName().equals("org.springframework.web.client.RestTemplate"))for(Object converter:(List)invoke(recv,"getMessageConverters"))converters.add(converter.getClass().getName().replace('.','/'));
            valid=valid&&!converters.isEmpty()&&((List)config().get("converter_classes")).containsAll(converters);
            f.put("valid",valid);f.put("converter_classes",converters);f.put("url",args[0]);f.put("method",String.valueOf(args[1]));f.put("response_class",args[3] instanceof Class?((Class)args[3]).getName():null);
            if(valid){f.put("request_body",PlannedServiceAgent.Recorder.value(invoke(args[2],"getBody")));Object body=invoke(result,"getBody");f.put("body",PlannedServiceAgent.Recorder.value(body));f.put("body_type",body==null?null:body.getClass().getName());f.put("fields",SpringTransportAgent.Transport.snapshot(body));}
        }else if(call.equals("org/springframework/http/ResponseEntity.getBody()Ljava/lang/Object;")||call.equals("org/springframework/http/HttpEntity.getBody()Ljava/lang/Object;")){
            f.put("kind","http-entity-body");f.put("class_sha256",hashes());f.put("valid",recv!=null&&Arrays.asList("org.springframework.http.ResponseEntity","org.springframework.http.HttpEntity").contains(recv.getClass().getName())&&result==invoke(recv,"getBody"));f.put("body",PlannedServiceAgent.Recorder.value(result));
        }
        if(!f.isEmpty())row.put("framework_contract",f);
    }
}
