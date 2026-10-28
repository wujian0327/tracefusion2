import java.util.*;
import java.math.BigDecimal;
import org.springframework.util.Assert;
import com.fasterxml.jackson.databind.ObjectMapper;
/** Independent local-field semantics oracle; JSON projection is a later stage. */
public class FoundationValueFixture {
 public static class Input {public boolean flag;public int number;public String text;public Input(boolean f,int n,String t){flag=f;number=n;text=t;}public boolean isFlag(){return flag;}public int getNumber(){return number;}public String getText(){return text;}}
 public static class Result {public Boolean flag;public BigDecimal amount;public String text;public int number;public boolean live;public List<String> empty;public Result(){}public Result(String s){text=s;}public Boolean getFlag(){return flag;}public BigDecimal getAmount(){return amount;}public String getText(){return text;}public int getNumber(){return number;}public boolean isLive(){return live;}public List<String> getEmpty(){return empty;}public void setFlag(Boolean x){flag=x;}public void setAmount(BigDecimal x){amount=x;}public void setText(String x){text=x;}public void setNumber(int x){number=x;}}
 enum Plain {ALPHA,BETA;static Plain pick(){return ALPHA;}}
 enum Unproved {ALPHA,BETA;static {OpaqueFoundation.touch(new Object());}static Unproved pick(){return ALPHA;}}
 public static class Escaping {public String text;public Escaping(){OpaqueFoundation.touch(this);}public String getText(){return text;}}
 public static class Bomb {public String text;public Bomb(){throw new IllegalArgumentException("original-ctor");}}
 public static Result root(Input left,Input right,int mode){
  Result r=new Result();
  if(mode==0)r.setFlag(Boolean.valueOf(left.isFlag()));
  else if(mode==1)r.setFlag(Boolean.valueOf(right.isFlag()));
  else if(mode==2)r.setAmount(new BigDecimal(left.getNumber()));
  else if(mode==3)r.setAmount(new BigDecimal(right.getNumber()));
  else if(mode==4){}
  else if(mode==5){}
  else if(mode==6){}
  else if(mode==7){r=new Result(left.getText());r.setText(null);}
  else if(mode==8)OpaqueFoundation.touch(r);
  else if(mode==9){}
  else if(mode==10)OpaqueFoundation.touch(left);
  else if(mode==11){Assert.isNull(null,"literal-message");r.setText(left.getText());}
  else if(mode==12){try{Assert.isNull(left,"literal-message");r.setText(left.getText());}catch(IllegalArgumentException original){r.setText(right.getText());}}
  else if(mode==13){Assert.isNull(null,()->"unused-supplier");r.setText(left.getText());}
  else if(mode==14){Unproved.pick();r.setText(left.getText());}
  else if(mode==15){r=new Result(left.getText());r.setText(right.getText());}
  else if(mode==16)r.setNumber(0);
  else if(mode==17){new Bomb();r.setText(left.getText());}
  else if(mode==18){Plain.pick();Plain ignored=Plain.BETA;r.setText(left.getText());}
  else if(mode==19){Escaping x=new Escaping();r.setText(x.getText());}
  else if(mode==20)r=new Result(left.getText());
  else if(mode==21){BigDecimal a=new BigDecimal(left.getNumber());BigDecimal b=new BigDecimal(right.getNumber());r.amount=a;}
  else if(mode==22)r.setAmount((BigDecimal)OpaqueFoundation.identity(new BigDecimal(left.getNumber())));
  return r;
 }
 public static void main(String[] args)throws Exception{
  String group=args[0];int[] modes=group.equals("flag")?new int[]{0,1}:group.equals("amount")?new int[]{2,3,21,22}:group.equals("number")?new int[]{5,16}:group.equals("live")?new int[]{6}:group.equals("empty")?new int[]{9}:new int[]{4,7,8,10,11,12,13,14,15,17,18,19,20};
  List<Map> cases=new ArrayList<>();int serial=0;
  for(int pass=0;pass<3;pass++)for(int mode:modes){Input left=new Input(pass!=1,pass==0?0:pass==1?-19:2147483647,pass==2?null:"SAME"),right=new Input(left.flag,left.number,left.text);String span=String.format("%016x",++serial);W3CTraceContext c=W3CTraceContext.server("00-11111111111111111111111111111111-"+span+"-01","fixture=foundation");SpringTransportAgent.Transport.ASYNC.set(c);Map r=new LinkedHashMap();r.put("mode",mode);r.put("message",c.message());r.put("pass",pass);
   try{r.put("value",root(left,right,mode));r.put("aborted",false);}catch(IllegalArgumentException original){if(mode!=17||!original.getMessage().equals("original-ctor"))throw original;r.put("aborted",true);}finally{SpringTransportAgent.Transport.ASYNC.remove();}cases.add(r);
  }
  System.out.println(new ObjectMapper().writeValueAsString(cases));
 }
}
class OpaqueFoundation {public static void touch(Object x){}public static Object identity(Object x){return x;}}
