import java.util.*;
import java.util.concurrent.*;
import java.nio.file.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Workload/oracle belong to the runner, not the planner or collector. */
public final class QueryPlannerFixture {
    public static final class Source { public int quantity;public float unitPrice;public String name;public String publicValue; }
    public static final class Orders { public float total; }
    public static final class Shipment { public String name; }
    public static final class Noise { public int marker;public String payload; }
    public static final class Gate {
        static final ThreadLocal<Boolean> PICK=new ThreadLocal<>(),NOISE=new ThreadLocal<>();
        public static boolean pick(){return PICK.get().booleanValue();}
        public static boolean noise(){return NOISE.get().booleanValue();}
    }
    public static final class Helpers {
        public static float calculate(int quantity,float price){return quantity*price+4.99f;}
        public static String copy(String name){return name;}
        public static void assign(Shipment shipment,String name){shipment.name=copy(name);}
    }
    public static void process(Source a,Source b,Orders orders,Shipment shipment,Noise noise) {
        int quantity;
        if(Gate.pick())quantity=a.quantity;else quantity=b.quantity;
        orders.total=0;
        orders.total=Helpers.calculate(quantity,a.unitPrice);
        shipment.name=b.name;
        Helpers.assign(shipment,a.name);
        if(Gate.noise())noise.payload=a.publicValue;else noise.payload=b.publicValue;
        noise.marker=a.quantity+b.quantity;
        // EXTRA_WORK: generated variants insert irrelevant field work here.
    }
    public static void main(String[] args) throws Exception {
        ObjectMapper json=new ObjectMapper();List<Map<String,Object>> cases=json.readValue(Paths.get(args[0]).toFile(),List.class);
        List<Map<String,Object>> results=Collections.synchronizedList(new ArrayList<>());
        ExecutorService pool=Executors.newFixedThreadPool(12);List<Future<?>> futures=new ArrayList<>();
        // Reuse these objects for the explicit two-call version test.
        Source repeatedA=new Source(),repeatedB=new Source();Orders repeatedOrders=new Orders();Shipment repeatedShipment=new Shipment();Noise repeatedNoise=new Noise();
        for(Map<String,Object> c:cases) {
            Runnable task=()->{
                try {
                    Thread.currentThread().setName(String.valueOf(c.get("id")));
                    boolean repeat=String.valueOf(c.get("id")).startsWith("repeat-");
                    Source a=repeat?repeatedA:new Source(),b=repeat?repeatedB:new Source();
                    a.quantity=((Number)c.get("aq")).intValue();b.quantity=((Number)c.get("bq")).intValue();a.unitPrice=((Number)c.get("price")).floatValue();b.unitPrice=a.unitPrice;
                    a.name=String.valueOf(c.get("an"));b.name=String.valueOf(c.get("bn"));a.publicValue=String.valueOf(c.get("ap"));b.publicValue=String.valueOf(c.get("bp"));
                    if(Boolean.TRUE.equals(c.get("alias")))b=a;
                    Orders orders=repeat?repeatedOrders:new Orders();Shipment shipment=repeat?repeatedShipment:new Shipment();Noise noise=repeat?repeatedNoise:new Noise();
                    Gate.PICK.set((Boolean)c.get("pick"));Gate.NOISE.set((Boolean)c.get("noise"));
                    process(a,b,orders,shipment,noise);
                    Map<String,Object> r=new LinkedHashMap<>();r.put("id",c.get("id"));r.put("total",orders.total);r.put("name",shipment.name);r.put("payload",noise.payload);r.put("marker",noise.marker);results.add(r);
                }catch(Exception error){throw new IllegalStateException(error);}
            };
            if(String.valueOf(c.get("id")).startsWith("parallel-"))futures.add(pool.submit(task));else task.run();
        }
        for(Future<?> future:futures)future.get();pool.shutdown();
        json.writerWithDefaultPrettyPrinter().writeValue(Paths.get(args[1]).toFile(),results);
    }
}
