import java.lang.reflect.*;
import java.util.*;

/** Inspect the application's Jackson through its own loader; no Jackson linkage. */
public final class BusinessJackson {
    static final Set<Class<?>> OBSERVED=Collections.newSetFromMap(new IdentityHashMap<Class<?>,Boolean>());
    static Class<?> boxed(Class<?> c){
        if(!c.isPrimitive())return c;
        if(c==boolean.class)return Boolean.class;if(c==int.class)return Integer.class;
        if(c==long.class)return Long.class;if(c==double.class)return Double.class;
        if(c==float.class)return Float.class;if(c==short.class)return Short.class;
        if(c==byte.class)return Byte.class;if(c==char.class)return Character.class;return Void.class;
    }
    static boolean moreSpecific(Method a,Method b){
        Class<?>[] x=a.getParameterTypes(),y=b.getParameterTypes();boolean strict=false;
        for(int i=0;i<x.length;i++){if(!boxed(y[i]).isAssignableFrom(boxed(x[i])))return false;strict|=x[i]!=y[i];}
        return strict;
    }
    static Object call(Object receiver,String name,Object...args)throws Exception{
        if(receiver==null)throw new IllegalStateException("Null business Jackson receiver: "+name);
        List<Method> choices=new ArrayList<>();
        for(Method m:receiver.getClass().getMethods()){
            if(!m.getName().equals(name)||m.isBridge()||Modifier.isStatic(m.getModifiers())||m.getParameterTypes().length!=args.length)continue;
            Class<?>[] ts=m.getParameterTypes();boolean fits=true;
            for(int i=0;i<ts.length;i++)if(args[i]==null?ts[i].isPrimitive():!boxed(ts[i]).isInstance(args[i]))fits=false;
            if(fits)choices.add(m);
        }
        List<Method> best=new ArrayList<>();
        for(Method a:choices){boolean dominated=false;for(Method b:choices)if(moreSpecific(b,a))dominated=true;if(!dominated)best.add(a);}
        if(best.size()!=1)throw new IllegalStateException("Missing/ambiguous business Jackson API: "+receiver.getClass().getName()+"."+name);
        Method m=best.get(0);m.setAccessible(true);
        try{return m.invoke(receiver,args);}catch(InvocationTargetException e){Throwable t=e.getCause();if(t instanceof Exception)throw (Exception)t;if(t instanceof Error)throw (Error)t;throw e;}
    }
    static boolean exact(Object o,String name){return o!=null&&o.getClass().getName().equals("com.fasterxml.jackson.databind."+name);}
    static boolean yes(Object o){return Boolean.TRUE.equals(o);}
    static Object enumValue(Object mapper,String type,String name)throws Exception{
        Class c=Class.forName("com.fasterxml.jackson.databind."+type,false,mapper.getClass().getClassLoader());return Enum.valueOf(c,name);
    }
    static void mapper(Object mapper)throws Exception{
        if(!exact(mapper,"ObjectMapper"))throw new IllegalStateException("Unmodeled ObjectMapper subclass");
        observe(mapper);
    }
    static void observe(Object mapper)throws Exception{
        Class<?> definition=mapper.getClass();while(definition!=null&&!definition.getName().equals("com.fasterxml.jackson.databind.ObjectMapper"))definition=definition.getSuperclass();
        if(definition==null)throw new IllegalStateException("Business mapper has no native Jackson definition");
        synchronized(PlannedServiceAgent.Recorder.class){if(OBSERVED.contains(definition))return;
            Object internal=PlannedServiceAgent.Recorder.class.getDeclaredField("JSON").get(null);
            if(!internal.getClass().getName().equals("tracefusion.internal.jackson.databind.ObjectMapper"))throw new IllegalStateException("Agent JSON dependency not isolated");
            Map r=PlannedServiceAgent.Recorder.row();r.put("business_class",definition.getName());r.put("mapper_class",mapper.getClass().getName());r.put("business_class_sha256",ExecutionKernelHooks.classHash(definition));
            ClassLoader loader=definition.getClassLoader();r.put("business_loader",loader==null?"bootstrap":loader.getClass().getName()+"@"+Integer.toHexString(System.identityHashCode(loader)));
            java.security.CodeSource source=definition.getProtectionDomain().getCodeSource();java.net.URL location=source!=null&&source.getClass()==java.security.CodeSource.class?source.getLocation():null;
            r.put("business_code_source",location==null?null:location.getProtocol()+":"+location.getPath());
            // Metadata observation must not dispatch user ObjectMapper overrides.
            r.put("business_version",definition.getPackage().getImplementationVersion());r.put("agent_class",internal.getClass().getName());r.put("agent_class_sha256",ExecutionKernelHooks.classHash(internal.getClass()));
            PlannedServiceAgent.Recorder.emit("jackson-isolation",r);OBSERVED.add(definition);}
    }
}
