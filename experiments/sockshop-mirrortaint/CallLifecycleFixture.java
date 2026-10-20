import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Real bytecode/exception-table controls, not application coverage evidence. */
public class CallLifecycleFixture {
    public static class Item {public String text;public Item(String x){text=x;}public String getText(){return text;}}
    interface Worker {Item work();}
    static int bodies,cleanups;
    static final RuntimeException ERROR=new IllegalArgumentException("original-exception");
    static Item identity(Item value){return value;}
    static Item boom(){bodies++;throw ERROR;}
    static Item nested(){try{return boom();}catch(IllegalArgumentException e){throw e;}finally{cleanups++;}}
    static Item computed(Item value){return new Item(value.getText());}
    static Item exercise(Item value,int mode){
        if(mode==9)Runtime.getRuntime().halt(0);
        if(mode==1){try{return boom();}catch(IllegalArgumentException e){if(e!=ERROR)throw new AssertionError();return value;}}
        if(mode==2)return nested();
        if(mode==3){try{Worker missing=null;return missing.work();}catch(NullPointerException e){return value;}}
        if(mode==4){try{return nested();}catch(IllegalArgumentException e){if(e!=ERROR)throw new AssertionError();return value;}finally{cleanups++;}}
        return value;
    }
    public static Item root(Item value,int mode){
        if(mode==0)return identity(value);
        if(mode==7)return computed(value);
        return exercise(value,mode);
    }
    public static void main(String[] args)throws Exception{
        if(args.length>0&&args[0].equals("halt")){root(new Item("SAME"),9);throw new AssertionError("halt returned");}
        int[] modes={0,1,0,2,0,3,0,4,0,7,0,2,0};
        List<Map> results=new ArrayList<>();
        for(int i=0;i<modes.length;i++){
            Item input=new Item("SAME");int mode=modes[i],oldBodies=bodies,oldCleanups=cleanups;
            W3CTraceContext ctx=W3CTraceContext.server("00-11111111111111111111111111111111-"+String.format("%016x",i+1)+"-01","fixture=lifecycle");SpringTransportAgent.Transport.ASYNC.set(ctx);
            Map result=new LinkedHashMap();result.put("index",i);result.put("mode",mode);result.put("message",ctx.fields().get("message"));
            try{
                Item output=root(input,mode);if(mode==2)throw new AssertionError("Exception swallowed");
                if(mode==7?(output==input||!output.text.equals(input.text)):output!=input)throw new AssertionError("Business return changed");
                ObjectMapper mapper=new ObjectMapper();ResponseBindingHooks.verifySerialization(output,mapper);mapper.writeValueAsString(output);
                Map row=ctx.fields();row.put("uri","fixture:lifecycle");row.put("phase","write");row.put("direction","response");row.put("fields",SpringTransportAgent.Transport.snapshot(output));
                synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",row);}
                result.put("status","returned");
            }catch(RuntimeException error){if(mode!=2||error!=ERROR)throw new AssertionError("Business exception changed",error);result.put("status","aborted");}
            result.put("body_entries",bodies-oldBodies);result.put("cleanups",cleanups-oldCleanups);
            if(mode==3&&bodies!=oldBodies)throw new AssertionError("Null invoke entered callee");
            if((mode==2&&cleanups-oldCleanups!=1)||(mode==4&&cleanups-oldCleanups!=2))throw new AssertionError("Finally changed");
            results.add(result);SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(new ObjectMapper().writeValueAsString(results));
    }
}
