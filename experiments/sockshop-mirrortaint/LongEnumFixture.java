import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
/** Literal enum state and exact long comparisons; no business field summaries. */
public class LongEnumFixture {
 public enum Code {LOW(-1,"low"),SAME(0,"same"),HIGH(1,"high");private long number;private String text;Code(long n,String t){number=n;text=t;}public long getNumber(){return number;}public String getText(){return text;}}
 public enum Mutable {ONE(1);private int number;Mutable(int n){number=n;}public void change(int n){number=n;}}
 public enum Callback {ONE(LongEnumOutside.callback());private int number;Callback(int n){number=n;}}
 public static class Input {public long left,right;public String a,b;public Input(){} }
 public static class Result {public long number;public String text,chosen;public Result(){} }
 public Result root(Input input){
  Code code;if(input.left<input.right)code=Code.LOW;else if(input.left==input.right)code=Code.SAME;else code=Code.HIGH;
  Result out=new Result();out.number=code.getNumber();out.text=code.getText();out.chosen=input.left>input.right?input.a:input.b;return out;
 }
 public static void main(String[] args)throws Exception{
  long[][] values={{Long.MIN_VALUE,Long.MAX_VALUE},{Long.MAX_VALUE,Long.MIN_VALUE},{Long.MIN_VALUE,Long.MIN_VALUE},{Long.MAX_VALUE,Long.MAX_VALUE},{9007199254740992L,9007199254740993L},{9007199254740993L,9007199254740992L},{-1,0},{0,-1},{0,0}};
  ObjectMapper mapper=new ObjectMapper();List<Map> cases=new ArrayList<>();LongEnumFixture fixture=new LongEnumFixture();int n=0;
  // Force both unsupported forms into the bytecode model without using them
  // to obtain a source answer.
  if(args.length>10){Mutable.ONE.change(2);System.out.println(Callback.ONE);}
  for(long[] pair:values){Input input=new Input();input.left=pair[0];input.right=pair[1];input.a=new String("same");input.b=new String("same");String wire=String.format("%016x",++n);W3CTraceContext context=W3CTraceContext.server("00-55555555555555555555555555555555-"+wire+"-01",null);SpringTransportAgent.Transport.ASYNC.set(context);Result result;
   try{result=fixture.root(input);}finally{SpringTransportAgent.Transport.ASYNC.remove();}
   Map row=new LinkedHashMap();row.put("case",n);row.put("message",context.message());row.put("left",pair[0]);row.put("right",pair[1]);row.put("number",result.number);row.put("text",result.text);row.put("chosen",result.chosen);cases.add(row);
  }System.out.println(mapper.writeValueAsString(cases));
 }
}
class LongEnumOutside {static int callback(){return 1;}}
