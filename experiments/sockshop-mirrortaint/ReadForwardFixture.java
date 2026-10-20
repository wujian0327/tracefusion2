import java.util.*;
import java.util.concurrent.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Semantic controls only; never substituted for an application JAR. */
public class ReadForwardFixture {
    public static class Item {public String text;public Item(String x){text=x;}public String getText(){return text;}public void setText(String x){text=x;}}
    public static Item first(List<Item> items){return items.stream().findFirst().orElseGet(()->new Item("SAME"));}
    public static Item forward(List<Item> left,List<Item> right,boolean choose){return first(choose?left:right);}
    public static Item repeated(List<Item> left,List<Item> right){first(left);return first(right);}
    public static Item reflected(Item value)throws Exception{value.getClass().getField("text").set(value,"SAME");return value;}
    public static Item opaque(Item value)throws Exception{return reflected(value);}
    public static CompletableFuture<Item> asyncWork(Item value){return CompletableFuture.supplyAsync(()->value);}
    public static Item async(Item value)throws Exception{return asyncWork(value).get();}
    public static Item overwritten(Item value){value.setText("SAME");return value;}
    static class MutatingBox {MutatingBox(Item value)throws Exception{value.getClass().getField("text").set(value,"SAME");}}
    public static Item constructor(Item value)throws Exception{new MutatingBox(value);return value;}
    static class OtherItem extends Item {OtherItem(String x){super(x);}public String getText(){return "SAME";}}
    static class OtherList extends ArrayList<Item>{OtherList(Item x){add(x);}}
    public static void main(String[] args)throws Exception{
        for(int i=0;i<6;i++){
            Item left=new Item("SAME"),right=new Item("SAME");List<Item> a=new ArrayList<>(Arrays.asList(left,new Item("SAME")));List<Item>b=new ArrayList<>(Arrays.asList(right,new Item("SAME")));
            W3CTraceContext context=W3CTraceContext.server("00-11111111111111111111111111111111-"+String.format("%016x",i+1)+"-01","fixture=read-effects");SpringTransportAgent.Transport.ASYNC.set(context);
            Item result;
            switch(args[0]){
                case "forward":result=forward(a,b,i%2==0);break;
                case "repeated":result=repeated(a,b);break;
                case "overlap":result=forward(a,a,true);break;
                case "empty":result=forward(new ArrayList<Item>(),b,true);break;
                case "custom-list":result=forward(new OtherList(left),b,true);break;
                case "opaque":result=opaque(left);break;
                case "async":result=async(left);break;
                case "overwritten":result=overwritten(left);break;
                case "constructor":result=constructor(left);break;
                default:throw new IllegalArgumentException(args[0]);
            }
            ObjectMapper mapper=new ObjectMapper();ResponseBindingHooks.verifySerialization(result,mapper);System.out.println(mapper.writeValueAsString(result));
            Map row=context.fields();row.put("uri","fixture:actual-jackson");row.put("phase","write");row.put("direction","response");row.put("fields",SpringTransportAgent.Transport.snapshot(result));
            synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",row);}
            SpringTransportAgent.Transport.ASYNC.remove();
        }
    }
}
