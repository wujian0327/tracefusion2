import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

public class PrimitiveObservationFixture {
    public static class Datum {
        public int big; public long wide; public double number; public float small;
        public boolean truth; public char letter; public byte signed; public short narrow;
        public Integer boxed; public Long boxedLong; public Object ref; public Integer absent;
        public int getBig(){return big;} public Integer getBoxed(){return boxed;} public Integer getAbsent(){return absent;}
    }
    public static class Store {public Datum read(){Datum d=new Datum();d.big=1000000;d.boxed=new Integer(1000000);return d;}}
    public static class Out {public int big;public Integer boxed;public Integer absent;public int getBig(){return big;}public Integer getBoxed(){return boxed;}public Integer getAbsent(){return absent;}}
    static int integerSink;static long longSink;static double doubleSink;static float floatSink;static boolean booleanSink;static char charSink;static byte byteSink;static short shortSink;static Object referenceSink;
    public void scan(Datum d){integerSink=d.big;longSink=d.wide;doubleSink=d.number;floatSink=d.small;booleanSink=d.truth;charSink=d.letter;byteSink=d.signed;shortSink=d.narrow;referenceSink=d.boxed;referenceSink=d.boxedLong;referenceSink=d.ref;referenceSink=d.absent;}
    public Out root(Store s){Datum d=s.read();Out o=new Out();o.big=d.big;o.boxed=d.boxed;o.absent=d.absent;return o;}
    static Map counts(int phase){Map r=new LinkedHashMap();r.put("phase",phase);r.put("IDS",PlannedServiceAgent.Recorder.IDS.size());r.put("VERSIONS",PlannedServiceAgent.Recorder.VERSIONS.size());r.put("ACTIVE",PlannedServiceAgent.Recorder.ACTIVE.size());r.put("CHECKED_CLASSES",PlannedServiceAgent.Recorder.CHECKED_CLASSES.size());r.put("LIBRARY_HASHES",ExecutionKernelHooks.LIBRARY_HASHES.size());r.put("ARRAY_VERSIONS",ExecutionKernelHooks.ARRAY_VERSIONS.size());r.put("ARRAY_SLOTS",ExecutionKernelHooks.ARRAY_SLOTS.size());r.put("INITIALIZED",ExecutionKernelHooks.INITIALIZED.size());return r;}
    public static void main(String[] args)throws Exception{
        PrimitiveObservationFixture f=new PrimitiveObservationFixture();Datum d=new Datum();d.big=1000000;d.wide=9000000000000000000L;d.number=1000000.25;d.small=1000000.5f;d.truth=true;d.letter='\u2000';d.signed=-120;d.narrow=30000;d.boxed=new Integer(1000000);d.boxedLong=new Long(9000000000000000000L);d.ref=new Object();
        ObjectMapper json=new ObjectMapper();
        if(args.length>0&&args[0].equals("stress")){
            List stats=new ArrayList();f.scan(d);PlannedServiceAgent.Recorder.id(d.boxed);PlannedServiceAgent.Recorder.id(d.boxedLong);PlannedServiceAgent.Recorder.id(d.ref);stats.add(counts(0));
            for(int phase=1;phase<=2;phase++){for(int i=0;i<1000;i++)f.scan(d);stats.add(counts(phase));}
            Map r=new LinkedHashMap();r.put("observations_per_phase",1000);r.put("stats",stats);r.put("boxed",PlannedServiceAgent.Recorder.id(d.boxed));r.put("boxedLong",PlannedServiceAgent.Recorder.id(d.boxedLong));r.put("ref",PlannedServiceAgent.Recorder.id(d.ref));System.out.println(json.writeValueAsString(r));return;
        }
        W3CTraceContext ctx=W3CTraceContext.server(null,null);boolean observe=Boolean.getBoolean("fixture.observe");if(observe)SpringTransportAgent.Transport.ASYNC.set(ctx);Out result=f.root(new Store());
        if(observe){ResponseBindingHooks.verifySerialization(result,json);Map wire=ctx.fields();wire.put("uri",null);wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));PlannedServiceAgent.Recorder.emit("http-json",wire);}
        System.out.println(json.writeValueAsString(result));
    }
}
