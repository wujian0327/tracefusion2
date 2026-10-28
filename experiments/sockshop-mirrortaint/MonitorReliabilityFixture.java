import java.lang.reflect.*;
import java.util.*;
/** Independent business exception/return/finally oracle, not a provenance benchmark. */
public class MonitorReliabilityFixture {
 public interface View {default Input get(Input x){if(x.text==null)throw ORIGINAL;return x;}}
 static final View VIEW=new View(){};
 public static class Input {public String text;public String kind;Input(String t,String k){text=t;kind=k;}}
 static final RuntimeException ORIGINAL=new IllegalArgumentException("original-business-object");
 static final Exception CHECKED=new java.io.IOException("checked-original");static final Error ORIGINAL_ERROR=new AssertionError("error-original");
 static int finalies,handlers;static List<String> parentChecks=new ArrayList<>();
 public static Input child(Input x){return deeper(x);}
 public static Input deeper(Input x){if(x.kind.equals("nested-mutation"))x.text="changed";if((x.kind.equals("nested-business")||x.kind.equals("caught-business")))throw ORIGINAL;return x;}
 static void pending(){try{Class.forName("PlannedServiceAgent$Recorder").getMethod("callsite",String.class).invoke(null,"parent-to-child");}catch(ClassNotFoundException noAgent){}catch(Exception e){throw new IllegalStateException(e);}}
 public static Input root(Input x)throws Exception{try{
   if(x.kind.equals("interface"))return VIEW.get(x);
   if(x.kind.equals("caught-business")){try{child(x);}catch(IllegalArgumentException e){if(e!=ORIGINAL)throw new AssertionError();handlers++;parentChecks.add(state());}return x;}
   if(x.kind.startsWith("nested")){pending();Input y=child(x);parentChecks.add(state());return y;}
   if(x.kind.equals("mutation"))x.text="changed";
   if(x.kind.equals("business"))throw ORIGINAL;if(x.kind.equals("checked"))throw CHECKED;if(x.kind.equals("error"))throw ORIGINAL_ERROR;
   return x;
 }finally{finalies++;}}
 static String state(){try{return Class.forName("MonitorSafety").getMethod("inspect").invoke(null).toString();}catch(ClassNotFoundException noAgent){return "no-agent";}catch(Exception e){throw new IllegalStateException(e);}}
 static void one(String label,String fault,String filter,String kind){
  System.setProperty("service.monitor.test.enabled","true");if(fault==null)System.clearProperty("service.monitor.test.fault");else System.setProperty("service.monitor.test.fault",fault);System.setProperty("service.monitor.test.method",filter);
  Input x=new Input("same",kind);String result;
  try{Input y=root(x);result="returned-same="+(x==y)+"/text="+y.text;}catch(Throwable original){handlers++;result="throw-same="+(original==ORIGINAL||original==CHECKED||original==ORIGINAL_ERROR);}
  System.out.println("BUSINESS|"+label+"|"+result+"|finally="+finalies+"|handlers="+handlers);
  System.out.println("STATE|"+label+"|"+state());
 }
 public static void main(String[] args){
  one("normal-before",null,"","normal");one("enter-failure","enter",".root(","normal");one("normal-after-enter",null,"","normal");one("business-exception",null,"","business");one("normal-after-business",null,"","normal");
  one("nested-enter","enter",".child(","nested");one("normal-after-nested",null,"","normal");one("exit-failure","exit",".root(","normal");one("normal-after-exit",null,"","normal");one("cleanup-failure","cleanup",".root(","normal");one("normal-after-cleanup",null,"","normal");
  one("active-registration-failure","enter-active",".root(","normal");one("normal-after-active",null,"","normal");one("nested-exit","exit",".child(","nested");one("nested-cleanup","cleanup",".child(","nested");one("abort-failure","abort",".root(","business");one("last-normal",null,"","normal");
  one("checked-exception",null,"","checked");one("error-identity",null,"","error");one("nested-business-exception",null,"","nested-business");one("nested-enter-and-business","enter",".child(","nested-business");one("final-normal",null,"","normal");
  one("source-write-monitor-failure",null,"","mutation");one("normal-after-write",null,"","normal");
  one("interface-default",null,"","interface");one("nested-write-failure",null,"","nested-mutation");one("caught-original-business",null,"","caught-business");
  for(String s:parentChecks)System.out.println("PARENT|"+s);
 }
}
