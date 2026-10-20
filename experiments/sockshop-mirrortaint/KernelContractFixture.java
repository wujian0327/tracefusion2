import java.util.*;
import java.util.function.Supplier;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Independent semantic cases; expected sources are defined in the driver. */
public class KernelContractFixture {
    public static class Item {
        public String text; public Item(String text){this.text=text;}
        public String getText(){return text;} public void setText(String text){this.text=text;}
        public Supplier<String> supplier(){return ()->text;}
    }
    static String at(String[] xs,int index){return xs[index];}
    static Item copy(Item x){return new Item(x.text);}
    static Item pick(Item left,Item right){return copy(right);}
    static String[] relay(String[] xs){return xs;}
    static String[] opaqueArray(String[] xs){int[] unsupported=new int[1];return xs;}
    static Item opaque(Item x){int[] unsupported=new int[1];return x;}
    public static Item root(Item left,Item right,int mode){
        if(mode==0){String[] xs=new String[1];return new Item(xs[0]);}
        if(mode==1){String[] xs=new String[1];xs[0]=left.text;xs[0]=right.text;return new Item(xs[0]);}
        if(mode==2){String[] xs=new String[2];xs[0]=left.text;xs[1]=right.text;return new Item(xs[1]);}
        if(mode==3){String[] xs=new String[2];xs[1]=right.text;return new Item(at(xs,1));}
        if(mode==4){try{String[] xs=new String[0];return new Item(xs[0]);}catch(ArrayIndexOutOfBoundsException e){return copy(right);}}
        if(mode==5){try{String[] xs=null;return new Item(xs[0]);}catch(NullPointerException e){return copy(right);}}
        if(mode==6){try{Object[] xs=new String[1];xs[0]=left;return copy(left);}catch(ArrayStoreException e){return copy(right);}}
        if(mode==7){try{String[] xs=new String[-1];return copy(left);}catch(NegativeArraySizeException e){return copy(right);}}
        if(mode==8){List<Item> xs=new ArrayList<>();xs.add(left);return xs.stream().findFirst().orElseGet(()->opaque(right));}
        if(mode==9){List<Item> xs=new ArrayList<>();return xs.stream().findFirst().orElseGet(()->right);}
        if(mode==10){Supplier<Item> f=()->pick(left,right);return f.get();}
        if(mode==11){try{Supplier<Item> f=()->copy(null);return f.get();}catch(NullPointerException e){return copy(left);}}
        if(mode==12){String[] xs=new String[1];xs[0]=opaque(left).text;return new Item(xs[0]);}
        if(mode==13)return copy(left);
        if(mode==14){String[] xs=new String[0];return new Item(xs[2]);}
        if(mode==16){Supplier<Item> a=()->left,b=()->right;return b.get();}
        if(mode==17){String[] xs=new String[1];xs[0]=left.text;xs[0]="SAME";return new Item(xs[0]);}
        if(mode==18){String[] xs=new String[1];xs[0]=left.text;opaqueArray(xs);return new Item(xs[0]);}
        if(mode==19){String[] xs=new String[2];xs[0]=left.text;xs[1]=right.text;return new Item(relay(xs)[1]);}
        if(mode==20){Supplier<String> f=left::getText;return new Item(f.get());}
        if(mode==21)return new Item(right.supplier().get());
        if(mode==22){Item local=copy(left);Supplier<Item> f=()->{int[] unsupported=new int[1];return local;};f.get();return local;}
        String[] xs=new String[2];if(xs.length==2)return copy(right);return copy(left);
    }
    public static void main(String[] args)throws Exception{
        Item left=new Item("SAME"),right=new Item("SAME");ObjectMapper json=new ObjectMapper();List<Map> cases=new ArrayList<>();
        for(int i=0;i<46;i++){
            int mode=i%23;W3CTraceContext c=W3CTraceContext.server("00-33333333333333333333333333333333-"+String.format("%016x",i+1)+"-01","fixture=contracts");SpringTransportAgent.Transport.ASYNC.set(c);
            Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",c.fields().get("message"));
            try{Item result=root(left,right,mode);ResponseBindingHooks.verifySerialization(result,json);row.put("response",json.readValue(json.writeValueAsString(result),Map.class));row.put("status","normal");Map wire=c.fields();wire.put("uri","fixture:contracts");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}}
            catch(ArrayIndexOutOfBoundsException expected){row.put("status","aborted");}cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();
        }System.out.println(json.writeValueAsString(cases));
    }
}
