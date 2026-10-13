import java.io.*;
import java.util.*;
import java.util.zip.GZIPInputStream;

/** Decode only locally generated author maps, retaining lifecycle snapshots. */
public final class FlowDistLocalTraceAudit {
    private static String quote(String value) {return "\""+value.replace("\\","\\\\").replace("\"","\\\"")+"\"";}
    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        File folder=new File(args[0]);File[] locals=folder.listFiles((d,n)->n.startsWith("Local")&&n.endsWith(".em"));
        if(locals==null||locals.length!=1)throw new IllegalStateException("Expected one final Local trace");
        Map<String,Integer> names;Map<Integer,Integer> sequence;
        try(ObjectInputStream in=new ObjectInputStream(new GZIPInputStream(new FileInputStream(locals[0])))) {
            names=(Map<String,Integer>)in.readObject();sequence=(Map<Integer,Integer>)in.readObject();
        }
        Map<Integer,String> index=new HashMap<>();
        for(Map.Entry<String,Integer> entry:names.entrySet())if(entry.getKey().startsWith("<")) {
            if(index.put(entry.getValue(),entry.getKey())!=null)throw new IllegalStateException("Duplicate author method ID");
        }
        int enters=0,returns=0;Map<String,Integer> counts=new TreeMap<>();
        for(int value:sequence.values()) {
            String method=index.get(Math.abs(value));if(method==null)continue;
            if(value<0){enters++;counts.put(method,counts.getOrDefault(method,0)+1);}else returns++;
        }
        if(enters<20||returns<20||index.size()<10)throw new IllegalStateException("Incomplete original method event sequence");
        File[] remotes=new File(folder,"test1").listFiles((d,n)->n.startsWith("Remote")&&n.endsWith(".em"));
        if(remotes==null||remotes.length<1)throw new IllegalStateException("Missing author remote snapshots");
        Arrays.sort(remotes);String self=null;
        for(File file:remotes)try(ObjectInputStream in=new ObjectInputStream(new FileInputStream(file))) {
            in.readObject();in.readObject();Map<String,Integer> senders=(Map<String,Integer>)in.readObject();
            String current=null;
            for(Map.Entry<String,Integer> entry:senders.entrySet())if(entry.getValue()==Integer.MAX_VALUE)current=entry.getKey();
            if(current==null || self!=null&&!self.equals(current))throw new IllegalStateException("Remote lifecycle PID changed");
            self=current;
        }
        System.out.print("{\"methods\":"+index.size()+",\"enter_events\":"+enters+",\"return_events\":"+returns
            +",\"local_trace\":"+quote(locals[0].getName())+",\"remote_snapshots\":"+remotes.length
            +",\"selected_final_remote\":"+quote(remotes[remotes.length-1].getName())+",\"entry_counts\":{");
        int i=0;for(Map.Entry<String,Integer> entry:counts.entrySet()) {
            if(i++>0)System.out.print(",");System.out.print(quote(entry.getKey())+":"+entry.getValue());
        }
        System.out.println("}}");
    }
}
