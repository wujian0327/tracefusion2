import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Literal rewrites and composition tests. Keys identify actual source calls, not values. */
public class PublicControlFixture {
    public static class Datum {
        public int value; public String nullable;
        public Datum(int value){this.value=value;this.nullable=null;}
        public int getValue(){return value;} public String getNullable(){return nullable;}
    }
    public static class Store {public Datum read(int key,int value){Datum d=new Datum(value);if(key==30&&value>0)d.nullable="SAME";return d;}}
    public static class Out {
        public int value;
        public Out(int value){this.value=value;}
        public int getValue(){return value;}
    }
    public boolean direct(Datum g){return g.value>0;}
    public boolean local(Datum g){boolean answer=g.value>0;return answer;}
    public int identity(int value){return value;}
    public void assign(Out out,int value){out.value=value;}
    public int recursive(int n,int value){if(n==0)return value;return recursive(n-1,value);}
    public void throwOriginal(Datum g,IllegalArgumentException original){if(g.value>0)throw original;}
    public int length(Datum g){return g.nullable.length();}
    public void intermediate(Datum g){length(g);}
    public Out rootImplicit(Store store,int scenario,int input){
        Datum a=store.read(10,7),b=store.read(11,7),g=store.read(30,input);int result=a.value;
        try{if(scenario==2)intermediate(g);else if(scenario==3){String nil=null;nil.length();}else length(g);}
        catch(NullPointerException original){result=b.value;}
        if(scenario==1)result=9;
        return new Out(result);
    }
    public Out rootException(Store store,int scenario,int input,IllegalArgumentException original){
        Datum a=store.read(10,7),b=store.read(11,7),g=store.read(20,input);int result;
        if(scenario==0){try{if(g.value>0)throw original;result=a.value;}catch(IllegalArgumentException e){result=b.value;}}
        else if(scenario==1){try{if(g.value>0)throw original;result=a.value;}catch(IllegalArgumentException e){result=b.value;}finally{int scratch=3;}}
        else if(scenario==2){try{if(g.value>0)throw original;result=a.value;}catch(IllegalArgumentException e){result=b.value;}result=9;}
        else{try{throwOriginal(g,original);result=a.value;}catch(IllegalArgumentException e){result=b.value;}}
        return new Out(result);
    }
    public Out root(Store store,int scenario,int input){
        Datum a=store.read(10,7),b=store.read(11,7),g=store.read(20,input);
        int result;
        if(scenario==0)result=direct(g)?1:0;
        else if(scenario==1)result=local(g)?1:0;
        else if(scenario==2)result=g.value>0?a.value:b.value;
        else if(scenario==3){if(g.value>0){Datum h=store.read(21,1);if(h.value>0)result=a.value;else result=b.value;}else result=b.value;}
        else if(scenario==4){if(g.value>0&&store.read(21,1).value>0)result=a.value;else result=b.value;}
        else if(scenario==5){if(g.value>0||store.read(21,1).value>0)result=a.value;else result=b.value;}
        else if(scenario==6){result=a.value;for(int i=0;i<g.value;i++)result=result+b.value;}
        else if(scenario==7){result=a.value;if(g.value>0)result=b.value;}
        else if(scenario==8){Out out=new Out(a.value);Out alias=out;if(g.value>0)out.value=b.value;return new Out(alias.value);}
        else if(scenario==9){Out out=new Out(a.value);if(g.value>0)out.value=7;return out;}
        else if(scenario==10){result=direct(g)?a.value:b.value;}
        else if(scenario==11){if(g.value>0)result=identity(a.value);else result=identity(b.value);}
        else if(scenario==12){int scratch=0;if(g.value>0)scratch=b.value;result=a.value;}
        else if(scenario==13){int unused=g.value>0?a.value:b.value;result=9;}
        else if(scenario==14){try{if(g.value>0)throw new IllegalArgumentException("original");result=a.value;}catch(IllegalArgumentException e){result=b.value;}}
        else if(scenario==15){try{if(g.value>0)throw new IllegalArgumentException("original");result=a.value;}catch(IllegalArgumentException e){result=b.value;}result=9;}
        else if(scenario==16){try{if(g.value>0)throw new IllegalArgumentException("original");result=a.value;}catch(IllegalArgumentException e){result=b.value;}finally{int scratch=3;}}
        else if(scenario==17){Datum ref=g.value>0?null:a;try{result=ref.value;}catch(NullPointerException e){result=b.value;}}
        else if(scenario==18){result=recursive(g.value,a.value);}
        else if(scenario==19){Out out=new Out(a.value);if(g.value>0)assign(out,b.value);return new Out(out.value);}
        else if(scenario==20){result=g.nullable==null?a.value:b.value;}
        else result=a.value;
        return new Out(result);
    }
    public static void main(String[] args)throws Exception{
        boolean observe=Boolean.getBoolean("fixture.observe");
        ObjectMapper mapper=new ObjectMapper();PublicControlFixture fixture=new PublicControlFixture();List<Map> results=new ArrayList<>();
        boolean exceptionOnly=args.length>0&&args[0].equals("exception-controls");
        boolean implicitOnly=args.length>0&&args[0].equals("implicit-controls");
        IllegalArgumentException original=new IllegalArgumentException("original object");
        for(int scenario=0;scenario<=((exceptionOnly||implicitOnly)?3:21);scenario++)for(int input=0;input<=2;input++){
            W3CTraceContext ctx=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(ctx);
            Out value=implicitOnly?fixture.rootImplicit(new Store(),scenario,input):exceptionOnly?fixture.rootException(new Store(),scenario,input,original):fixture.root(new Store(),scenario,input);
            if(observe){ResponseBindingHooks.verifySerialization(value,mapper);Map wire=ctx.fields();wire.put("uri",null);wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(value));PlannedServiceAgent.Recorder.emit("http-json",wire);}
            Map row=new LinkedHashMap();row.put("scenario",scenario);row.put("input",input);row.put("value",value.value);row.put("message",ctx.message());results.add(row);
            if(observe)SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(mapper.writeValueAsString(results));
    }
}
