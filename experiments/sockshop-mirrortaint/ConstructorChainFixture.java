import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
/** Constructor identity/effects; expected sources are declared separately. */
public class ConstructorChainFixture {
 public static class Input {public String left,right;public Object tested;public int mode,finallyCount;public IllegalArgumentException failure;public Input(){} }
 public static class Result {public String text;public Result(){} }
 public static class Base {public String text,hidden;public String empty;public List<String> members;public Base(Input x){text=x.left;hidden=x.left;members=new ArrayList<>();members.add(x.left);if(x.mode>=11)text=x.tested instanceof List?x.right:x.left;if(x.mode==5)throw x.failure;}public String getBase(){return text;}public String getHidden(){return hidden;}public String getEmpty(){return empty;}}
 public static class Child extends Base {public String hidden;public Child(Input x){super(x);hidden=x.right;if(x.mode==1)text=x.right;if(x.mode==10)text="same";}public String getChildHidden(){return hidden;}}
 public static class Delegating extends Base {public Delegating(Input x){this(x,1);}public Delegating(Input x,int ignored){super(x);super.text=x.right;}}
 public static class Callback extends Base {public Callback(Input x){super(x);OpaqueConstructorEffects.touch(x);}}
 public static class Published extends Base {public static Published published;public Published(Input x){super(x);published=this;}}
 public static class Box {public String text;public Box(){} }
 public static class Reader {private Box value;public Reader(String s){value=new Box();value.text=s;}public Box read(){return value;}}
 public Reader reader;
 public Result root(Input input){Box remote=reader.read();Result out=new Result();
  try{
   if(input.mode==9){Delegating c=new Delegating(input);out.text=c.getBase();}
   else if(input.mode==6){new Callback(input);out.text=remote.text;}
   else if(input.mode==7){new Published(input);OpaqueConstructorEffects.global();out.text=remote.text;}
   else{Child c=new Child(input);if(input.mode==2)out.text=c.getHidden();else if(input.mode==3)out.text=c.getChildHidden();else if(input.mode==4)out.text=c.getEmpty();else if(input.mode==8)out.text=remote.text;else out.text=c.getBase();}
  }catch(IllegalArgumentException e){if(e!=input.failure)throw e;out.text="fallback";}finally{input.finallyCount++;}
  return out;
 }
 public static void main(String[] args)throws Exception{List<Map> results=new ArrayList<>();ObjectMapper mapper=new ObjectMapper();int n=0;
  for(int repeat=0;repeat<2;repeat++)for(int mode=0;mode<=14;mode++){Input input=new Input();input.left=new String("same");input.right=new String("same");input.mode=mode;input.tested=mode==12?new ArrayList<>():mode==13?"same":mode==14?new Object[]{"same"}:null;input.failure=new IllegalArgumentException("original");ConstructorChainFixture f=new ConstructorChainFixture();f.reader=new Reader("same");W3CTraceContext c=W3CTraceContext.server("00-66666666666666666666666666666666-"+String.format("%016x",++n)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(c);Result value;
   try{value=f.root(input);}finally{SpringTransportAgent.Transport.ASYNC.remove();}
   Map row=new LinkedHashMap();row.put("mode",mode);row.put("repeat",repeat);row.put("message",c.message());row.put("text",value.text);row.put("finallyCount",input.finallyCount);results.add(row);
  }System.out.println(mapper.writeValueAsString(results));
 }
}
class OpaqueConstructorEffects {static void touch(ConstructorChainFixture.Input x){}static void global(){} }
