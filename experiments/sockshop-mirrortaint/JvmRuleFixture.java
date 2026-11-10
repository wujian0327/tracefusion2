import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
/** Original Java results and explicit source fields, never provenance logic. */
public class JvmRuleFixture {
 public static class Data {public long a,b,other;public int x,y;public Data(long a,long b,int x,int y){this.a=a;this.b=b;this.x=x;this.y=y;}public long getA(){return a;}public long getB(){return b;}public void setOther(long n){other=n;}}
 public static class Out {public long result;public Out(long v){result=v;}public long getResult(){return result;}}
 public static class Store {public Data read(int mode){return new Data(mode==0?Long.MAX_VALUE:mode==1?Long.MIN_VALUE:7L,mode==1?-1L:mode==0?1L:7L,Integer.MAX_VALUE,1);}}
 public static Out root(Store store,int mode){
  Data row=store.read(mode);
  if(mode==0||mode==1||mode==2)return new Out(row.a+row.b);
  if(mode==3)return new Out((long)(row.x+row.y));
  if(mode==4){row.a=7L;return new Out(row.a);}
  if(mode==5){Data alias=row;alias.a=7L;return new Out(row.a);}
  if(mode==6){row.setOther(row.a);return new Out(row.b);}
  try{Data absent=null;return new Out(absent.a);}catch(NullPointerException original){return new Out(row.b);}
 }
 public static void main(String[] args)throws Exception{
  List<Map> results=new ArrayList<>();
  for(int mode=0;mode<8;mode++){
   W3CTraceContext c=W3CTraceContext.server("00-33333333333333333333333333333333-"+String.format("%016x",mode+1)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(c);
   try{Out out=root(new Store(),mode);Map r=new LinkedHashMap();r.put("case",mode);r.put("message",c.message());r.put("value",out.result);results.add(r);}finally{SpringTransportAgent.Transport.ASYNC.remove();}
  }
  System.out.println(new ObjectMapper().writeValueAsString(results));
 }
}
