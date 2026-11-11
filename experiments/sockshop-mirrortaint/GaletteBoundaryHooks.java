import edu.neu.ccs.prl.galette.internal.runtime.Tag;
import edu.neu.ccs.prl.galette.internal.runtime.Tainter;
import java.util.*;
import java.lang.reflect.*;
import java.nio.file.*;

/** Labels declared read-return leaves, records raw facts, exports native tags.
 * No propagation, value equality joins, expected-source sets or TF imports.
 */
public final class GaletteBoundaryHooks {
    static Properties config=new Properties();static java.io.BufferedWriter output;static long seq,ids,frames,calls;static boolean invalid;
    static final IdentityHashMap<Object,String> IDS=new IdentityHashMap<>();static final Map<String,Integer> VERSIONS=new HashMap<>();
    static class Scope {String id,method,root,message;Scope(String id,String method,String root,String message){this.id=id;this.method=method;this.root=root;this.message=message;}}
    static class Call {long id;String caller,callee,frame;int pc;}
    static final ThreadLocal<Deque<Scope>> STACK=ThreadLocal.withInitial(ArrayDeque::new);
    static final ThreadLocal<Deque<Call>> CALLS=ThreadLocal.withInitial(ArrayDeque::new);
    static {
        try {
            try(java.io.InputStream in=Files.newInputStream(Paths.get(System.getProperty("galette.boundary.config")))){config.load(in);}
            output=Files.newBufferedWriter(Paths.get(System.getProperty("galette.boundary.events")),StandardOpenOption.CREATE_NEW);
            emit("start",new LinkedHashMap<>());Runtime.getRuntime().addShutdownHook(new Thread(()->{synchronized(GaletteBoundaryHooks.class){Map m=new LinkedHashMap();m.put("capture_invalid",invalid);emit("closed",m);try{output.close();}catch(Exception e){}}}));
        }catch(Exception error){throw new ExceptionInInitializerError(error);}
    }
    static String id(Object value){if(value==null)return null;String found=IDS.get(value);if(found==null){found="o"+(++ids);IDS.put(value,found);}return found;}
    static Scope scope(){return STACK.get().peek();}
    static String message()throws Exception {
        ClassLoader loader=Thread.currentThread().getContextClassLoader();Class<?> holder=Class.forName("org.springframework.web.context.request.RequestContextHolder",false,loader);
        Object attributes=holder.getMethod("getRequestAttributes").invoke(null);if(attributes==null)throw new IllegalStateException("No actual servlet request");
        if(!attributes.getClass().getName().equals("org.springframework.web.context.request.ServletRequestAttributes"))throw new IllegalStateException("Unreviewed request attributes type");
        Object request=attributes.getClass().getMethod("getRequest").invoke(attributes);
        if(!request.getClass().getName().equals("org.apache.catalina.connector.RequestFacade"))throw new IllegalStateException("Unreviewed servlet request type");
        String header=(String)request.getClass().getMethod("getHeader",String.class).invoke(request,"traceparent");
        if(header==null||!header.matches("00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}"))throw new IllegalStateException("Missing exact request identity");
        return header.substring(3,35)+"/"+header.substring(36,52);
    }
    public static synchronized void enter(String method){try {
        Scope parent=scope();if(parent==null&&!method.equals(config.getProperty("entry")))return;
        String frame="f"+(++frames),root=parent==null?frame:parent.root,msg=parent==null?message():parent.message;
        Scope next=new Scope(frame,method,root,msg);STACK.get().push(next);Map r=new LinkedHashMap();r.put("method",method);r.put("parent",parent==null?null:parent.id);emit("enter",r);
    }catch(Throwable error){problem("enter",error);}}
    public static synchronized void exit(String method){if(scope()==null)return;try{if(!scope().method.equals(method))throw new IllegalStateException("Frame completion differs");Map r=new LinkedHashMap();r.put("method",method);emit("exit",r);STACK.get().pop();}catch(Throwable error){problem("exit",error);}}
    public static synchronized void written(Object owner,String field){if(scope()==null)return;String key=id(owner)+":"+field;int version=VERSIONS.getOrDefault(key,0)+1;VERSIONS.put(key,version);Map r=new LinkedHashMap();r.put("owner",id(owner));r.put("field",field);r.put("version",version);emit("write",r);}
    public static synchronized void sourceEnter(String caller,int pc,String callee){if(scope()==null)return;try{if(!scope().method.equals(caller))throw new IllegalStateException("Source caller scope differs");Call c=new Call();c.id=++calls;c.caller=caller;c.pc=pc;c.callee=callee;c.frame=scope().id;CALLS.get().push(c);Map r=call(c);emit("source-call-enter",r);}catch(Throwable error){problem("source-enter",error);}}
    static Map call(Call c){Map r=new LinkedHashMap();r.put("source_call_id",c.id);r.put("caller",c.caller);r.put("pc",c.pc);r.put("callee",c.callee);r.put("caller_frame",c.frame);return r;}
    public static synchronized void sourceExit(Object result,String callee){if(scope()==null)return;try{Call c=CALLS.get().peek();if(c==null||!c.callee.equals(callee)||!c.frame.equals(scope().id))throw new IllegalStateException("Source completion differs");List<Map> fields=new ArrayList<>();walk(result,"",null,null,fields,new IdentityHashMap<>(),false,c);Map raw=call(c);raw.put("result",id(result));raw.put("fields",fields);emit("source",raw);walk(result,"",null,null,new ArrayList<>(),new IdentityHashMap<>(),true,c);Map done=call(c);done.put("result",id(result));emit("source-call-exit",done);CALLS.get().pop();}catch(Throwable error){problem("source-exit",error);}}
    public static synchronized void sourceThrow(Throwable error,String callee){try{Call c=CALLS.get().pop();while(scope()!=null&&!scope().id.equals(c.frame)){emit("abort",new LinkedHashMap<>());STACK.get().pop();}Map r=call(c);r.put("exception",id(error));r.put("exception_type",error.getClass().getName());emit("source-call-throw",r);}catch(Throwable failure){problem("source-throw",failure);}}
    public static synchronized void target(Object result){if(scope()==null)return;try{List<Map> fields=new ArrayList<>();walk(result,"",null,null,fields,new IdentityHashMap<>(),false,null);Map r=new LinkedHashMap();r.put("result",id(result));r.put("fields",fields);emit("target",r);}catch(Throwable error){problem("target",error);}}
    static boolean scalar(Object x){return x==null||Arrays.asList(String.class,Long.class,Integer.class,Double.class,Float.class,Short.class,Byte.class,Boolean.class,Character.class,java.util.Date.class,java.sql.Timestamp.class,Class.class).contains(x.getClass());}
    static boolean targetPrefix(String path){String target=config.getProperty("target","*");if(target.equals("*"))return true;String[] a=path.split("/"),b=target.split("/");if(a.length>b.length)return false;for(int i=0;i<a.length;i++)if(!b[i].equals("*")&&!a[i].equals(b[i]))return false;return true;}
    static Tag fieldTag(Object owner,Field f,Object value)throws Exception {
        Class<?> t=f==null?null:f.getType();
        if(t==long.class)return Tainter.getTag(f.getLong(owner));if(t==int.class)return Tainter.getTag(f.getInt(owner));if(t==boolean.class)return Tainter.getTag(f.getBoolean(owner));
        if(t==double.class)return Tainter.getTag(f.getDouble(owner));if(t==float.class)return Tainter.getTag(f.getFloat(owner));if(t==short.class)return Tainter.getTag(f.getShort(owner));if(t==byte.class)return Tainter.getTag(f.getByte(owner));if(t==char.class)return Tainter.getTag(f.getChar(owner));return Tainter.getTag(value);
    }
    static Object marked(Object owner,Field f,Object value,Tag tag)throws Exception {
        Class<?> t=f==null?null:f.getType();
        if(t==long.class){f.setLong(owner,Tainter.setTag(f.getLong(owner),tag));return value;}if(t==int.class){f.setInt(owner,Tainter.setTag(f.getInt(owner),tag));return value;}
        if(t==boolean.class){f.setBoolean(owner,Tainter.setTag(f.getBoolean(owner),tag));return value;}if(t==double.class){f.setDouble(owner,Tainter.setTag(f.getDouble(owner),tag));return value;}
        if(t==float.class){f.setFloat(owner,Tainter.setTag(f.getFloat(owner),tag));return value;}if(t==short.class){f.setShort(owner,Tainter.setTag(f.getShort(owner),tag));return value;}
        if(t==byte.class){f.setByte(owner,Tainter.setTag(f.getByte(owner),tag));return value;}if(t==char.class){f.setChar(owner,Tainter.setTag(f.getChar(owner),tag));return value;}
        Object marked=Tainter.setTag(value,tag);if(f!=null)f.set(owner,marked);return marked;
    }
    static String esc(String s){return s.replace("~","~0").replace("/","~1");}
    static void walk(Object value,String path,Object parent,Field field,List<Map> fields,IdentityHashMap<Object,Boolean> active,boolean mark,Call source)throws Exception {
        if(source==null&&!targetPrefix(path))return;
        if(path.split("/").length>18||fields.size()>20000)throw new IllegalStateException("Boundary bound");
        if(scalar(value)) {
            if(parent==null)throw new IllegalStateException("Unowned scalar boundary");String key=field==null?(parent instanceof List?"@list:":"@map:")+path.substring(path.lastIndexOf('/')+1):field.getDeclaringClass().getName().replace('.','/')+"."+field.getName();
            String owner=id(parent);int version=VERSIONS.getOrDefault(owner+":"+key,0);String label=source==null?null:source.id+"/"+owner+"/"+key+"/"+version;
            if(mark){marked(parent,field,value,Tag.of(label));return;}
            Map f=new LinkedHashMap();f.put("path",path);f.put("owner",owner);f.put("field",key);f.put("version",version);
            if(value instanceof java.util.Date||value instanceof Class){f.put("opaque_reference",true);f.put("runtime_type",value.getClass().getName());if(value instanceof Class)f.put("class_name",((Class)value).getName());}else f.put("value",value instanceof Character?value.toString():value);f.put("value_object",id(value));
            if(source!=null)f.put("label",label);else{Tag tag=fieldTag(parent,field,value);f.put("labels",tag==null?Collections.emptyList():Arrays.asList(tag.getLabels()));}fields.add(f);return;
        }
        if(active.put(value,true)!=null)throw new IllegalStateException("Boundary cycle");
        try {
            if(value instanceof List){if(!Arrays.asList("java.util.ArrayList","java.util.Collections$EmptyList","java.util.Arrays$ArrayList").contains(value.getClass().getName()))throw new IllegalStateException("Unsupported list class");int n=((List)value).size();for(int i=0;i<n;i++){Object item=((List)value).get(i);if(mark&&scalar(item)){String key="@list:"+i;String label=source.id+"/"+id(value)+"/"+key+"/"+VERSIONS.getOrDefault(id(value)+":"+key,0);((List)value).set(i,Tainter.setTag(item,Tag.of(label)));}else walk(item,path+"/"+i,value,null,fields,active,mark,source);}if(n!=((List)value).size())throw new IllegalStateException("List changed during observation");return;}
            if(value instanceof Map){if(value.getClass()!=HashMap.class&&value.getClass()!=LinkedHashMap.class)throw new IllegalStateException("Unsupported map class");for(Object raw:((Map)value).entrySet()){Map.Entry e=(Map.Entry)raw;if(!(e.getKey()instanceof String))throw new IllegalStateException("Non-string key");String next=path+"/"+esc((String)e.getKey());Object v=e.getValue();if(mark&&scalar(v)){String key="@map:"+esc((String)e.getKey());String label=source.id+"/"+id(value)+"/"+key+"/"+VERSIONS.getOrDefault(id(value)+":"+key,0);e.setValue(Tainter.setTag(v,Tag.of(label)));}else walk(v,next,value,null,fields,active,mark,source);}return;}
            if(!value.getClass().getName().replace('.','/').startsWith(config.getProperty("prefix")))throw new IllegalStateException("Unsupported DTO type "+value.getClass().getName());
            for(Class<?> cls=value.getClass();cls!=Object.class;cls=cls.getSuperclass())for(Field f:cls.getDeclaredFields()){if(Modifier.isStatic(f.getModifiers())||f.isSynthetic())continue;f.setAccessible(true);walk(f.get(value),path+"/"+esc(f.getName()),value,f,fields,active,mark,source);}
        }finally{active.remove(value);}
    }
    static void problem(String where,Throwable error){invalid=true;Map r=new LinkedHashMap();r.put("where",where);r.put("exception",error.getClass().getName());r.put("detail",error.getMessage());List<String> stack=new ArrayList<>();for(StackTraceElement f:error.getStackTrace())stack.add(f.toString());r.put("stack",stack);emit("problem",r);}
    static synchronized void emit(String kind,Map row){try{Scope s=scope();row.put("kind",kind);row.put("seq",++seq);row.put("thread",Thread.currentThread().getId());row.put("frame",s==null?null:s.id);row.put("root",s==null?null:s.root);row.put("message",s==null?null:s.message);output.write(json(row));output.newLine();output.flush();}catch(Exception error){invalid=true;try{Files.write(Paths.get(System.getProperty("galette.boundary.events")+".invalid"),error.getClass().getName().getBytes("UTF-8"),StandardOpenOption.CREATE,StandardOpenOption.APPEND);}catch(Exception ignored){}}}
    static String json(Object value){if(value==null)return "null";if(value instanceof String){String s=(String)value;return "\""+s.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\r","\\r").replace("\t","\\t")+"\"";}if(value instanceof Boolean||value instanceof Number)return value.toString();StringBuilder b=new StringBuilder();if(value instanceof Map){b.append('{');boolean first=true;for(Object raw:((Map)value).entrySet()){Map.Entry e=(Map.Entry)raw;if(!first)b.append(',');first=false;b.append(json(e.getKey())).append(':').append(json(e.getValue()));}return b.append('}').toString();}if(value instanceof List){b.append('[');boolean first=true;for(Object x:(List)value){if(!first)b.append(',');first=false;b.append(json(x));}return b.append(']').toString();}throw new IllegalArgumentException("Non-metadata JSON value");}
}
