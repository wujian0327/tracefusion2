import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Literal declared types; equal wrapper values deliberately have different identities. */
public class MethodObservationFixture {
    public static class Datum {public int value;public Datum(int v){value=v;}public int getValue(){return value;}}
    public static class Store {public Datum read(){return new Datum(1000000);}}
    public static class Out {public int value;public Out(int v){value=v;}public int getValue(){return value;}}
    public static class Pack {public int i;public long j;public double d;public Object ref;public Pack(int x,long y,double z,Object r){i=x;j=y;d=z;ref=r;}}
    public boolean z(boolean x){return x;} public static byte b(byte x){return x;}
    public char c(char x){return x;} public static short s(short x){return x;}
    public int i(int x){return x;} public static long j(long x){return x;}
    public float f(float x){return x;} public static double d(double x){return x;}
    public Integer integer(Integer x){return x;} public static Long longer(Long x){return x;}
    public Object object(Object x){return x;} public void empty(int x,long y,double z){}
    public int mixed(boolean a,byte b,char c,short d,int e,long f,float g,double h,Integer i,Long j,Object k){return e;}
    public void failure(int unused,long wide,double negative,RuntimeException error){throw error;}
    public void probe(Integer one,Integer two,Long left,Long right,Object ordinary){
        z(true);b((byte)-120);c('\u2000');s((short)30000);i(1000000);long wide=j(9000000000000000000L);f(-0.0f);double nan=d(Double.NaN);double negative=d(-0.0d);
        integer(one);integer(two);longer(left);longer(right);object(one);object(ordinary);object(null);empty(1000000,9000000000000000000L,-0.0d);
        mixed(true,(byte)-120,'\u2000',(short)30000,1000000,9000000000000000000L,Float.NaN,-0.0d,one,left,ordinary);
    }
    public Out root(Store store,Integer one,Integer two,Long left,Long right,Object ordinary,RuntimeException error){
        Datum data=store.read();probe(one,two,left,right,ordinary);
        int primitive=data.value;java.util.function.Predicate<Object> byValue=x->primitive>0;java.util.function.Predicate<Object> byIdentity=x->x==one;
        Pack p=new Pack(data.value,9000000000000000000L,-0.0d,one);
        try{failure(1000000,9000000000000000000L,-0.0d,error);}catch(RuntimeException original){if(original!=error)throw new AssertionError();}
        return new Out(i(p.i));
    }
    static Map count(int phase){Map r=new LinkedHashMap();r.put("phase",phase);r.put("IDS",PlannedServiceAgent.Recorder.IDS.size());r.put("VERSIONS",PlannedServiceAgent.Recorder.VERSIONS.size());return r;}
    public static void main(String[] args)throws Exception{
        MethodObservationFixture f=new MethodObservationFixture();Integer one=new Integer(1000000),two=new Integer(1000000);Long left=new Long(9000000000000000000L),right=new Long(9000000000000000000L);Object ordinary=new Object();RuntimeException error=new RuntimeException("preallocated");ObjectMapper json=new ObjectMapper();
        if(one==two||left==right||!one.equals(two)||!left.equals(right))throw new AssertionError();
        if(args.length>0&&args[0].equals("stress")){List counts=new ArrayList();f.probe(one,two,left,right,ordinary);counts.add(count(0));for(int phase=1;phase<=2;phase++){for(int n=0;n<200;n++)f.probe(one,two,left,right,ordinary);counts.add(count(phase));}System.out.println(json.writeValueAsString(counts));return;}
        double payload=Double.longBitsToDouble(0x7ff8000000000017L);float singlePayload=Float.intBitsToFloat(0x7fc00017);
        if(Double.doubleToRawLongBits(d(payload))!=0x7ff8000000000017L||Float.floatToRawIntBits(f.f(singlePayload))!=0x7fc00017)throw new AssertionError("NaN payload changed");
        W3CTraceContext ctx=W3CTraceContext.server(null,null);boolean observe=Boolean.getBoolean("fixture.observe");if(observe)SpringTransportAgent.Transport.ASYNC.set(ctx);
        Out out=f.root(new Store(),one,two,left,right,ordinary,error);if(out.value!=1000000)throw new AssertionError();
        if(observe){ResponseBindingHooks.verifySerialization(out,json);Map wire=ctx.fields();wire.put("uri",null);wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(out));PlannedServiceAgent.Recorder.emit("http-json",wire);}
        System.out.println(json.writeValueAsString(out));
    }
}
