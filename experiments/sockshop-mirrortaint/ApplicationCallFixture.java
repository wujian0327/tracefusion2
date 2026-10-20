import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Semantic oracle inputs; no provenance propagation in this program. */
public class ApplicationCallFixture {
    public static class Item {
        public String text;public String other;
        public Item(String text,String other){this.text=text;this.other=other;}
        public String getText(){return text;}public String getOther(){return other;}
        public void setText(String text){this.text=text;}public void setOther(String other){this.other=other;}
    }
    public static Item GLOBAL;
    public static class Box {public Item nested;public Box(Item nested){this.nested=nested;}public Item getNested(){return nested;}}
    static Item identity(Item x){return x;}
    static String field(Item x){return x.getText();}
    static String directField(Item x){return x.text;}
    static int twice(int value){return value+value;}
    static Item copy(Item x){return new Item(field(x),"unchanged");}
    static Item writeOther(Item x,Item source){x.setOther(field(source));return x;}
    static Item overwrite(Item x,Item source){x.setText(field(source));return x;}
    static String opaque(Item x){return x.getText().toString();}
    static Item opaqueAlias(Item x){int[] unsupported=new int[1];return x;}
    static Box opaqueBox(Box x){int[] unsupported=new int[1];return x;}
    static Item escaped(Item x){Item local=copy(x);Box box=new Box(local);opaqueBox(box);return local;}
    static Item recursive(Item x){return recursive(x);}
    static void opaqueGlobal(){int[] unsupported=new int[1];GLOBAL.setText("SAME");}
    static Item capturedBeforeOpaque(Item x,Item y){Item result=copy(x);opaque(y);return result;}
    static void voidWrite(Item x,Item source){x.setOther(field(source));}
    static Item collected(Item left,Item right){List<String> xs=new ArrayList<>();xs.add(field(left));xs.add(field(right));return new Item(xs.get(1),"unchanged");}
    static String rethrow(Item x){try{return field(x);}catch(NullPointerException e){throw e;}}
    public static Item root(Item left,Item right,int mode){
        if(mode==0)return identity(left);
        if(mode==1)return copy(right);
        if(mode==2)return writeOther(left,right);
        if(mode==3)return overwrite(left,right);
        if(mode==4)return new Item(opaque(left),"unchanged");
        if(mode==5){try{return copy(null);}catch(NullPointerException e){return copy(right);}}
        if(mode==6)return copy(left);
        if(mode==7)return copy(null);
        if(mode==8)return capturedBeforeOpaque(left,right);
        if(mode==9)return opaqueAlias(left);
        if(mode==10){opaqueGlobal();return left;}
        if(mode==11)return new Item(field(left),"unchanged");
        if(mode==12){voidWrite(left,right);return left;}
        if(mode==13)return collected(left,right);
        if(mode==15)return escaped(left);
        if(mode==16){try{return new Item(directField(null),"unchanged");}catch(NullPointerException e){return copy(right);}}
        if(mode==17){if(twice(mode)>0)return copy(left);return copy(right);}
        try{return new Item(rethrow(null),"unchanged");}catch(NullPointerException e){return new Item("fallback","unchanged");}
    }
    public static void main(String[] args)throws Exception{
        Item left=new Item("SAME","left"),right=new Item("SAME","right");ObjectMapper json=new ObjectMapper();List<Map<String,Object>> cases=new ArrayList<>();
        for(int i=0;i<36;i++){
            left.setText("SAME");right.setText("SAME");GLOBAL=left;
            int mode=i%18;W3CTraceContext c=W3CTraceContext.server("00-22222222222222222222222222222222-"+String.format("%016x",i+1)+"-01","fixture=calls");SpringTransportAgent.Transport.ASYNC.set(c);
            Map<String,Object> row=new LinkedHashMap<>();row.put("mode",mode);row.put("message",c.fields().get("message"));
            try{
                Item result=root(left,right,mode);ResponseBindingHooks.verifySerialization(result,json);String text=json.writeValueAsString(result);row.put("response",json.readValue(text,Map.class));row.put("status","normal");
                Map wire=c.fields();wire.put("uri","fixture:application-calls");wire.put("direction","response");wire.put("phase","write");wire.put("fields",SpringTransportAgent.Transport.snapshot(result));synchronized(PlannedServiceAgent.Recorder.class){PlannedServiceAgent.Recorder.emit("http-json",wire);}
            }catch(NullPointerException expected){row.put("status","aborted");}
            cases.add(row);SpringTransportAgent.Transport.ASYNC.remove();
        }
        System.out.println(json.writeValueAsString(cases));
    }
}
