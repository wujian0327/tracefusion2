import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public class I2LSourceFixture {
 public static class Input {public int left,right;public boolean choose;public int getLeft(){return left;}public int getRight(){return right;}public boolean isChoose(){return choose;}}
 public static class Result {public long value;public long getValue(){return value;}}
 public static class Box {public long amount=7;public long getAmount(){return amount;}}
 public static class Source {public static Box read(){return new Box();}}
 public static class OpaqueCaller {public static Box fetch(int n){float opaque=(float)n;Box b=Source.read();if(n<0)throw new IllegalArgumentException("original");if(opaque==0)Source.read();return b;}}
 public Result root(Input input){Result out=new Result();int selected=input.choose?input.left:input.right;out.value=(long)selected;return out;}
 public Result unknown(Input input){Result out=new Result();out.value=(long)OpaqueI2L.value(input.left);return out;}
 public Result observation(Input input){Result out=new Result();try{out.value=OpaqueCaller.fetch(input.left).amount;}catch(IllegalArgumentException original){out.value=-1;}return out;}
 public static void main(String[] args)throws Exception{I2LSourceFixture self=new I2LSourceFixture();List<Map> result=new ArrayList<>();int id=0;for(int n:new int[]{Integer.MIN_VALUE,-1,0,1,Integer.MAX_VALUE})for(boolean choose:new boolean[]{true,false}){Input input=new Input();input.left=n;input.right=n;input.choose=choose;W3CTraceContext context=W3CTraceContext.server("00-77777777777777777777777777777777-"+String.format("%016x",++id)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(context);Result actual;try{actual=args.length==0?self.root(input):args[0].equals("unknown")?self.unknown(input):self.observation(input);}finally{SpringTransportAgent.Transport.ASYNC.remove();}Map row=new LinkedHashMap();row.put("message",context.message());row.put("choose",choose);row.put("value",actual.value);result.add(row);}System.out.println(new ObjectMapper().writeValueAsString(result));}
}
class OpaqueI2L {static int value(int x){return x;}}
