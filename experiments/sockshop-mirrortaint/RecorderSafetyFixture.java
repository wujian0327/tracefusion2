import java.util.*;import java.nio.file.*;
public class RecorderSafetyFixture{
    static int getterCalls;
    public static class Sentinel{public String getText(){getterCalls++;return "SIDE EFFECT";}}
    public static void main(String[]args)throws Exception{
        PlannedServiceAgent.Recorder.output=Files.newBufferedWriter(Paths.get(args[0]));
        Map bad=new LinkedHashMap();bad.put("live",Arrays.asList(new Sentinel()));boolean refused=false;
        try{PlannedServiceAgent.Recorder.emit("bad",bad);}catch(IllegalStateException expected){refused=true;}
        if(!refused||getterCalls!=0||PlannedServiceAgent.Recorder.seq!=0)throw new AssertionError("Event serialization invoked business code or consumed sequence");
        Map good=new LinkedHashMap();good.put("safe",Arrays.asList("text",1,true,null));PlannedServiceAgent.Recorder.emit("good",good);PlannedServiceAgent.Recorder.output.close();System.out.println("refused_live_object=true getter_calls=0 contiguous_after_refusal=true");
    }
}
