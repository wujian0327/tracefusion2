import java.io.*;
import java.security.*;
import java.util.*;

/** Runtime bytecode identity used by the finite JDK read-effect contract. */
public final class JdkContractProbe {
    // Bootstrap definitions are fixed for this process under the supported
    // runtime contract (no class redefinition). Keep actual hashes in every
    // witness; caching never substitutes a configured/expected digest.
    static final Map<Class<?>,String> HASHES=new IdentityHashMap<Class<?>,String>();
    static final String[] CLASSES={"java/util/ArrayList","java/util/Arrays$ArrayList","java/util/Collections$SingletonList","java/util/Collections$EmptyList","java/util/Collection","java/util/stream/StreamSupport","java/util/stream/ReferencePipeline","java/util/stream/ReferencePipeline$Head","java/util/Optional","java/lang/invoke/LambdaMetafactory","java/lang/StringBuilder","java/lang/AbstractStringBuilder"};
    static String hash(String name)throws Exception{
        Class<?> type=Class.forName(name.replace('/','.'),false,null);
        synchronized(HASHES){String cached=HASHES.get(type);if(cached!=null)return cached;}
        InputStream in=type.getResourceAsStream("/"+name+".class");if(in==null)throw new IllegalStateException("Runtime class absent: "+name);
        MessageDigest digest=MessageDigest.getInstance("SHA-256");byte[] b=new byte[8192];try{int n;while((n=in.read(b))!=-1)digest.update(b,0,n);}finally{in.close();}
        StringBuilder out=new StringBuilder();for(byte x:digest.digest())out.append(String.format("%02x",x&255));String result=out.toString();
        synchronized(HASHES){String previous=HASHES.get(type);if(previous!=null&&!previous.equals(result))throw new IllegalStateException("Runtime class resource changed");HASHES.put(type,result);}return result;
    }
    static Map<String,String> hashes()throws Exception{Map<String,String> r=new TreeMap<>();for(String name:CLASSES)r.put(name,hash(name));return r;}
    static Map<String,String> selected(String[] names)throws Exception{Map<String,String> r=new TreeMap<>();for(String n:names)r.put(n,hash(n));return r;}
    public static void main(String[] args)throws Exception{System.out.println("java.runtime.version="+System.getProperty("java.runtime.version"));for(Map.Entry<String,String> e:(args.length==0?hashes():selected(args)).entrySet())System.out.println(e.getKey()+"="+e.getValue());}
}
