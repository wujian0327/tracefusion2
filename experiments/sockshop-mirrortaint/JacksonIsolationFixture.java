import java.io.*;
import java.net.*;
import java.util.*;
import java.lang.reflect.*;

/** No business Jackson on the application classpath; two native child loaders. */
public final class JacksonIsolationFixture {
    static class NativeLoader extends URLClassLoader {
        int toStringCalls;
        NativeLoader(URL[] urls){super(urls,null);}
        public String toString(){toStringCalls++;return "custom-loader";}
    }
    public static void main(String[] args)throws Exception{
        try{Class.forName("com.fasterxml.jackson.databind.ObjectMapper");throw new AssertionError("Agent leaked original Jackson namespace");}
        catch(ClassNotFoundException expected){}
        Field json=PlannedServiceAgent.Recorder.class.getDeclaredField("JSON");json.setAccessible(true);
        Object internal=json.get(null);if(!internal.getClass().getName().equals("tracefusion.internal.jackson.databind.ObjectMapper"))throw new AssertionError("Private JSON missing");
        List reports=new ArrayList();
        for(String dir:args){
            File[] files=new File(dir).listFiles((d,n)->n.startsWith("jackson-")&&n.endsWith(".jar"));if(files==null||files.length!=3)throw new AssertionError("Need exact native Jackson triad");
            URL[] urls=new URL[files.length];for(int i=0;i<files.length;i++)urls[i]=files[i].toURI().toURL();
            try(NativeLoader loader=new NativeLoader(urls)){
                Object mapper=Class.forName("com.fasterxml.jackson.databind.ObjectMapper",true,loader).newInstance();BusinessJackson.mapper(mapper);
                Object value=BusinessJackson.call(mapper,"readValue","{\"value\":17}",Map.class);if(!Integer.valueOf(17).equals(((Map)value).get("value")))throw new AssertionError("Native decoder failed");
                if(loader.toStringCalls!=0)throw new AssertionError("Observer invoked user loader.toString");
                Map r=new LinkedHashMap();r.put("version",String.valueOf(BusinessJackson.call(mapper,"version")));r.put("hash",ExecutionKernelHooks.classHash(mapper.getClass()));r.put("separate_loader",mapper.getClass().getClassLoader()==loader);reports.add(r);
            }
        }
        Map result=new LinkedHashMap();result.put("no_original_Jackson_in_system_loader",true);result.put("private_agent_mapper",internal.getClass().getName());result.put("native_loaders",reports);PlannedServiceAgent.Recorder.emit("isolation-fixture",result);
        System.out.println(BusinessJackson.call(internal,"writeValueAsString",result));
    }
}
