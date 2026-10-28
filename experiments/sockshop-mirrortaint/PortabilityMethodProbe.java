import java.lang.reflect.*;
import java.lang.annotation.Annotation;
import java.beans.*;
import java.util.*;

/** No agent, no business method execution: original reflection metadata only. */
public final class PortabilityMethodProbe {
    static String desc(Class<?> c){
        if(c.isArray())return c.getName().replace('.','/');
        if(!c.isPrimitive())return "L"+c.getName().replace('.','/')+";";
        return c==void.class?"V":c==boolean.class?"Z":c==byte.class?"B":c==char.class?"C":c==short.class?"S":c==int.class?"I":c==long.class?"J":c==float.class?"F":"D";
    }
    static Map<String,Object> map(){return new LinkedHashMap<String,Object>();}
    static List<Map<String,Object>> annotations(Annotation[] annotations){
        List<Map<String,Object>> out=new ArrayList<Map<String,Object>>();
        for(Annotation a:annotations){String name=a.annotationType().getName();if(!name.startsWith("org.springframework.web.bind.annotation.")&&!name.startsWith("com.fasterxml.jackson.annotation."))continue;
            Map<String,Object> row=map();row.put("annotation",name);
            for(String n:Arrays.asList("value","path","method","name","required"))try{Object v=a.annotationType().getMethod(n).invoke(a);row.put(n,v);}catch(Exception absent){}
            out.add(row);
        }return out;
    }
    static boolean leaf(Class<?> c){return c.isPrimitive()||c==String.class||Number.class.isAssignableFrom(c)||c==Boolean.class||c.isEnum()||Date.class.isAssignableFrom(c)||c==UUID.class;}
    static Map<String,Object> bean(Class<?> c,Set<Class<?>> seen,int depth){
        Map<String,Object> out=map();out.put("type",c.getName());out.put("descriptor",desc(c));out.put("leaf",leaf(c));
        if(leaf(c)||depth>5||!seen.add(c)){if(depth>5||seen.contains(c)&&!leaf(c))out.put("bounded_metadata",true);return out;}
        List<Map<String,Object>> fields=new ArrayList<Map<String,Object>>();out.put("properties",fields);
        try{
            for(PropertyDescriptor p:Introspector.getBeanInfo(c).getPropertyDescriptors()){
                Method getter=p.getReadMethod();if(getter==null||p.getName().equals("class"))continue;
                Map<String,Object> row=map();row.put("property",p.getName());row.put("getter",getter.getDeclaringClass().getName()+"."+getter.getName());row.put("type",p.getPropertyType().getName());row.put("generic_type",getter.getGenericReturnType().getTypeName());row.put("descriptor",desc(p.getPropertyType()));row.put("annotations",annotations(getter.getAnnotations()));
                Field field=null;for(Class<?> k=c;k!=null;k=k.getSuperclass())try{field=k.getDeclaredField(p.getName());break;}catch(NoSuchFieldException missing){}
                if(field!=null){row.put("field",field.getDeclaringClass().getName().replace('.','/')+"."+field.getName());row.put("field_annotations",annotations(field.getAnnotations()));}
                else row.put("field",null);
                if(!leaf(p.getPropertyType())&&!p.getPropertyType().getName().startsWith("java."))row.put("nested",bean(p.getPropertyType(),new HashSet<Class<?>>(seen),depth+1));
                Type t=getter.getGenericReturnType();if(t instanceof ParameterizedType){List<Object> elements=new ArrayList<Object>();for(Type e:((ParameterizedType)t).getActualTypeArguments())if(e instanceof Class&&!leaf((Class)e))elements.add(bean((Class)e,new HashSet<Class<?>>(seen),depth+1));row.put("generic_beans",elements);}
                fields.add(row);
            }
        }catch(Exception e){out.put("metadata_error",e.toString());}
        return out;
    }
    static String json(Object x){
        if(x==null)return "null";if(x instanceof Boolean||x instanceof Number)return x.toString();
        if(x instanceof Map){List<String> a=new ArrayList<String>();for(Object raw:((Map)x).entrySet()){Map.Entry e=(Map.Entry)raw;a.add(json(String.valueOf(e.getKey()))+":"+json(e.getValue()));}return "{"+String.join(",",a)+"}";}
        if(x instanceof Iterable){List<String>a=new ArrayList<String>();for(Object v:(Iterable)x)a.add(json(v));return "["+String.join(",",a)+"]";}
        if(x.getClass().isArray()){List<Object>a=new ArrayList<Object>();for(int i=0;i<Array.getLength(x);i++)a.add(Array.get(x,i));return json(a);}
        String s=String.valueOf(x);StringBuilder b=new StringBuilder("\"");for(int i=0;i<s.length();i++){char c=s.charAt(i);if(c=='"'||c=='\\')b.append('\\').append(c);else if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}return b.append('"').toString();
    }
    public static void main(String[] args)throws Exception{
        Class<?> c=Class.forName(args[0],false,Thread.currentThread().getContextClassLoader());List<Object> matches=new ArrayList<Object>();
        for(Method m:c.getDeclaredMethods())if(m.getName().equals(args[1])){
            Map<String,Object> r=map();String signature=c.getName().replace('.','/')+"."+m.getName()+"(";for(Class<?> t:m.getParameterTypes())signature+=desc(t);signature+=")"+desc(m.getReturnType());r.put("entry",signature);r.put("class_annotations",annotations(c.getAnnotations()));r.put("method_annotations",annotations(m.getAnnotations()));r.put("return_generic",m.getGenericReturnType().getTypeName());r.put("return_bean",bean(m.getReturnType(),new HashSet<Class<?>>(),0));List<Object> params=new ArrayList<Object>();Annotation[][] annotations=m.getParameterAnnotations();
            for(int i=0;i<m.getParameterTypes().length;i++){Map<String,Object> a=bean(m.getParameterTypes()[i],new HashSet<Class<?>>(),0);a.put("annotations",annotations(annotations[i]));params.add(a);}r.put("parameters",params);matches.add(r);
        }
        Map<String,Object> out=map();out.put("java_runtime",System.getProperty("java.runtime.version"));out.put("java_vendor",System.getProperty("java.vendor"));out.put("methods",matches);out.put("business_methods_executed",false);System.out.println(json(out));
    }
}
