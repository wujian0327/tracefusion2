import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Independent arithmetic cases: operands remain sources even when result is zero. */
public class NumericKernelFixture {
    public static class Input {public int count;public double rate;Input(int c,double r){count=c;rate=r;}}
    public static class Result {public double value;}
    public static Result root(Input a,Input b){Result r=new Result();r.value=(double)a.count*b.rate;return r;}
    public static void main(String[] args)throws Exception{
        ObjectMapper json=new ObjectMapper();List<Map> cases=new ArrayList<>();
        int[] counts={0,1,-1,Integer.MIN_VALUE,Integer.MAX_VALUE,3,3};double[] rates={2.5,0,-2.5,0.5,0.25,1.25,1.25};
        for(int i=0;i<counts.length;i++){
            Input a=new Input(counts[i],rates[i]),b=new Input(counts[i],rates[i]);
            W3CTraceContext c=W3CTraceContext.server("00-44444444444444444444444444444444-"+String.format("%016x",i+1)+"-01","fixture=numeric");SpringTransportAgent.Transport.ASYNC.set(c);
            Result result=root(a,b);ResponseBindingHooks.verifySerialization(result,json);Map row=new LinkedHashMap();row.put("message",c.fields().get("message"));row.put("expected",((double)counts[i])*rates[i]);row.put("response",result.value);cases.add(row);
            Map wire=c.fields();wire.put("uri","fixture:numeric");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}SpringTransportAgent.Transport.ASYNC.remove();
        }System.out.println(json.writeValueAsString(cases));
    }
}
