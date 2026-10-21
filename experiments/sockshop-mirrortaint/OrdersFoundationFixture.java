import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Inputs and literal oracle cases only; no provenance propagation. */
public class OrdersFoundationFixture {
    public static String STATIC_TEXT="SAME";
    public static Item GLOBAL;
    public static class External {public static final String VALUE=populate();}
    static String populate(){touch(GLOBAL);return "SAME";}
    public static class Item {public String text;public Item(String text){this.text=text;}public String getText(){return text;}public void setText(String text){this.text=text;}}
    public static class Out {public String text;public Out(String text){this.text=text;}public String getText(){return text;}}
    public class Inner {public String text;public Inner(String text){this.text=text;}public String getText(){return text;}}
    static void touch(Item x){x.setText("SAME");}
    public static class Base {public Base(Item x,boolean fail){int[] notModeled=new int[1];touch(x);if(fail)throw new IllegalArgumentException("expected");}}
    public static class Mutator extends Base {public Mutator(Item x){super(x,false);}}
    public static class Throwing extends Base {public Throwing(Item x){super(x,true);}}
    public static class Parent {public Parent(){}}
    public static class Token extends Parent {public Token(){super();}}
    public static class View {public Item item;public View(Item x){item=x;}public String toString(){return new StringBuilder().append('[').append(item.getText()).append(']').toString();}}
    public static class ChangingView {public Item item;public ChangingView(Item x){item=x;}public String toString(){item.setText("SAME");return item.getText();}}
    public static class OpaqueView {public Item item;public OpaqueView(Item x){item=x;}public String toString(){int[] notModeled=new int[1];return item.getText();}}
    static void opaque(Object x){int[] notModeled=new int[1];}
    public static Out root(Item left,Item right,int mode){
        if(mode==0)return new Out(new StringBuilder().append(left.getText()).append('-').append(right.getText()).toString());
        if(mode==1)return new Out(new StringBuilder().append(new View(left)).toString());
        if(mode==2){new Mutator(left);return new Out(left.getText());}
        if(mode==3){String saved=left.getText();new Mutator(left);return new Out(saved);}
        if(mode==4){try{new Throwing(left);}catch(IllegalArgumentException e){return new Out("fallback");}}
        if(mode==5){new Token();return new Out("constant");}
        if(mode==6)return new Out(STATIC_TEXT);
        if(mode==7){StringBuilder b=new StringBuilder();opaque(b);return new Out(b.append(left.getText()).toString());}
        if(mode==8)return new Out(new StringBuilder().append(new ChangingView(left)).toString());
        if(mode==9)return new Out(new StringBuilder().append(new OpaqueView(left)).toString());
        if(mode==10){new Throwing(left);return new Out("unreached");}
        if(mode==11)return new Out(new StringBuilder().append(0).append(true).append(1L).append(2.5F).append(3.5D).append((String)null).toString());
        if(mode==13){String discard=External.VALUE;return new Out(left.getText());}
        if(mode==14){OrdersFoundationFixture outer=new OrdersFoundationFixture();return new Out(outer.new Inner(left.getText()).getText());}
        if(mode==15){String copied=left.getText();OrdersFoundationFixture outer=new OrdersFoundationFixture();outer.new Inner(copied);return new Out(copied);}
        touch(right);return new Out(left.getText());
    }
    public static void main(String[] args)throws Exception{
        ObjectMapper json=new ObjectMapper();List<Map<String,Object>> cases=new ArrayList<>();Item left=new Item("SAME"),right=new Item("SAME");
        for(int i=0;i<32;i++){
            left.setText("SAME");right.setText("SAME");GLOBAL=left;int mode=i%16;W3CTraceContext c=W3CTraceContext.server("00-55555555555555555555555555555555-"+String.format("%016x",i+1)+"-01","fixture=orders-foundation");SpringTransportAgent.Transport.ASYNC.set(c);Map row=new LinkedHashMap();row.put("mode",mode);row.put("message",c.fields().get("message"));
            try{Out result=root(left,right,mode);ResponseBindingHooks.verifySerialization(result,json);row.put("response",json.readValue(json.writeValueAsString(result),Map.class));row.put("status","normal");Map wire=c.fields();wire.put("uri","fixture:orders-foundation");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}}
            catch(IllegalArgumentException expected){row.put("status","aborted");}
            cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(json.writeValueAsString(cases));
    }
}
