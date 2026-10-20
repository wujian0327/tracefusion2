import java.io.*;
import java.lang.reflect.*;
import java.util.*;
import com.fasterxml.jackson.core.*;
import com.fasterxml.jackson.databind.*;

/** Raw HTTP bytes and decoded identities, separate from provenance inference. */
public final class SourceEvidenceHooks {
    static final Map<Object,Capture> CAPTURES=Collections.synchronizedMap(new IdentityHashMap<Object,Capture>());
    static boolean enabled(){return Boolean.TRUE.equals(PlannedServiceAgent.plan.get("source_evidence"));}
    static class Capture {
        final Object original;final ByteArrayOutputStream bytes=new ByteArrayOutputStream();InputStream stream;boolean overflow,reset,eof;
        Capture(Object original){this.original=original;}
        void append(byte[] b,int off,int len){if(bytes.size()+len<=1048576)bytes.write(b,off,len);else overflow=true;}
        InputStream body()throws Exception{
            if(stream!=null)return stream;
            final InputStream input=(InputStream)SpringTransportAgent.Transport.api(original,"org.springframework.http.HttpInputMessage","getBody",new Class[0]);
            stream=new FilterInputStream(input){
                public int read()throws IOException{int n=in.read();if(n>=0)append(new byte[]{(byte)n},0,1);else eof=true;return n;}
                public int read(byte[] b,int off,int len)throws IOException{int n=in.read(b,off,len);if(n>0)append(b,off,n);else if(n==-1)eof=true;return n;}
                public long skip(long n)throws IOException{reset=true;return in.skip(n);}
                public synchronized void reset()throws IOException{reset=true;in.reset();}
            };return stream;
        }
    }
    public static Object input(final Object original){
        if(!enabled())return original;
        try{
            ClassLoader loader=Thread.currentThread().getContextClassLoader();Class<?> type=Class.forName("org.springframework.http.HttpInputMessage",false,loader);
            if(Class.forName("org.springframework.http.converter.json.MappingJacksonInputMessage",false,loader).isInstance(original))return original;
            final Capture c=new Capture(original);
            Object proxy=Proxy.newProxyInstance(loader,new Class[]{type},new InvocationHandler(){public Object invoke(Object p,Method m,Object[] a)throws Throwable{
                if(m.getDeclaringClass()==Object.class){if(m.getName().equals("hashCode"))return System.identityHashCode(p);if(m.getName().equals("equals"))return p==a[0];return "TF2 input observation";}
                if(m.getName().equals("getBody"))return c.body();
                try{return m.invoke(original,a);}catch(InvocationTargetException e){throw e.getCause();}
            }});CAPTURES.put(proxy,c);return proxy;
        }catch(Throwable e){PlannedServiceAgent.Recorder.problem("source-input:"+e);return original;}
    }
    static Object content(Object body)throws Exception{
        if(body!=null&&body.getClass().getName().equals("org.springframework.hateoas.Resource")){
            InputStream in=body.getClass().getResourceAsStream("/org/springframework/hateoas/Resource.class");ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] b=new byte[4096];try{int n;while((n=in.read(b))!=-1)bytes.write(b,0,n);}finally{in.close();}
            if(!PlannedServiceAgent.Recorder.hash(bytes.toByteArray()).equals("35917e028c262c46d1bbeb80cdba2e3bee26f90e3807a7b58d7211e50f78a4eb"))throw new IllegalStateException("Unreviewed HATEOAS Resource version");
            return SpringTransportAgent.Transport.api(body,"org.springframework.hateoas.Resource","getContent",new Class[0]);
        }
        return body;
    }
    public static void read(Object body,Object message,Object mapper){
        if(!enabled())return;Capture c=CAPTURES.remove(message);if(c==null)return;
        synchronized(PlannedServiceAgent.Recorder.class){try{
            Map r=new LinkedHashMap();if(!SpringTransportAgent.Transport.RPC.get().isEmpty()){r.putAll(SpringTransportAgent.Transport.RPC.get().peek());r.put("direction","response");}
            else{r.putAll(SpringTransportAgent.Transport.context());r.put("direction","request");}
            if(r.get("message")==null)return;
            byte[] bytes=c.bytes.toByteArray();ObjectMapper parser=new ObjectMapper();parser.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
            JsonParser jp=parser.getFactory().createParser(bytes);JsonNode document=parser.readTree(jp);
            long length=((Number)SpringTransportAgent.Transport.api(SpringTransportAgent.Transport.headers(message),"org.springframework.http.HttpHeaders","getContentLength",new Class[0])).longValue();
            boolean complete=document!=null&&jp.nextToken()==null&&!c.overflow&&!c.reset&&(c.eof||length>=0&&length==bytes.length);jp.close();
            Object decoded=content(body);r.put("phase","read");r.put("raw_base64",Base64.getEncoder().encodeToString(bytes));r.put("raw_sha256",PlannedServiceAgent.Recorder.hash(bytes));
            r.put("document_complete",complete);r.put("body_type",body==null?null:body.getClass().getName());r.put("body_object",PlannedServiceAgent.Recorder.id(body));
            r.put("content_length",length);r.put("observed_eof",c.eof);r.put("capture_version",2);
            r.put("content_type",decoded==null?null:decoded.getClass().getName());r.put("content_object",PlannedServiceAgent.Recorder.id(decoded));r.put("fields",SpringTransportAgent.Transport.snapshot(decoded));
            r.put("mapper_class",mapper.getClass().getName());r.put("fact_only",true);SpringTransportAgent.Transport.emit("http-source-fact",r);
        }catch(Throwable e){PlannedServiceAgent.Recorder.problem("source-read:"+e);}}
    }
    public static void abort(Object message){CAPTURES.remove(message);}
}
