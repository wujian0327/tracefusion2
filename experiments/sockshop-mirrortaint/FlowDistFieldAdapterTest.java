import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.GZIPOutputStream;

/** Decoder regression checks use no expected dependency labels. */
public final class FlowDistFieldAdapterTest {
    static Path capture(Map<String,Integer> names,Map<Integer,Integer> events) throws Exception {
        Path path=Files.createTempDirectory("flowdist-field-decoder-test-");
        try(ObjectOutputStream out=new ObjectOutputStream(new GZIPOutputStream(Files.newOutputStream(path.resolve("Local1.em"))))) {
            out.writeObject(names);out.writeObject(events);
        }
        return path;
    }
    static void reject(Map<String,Integer> names,Map<Integer,Integer> events,String reason) throws Exception {
        Path path=capture(names,events);boolean rejected=false;
        try {FlowDistFieldDecision.decode(path,"<Source>","<Sink>");}
        catch(IllegalStateException expected){rejected=true;}
        if(!rejected)throw new AssertionError(reason);
        Files.delete(path.resolve("Local1.em"));Files.delete(path);
    }
    public static void main(String[] args) throws Exception {
        Map<String,Integer> names=new HashMap<>();names.put("<Source>",3);names.put("<Sink>",8);
        names.put("process-peer",3); // Clock namespace may collide with a method ID.
        LinkedHashMap<Integer,Integer> events=new LinkedHashMap<>();
        events.put(1,-3);events.put(2,3);events.put(4,-8);events.put(5,8);events.put(9,-3);events.put(10,3);
        Path path=capture(names,events);
        Map<?,?> result=FlowDistFieldDecision.decode(path,"<Source>","<Sink>");
        if(!result.get(2).equals(events)||((Map<?,?>)result.get(2)).size()!=6)throw new AssertionError("Repeated method events lost");
        if(((Map<?,?>)result.get(1)).size()!=2)throw new AssertionError("Clock metadata entered method namespace");
        Files.delete(path.resolve("Local1.em"));Files.delete(path);
        LinkedHashMap<Integer,Integer> bad=new LinkedHashMap<>(events);bad.put(11,-999);reject(names,bad,"Unknown event ID accepted");
        bad=new LinkedHashMap<>();bad.put(2,-3);bad.put(1,-8);bad.put(3,8);reject(names,bad,"Nonmonotonic events accepted");
        bad=new LinkedHashMap<>();bad.put(1,-3);bad.put(2,3);reject(names,bad,"Unobserved endpoint accepted");
        Map<String,Integer> duplicate=new HashMap<>(names);duplicate.put("<Duplicate>",3);reject(duplicate,events,"Duplicate method IDs accepted");
        System.out.println("5 full-event decoder regression checks passed");
    }
}
