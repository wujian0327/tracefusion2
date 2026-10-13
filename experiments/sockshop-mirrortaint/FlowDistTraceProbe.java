import java.io.File;
import java.io.FileInputStream;
import java.io.ObjectInputStream;
import java.util.Arrays;
import java.util.Map;
import java.util.TreeMap;

/** Inspect only trusted, locally generated author Remote*.em traces. */
public final class FlowDistTraceProbe {
    private static String quote(String s) {
        StringBuilder b=new StringBuilder("\"");
        for (char c:s.toCharArray()) {
            if (c=='"' || c=='\\') b.append('\\').append(c);
            else if (c<32) b.append(String.format("\\u%04x",(int)c));
            else b.append(c);
        }
        return b.append('"').toString();
    }
    private static String clean(String s) { return s.replace("\0", "").trim(); }
    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        String source=args.length>1?args[1]:"<CalculatorHandler: int add(int,int)>";
        String sink=args.length>2?args[2]:"<CalculatorClient: void main(java.lang.String[])>";
        File[] files=new File(args[0]).listFiles((d,n)->n.startsWith("Remote") && n.endsWith(".em"));
        if (files==null || files.length!=2) throw new IllegalStateException("Expected two process traces");
        Arrays.sort(files);
        System.out.print("[");
        for (int i=0;i<files.length;i++) {
            Map<String,Integer> first,last,senders;
            try (ObjectInputStream in=new ObjectInputStream(new FileInputStream(files[i]))) {
                first=(Map<String,Integer>)in.readObject();last=(Map<String,Integer>)in.readObject();
                senders=(Map<String,Integer>)in.readObject();
            }
            String self=null;TreeMap<String,Integer> peers=new TreeMap<>();
            for (Map.Entry<String,Integer> e:senders.entrySet()) {
                if (e.getValue().equals(Integer.MAX_VALUE)) self=clean(e.getKey());
                else if (!e.getKey().startsWith("<")) peers.put(clean(e.getKey()),e.getValue());
            }
            if (self==null) throw new IllegalStateException("Missing process identity");
            if (i>0) System.out.print(",");
            System.out.print("{\"trace\":"+quote(files[i].getName())+",\"process\":"+quote(self)+",\"peers\":{");
            int j=0;
            for (Map.Entry<String,Integer> e:peers.entrySet()) {
                if (j++>0) System.out.print(",");
                System.out.print(quote(e.getKey())+":"+e.getValue());
            }
            System.out.print("},\"server_add_first\":"+first.get("<CalculatorHandler: int add(int,int)>")+
                ",\"client_main_last\":"+last.get("<CalculatorClient: void main(java.lang.String[])>")+
                ",\"source_first\":"+first.get(source)+",\"sink_last\":"+last.get(sink)+"}");
        }
        System.out.println("]");
    }
}
