import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Completion conditions versus payloads; source truth is specified outside TF. */
public class ExceptionCompletionFixture {
    public static class Datum {public int value;public String nullable;public Datum(int v){value=v;}public int getValue(){return value;}public String getNullable(){return nullable;}}
    public static class Store {public Datum read(int key,int v){Datum d=new Datum(v);if(key==30&&v>0)d.nullable="SAME";return d;}}
    public static class Out {public int value;public Out(int v){value=v;}public int getValue(){return value;}}
    public void writeThenThrow(Datum d,int payload,int gate,IllegalArgumentException original){d.value=payload;if(gate>0)throw original;}
    public void testOnly(int payload,int gate,IllegalArgumentException original){if(gate>0)throw original;}
    public int compute(int payload,int gate,IllegalArgumentException original){if(gate>0)throw original;return payload;}
    public void middle(Datum d,int payload,int gate,IllegalArgumentException original){writeThenThrow(d,payload,gate,original);}
    public void nullable(Datum d,int payload,String text){d.value=payload;text.length();}
    public void field(Datum d,Datum maybe,int payload){d.value=payload;int ignored=maybe.value;}
    public void put(Datum maybe,int payload){maybe.value=payload;}
    public Object load(Object[] values,int index,int unused){return values[index];}
    public void store(Object[] values,int index,Object payload){values[index]=payload;}
    public void recursive(Datum d,int payload,int gate,int depth,IllegalArgumentException original){if(depth>0)recursive(d,payload,gate,depth-1,original);else writeThenThrow(d,payload,gate,original);}
    public Out root(Store store,int scenario,int input,IllegalArgumentException original){
        Datum a=store.read(10,7),b=store.read(11,7),g=store.read(20,input);int result;
        if(scenario==0){try{writeThenThrow(a,b.value,g.value,original);result=a.value;}catch(IllegalArgumentException e){result=b.value;}}
        else if(scenario==1){try{testOnly(b.value,g.value,original);result=a.value;}catch(IllegalArgumentException e){result=b.value;}}
        else if(scenario==2){try{result=compute(a.value,g.value,original);}catch(IllegalArgumentException e){result=b.value;}}
        else if(scenario==3){try{middle(a,b.value,g.value,original);result=a.value;}catch(IllegalArgumentException e){result=b.value;}}
        else if(scenario==4){Datum text=store.read(30,input);try{nullable(a,b.value,text.nullable);result=a.value;}catch(NullPointerException e){result=b.value;}}
        else if(scenario==5){Datum maybe=g.value>0?a:null;try{field(a,maybe,b.value);result=a.value;}catch(NullPointerException e){result=b.value;}}
        else if(scenario==6){Datum maybe=g.value>0?a:null;try{put(maybe,b.value);result=a.value;}catch(NullPointerException e){result=a.value;}}
        else if(scenario==7){Object[] values=new Object[1];values[0]=a;try{load(values,g.value,b.value);result=a.value;}catch(ArrayIndexOutOfBoundsException e){result=b.value;}}
        else if(scenario==8){Object[] values=new Object[1];try{store(values,g.value,b.nullable);result=a.value;}catch(ArrayIndexOutOfBoundsException e){result=b.value;}}
        else if(scenario==9){Object[] values=g.value>0?new Object[1]:null;Datum index=store.read(21,0);try{store(values,index.value,b.nullable);result=a.value;}catch(NullPointerException e){result=b.value;}}
        else if(scenario==10){try{if(g.value>0)throw original;result=a.value;}catch(IllegalArgumentException e){result=b.value;}}
        else if(scenario==11){try{writeThenThrow(a,b.value,g.value,original);result=a.value;}catch(IllegalArgumentException e){result=b.value;}finally{int scratch=3;}result=9;}
        else if(scenario==12){try{recursive(a,b.value,g.value,2,original);result=a.value;}catch(IllegalArgumentException e){result=b.value;}}
        else if(scenario==14){Object payload=g.value>0?store:"TEXT";String[] values=new String[1];try{store(values,0,payload);result=a.value;}catch(ArrayStoreException e){result=b.value;}}
        else result=a.value;
        return new Out(result);
    }
    public static void main(String[] args)throws Exception{
        boolean observe=Boolean.getBoolean("fixture.observe");ObjectMapper mapper=new ObjectMapper();ExceptionCompletionFixture f=new ExceptionCompletionFixture();List<Map> all=new ArrayList<>();IllegalArgumentException original=new IllegalArgumentException("original");
        for(int s=0;s<15;s++)for(int n=0;n<2;n++){
            if(args.length>0){if(args[0].equals("supported")){if(s==6)continue;}else if(s!=Integer.parseInt(args[0]))continue;}
            W3CTraceContext ctx=W3CTraceContext.server(null,null);if(observe)SpringTransportAgent.Transport.ASYNC.set(ctx);
            Out result=f.root(new Store(),s,n,original);
            if(observe){ResponseBindingHooks.verifySerialization(result,mapper);Map wire=ctx.fields();wire.put("uri",null);wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));PlannedServiceAgent.Recorder.emit("http-json",wire);}
            Map row=new LinkedHashMap();row.put("scenario",s);row.put("input",n);row.put("value",result.value);row.put("message",ctx.message());all.add(row);if(observe)SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(mapper.writeValueAsString(all));
    }
}
