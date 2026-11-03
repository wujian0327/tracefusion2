import java.util.*;
public class MapWrapperFixture {
    public static class DTO {private String text;public DTO(String x){text=x;}public String getText(){return text;}}
    public static class Wrapper extends HashMap<String,Object>{public Wrapper with(String k,Object v){put(k,v);return this;}}
    public static class Child extends Wrapper {}
    public static class BadGet extends Wrapper {static int hits;public Object get(Object k){hits++;throw new IllegalArgumentException("get must not run");}}
    public static class BadKeys extends Wrapper {static int hits;public Set<String> keySet(){hits++;throw new IllegalArgumentException("keys must not run");}}
    public static class Stateful extends Wrapper {Object hidden=new Object();}
    static final IllegalArgumentException ERROR=new IllegalArgumentException("business");
    static int finished;
    public static Wrapper root(int kind){return perform(kind);}
    public static Wrapper perform(int kind){try{
        if(kind==5)throw ERROR;
        Wrapper w=kind==2?new BadGet():kind==3?new BadKeys():kind==4?new Stateful():kind==1?new Child():new Wrapper();
        w.put("data",new DTO(kind==1?null:"same"));w.put("nested",Arrays.asList(new DTO("same"),new DTO("same"),null));w.put("nil",null);return w;
    }finally{finished++;}}
    static String content(Object v){if(v==null)return "null";if(v instanceof DTO)return "{\"text\":"+content(((DTO)v).text)+"}";
        if(v instanceof Map){StringJoiner s=new StringJoiner(",","{","}");for(Map.Entry<?,?> e:((Map<?,?>)v).entrySet())s.add(content(e.getKey())+":"+content(e.getValue()));return s.toString();}
        if(v instanceof List){StringJoiner s=new StringJoiner(",","[","]");for(Object x:(List<?>)v)s.add(content(x));return s.toString();}return "\""+(String)v+"\"";}
    public static void main(String[] args){int kind=Integer.parseInt(args[0]);boolean exact=false;Wrapper r=null;try{r=root(kind);}catch(IllegalArgumentException e){exact=e==ERROR;}
        System.out.println("{\"content\":"+content(r)+",\"normal\":"+(r!=null)+",\"same_exception\":"+exact+",\"finally\":"+finished+",\"get_hits\":"+BadGet.hits+",\"key_hits\":"+BadKeys.hits+"}");}
}
