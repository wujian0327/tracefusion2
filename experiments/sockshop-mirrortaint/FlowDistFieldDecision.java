import java.io.*;
import java.nio.file.*;
import java.lang.reflect.Field;
import java.util.*;
import java.util.zip.GZIPInputStream;
import disttaint.DynTransferGraph;
import disttaint.OT3AnalysisAll;
import disttaint.dtStmtUtil;

/** Full recorded events into the author's query builder and statement search.
 * No method-key collapsing, invented events, field edges, or static fallback.
 * Requires the separately audited single method-ID namespace compatibility fix.
 */
public final class FlowDistFieldDecision {
    static Object get(String name) throws Exception {
        Field f=OT3AnalysisAll.class.getDeclaredField(name);f.setAccessible(true);return f.get(null);
    }
    static void set(String name,Object value) throws Exception {
        Field f=OT3AnalysisAll.class.getDeclaredField(name);f.setAccessible(true);f.set(null,value);
    }
    @SuppressWarnings("unchecked")
    static HashMap<Integer,Object> decode(Path directory,String source,String sink) throws Exception {
        File[] files=directory.toFile().listFiles((d,n)->n.startsWith("Local")&&n.endsWith(".em"));
        if(files==null||files.length!=1)throw new IllegalStateException("One complete Local capture required");
        Map<String,Integer> raw;Map<Integer,Integer> events;
        try(ObjectInputStream in=new ObjectInputStream(new GZIPInputStream(new FileInputStream(files[0])))) {
            raw=(Map<String,Integer>)in.readObject();events=(Map<Integer,Integer>)in.readObject();
        }
        LinkedHashMap<String,Integer> names=new LinkedHashMap<>();Map<Integer,String> inverse=new HashMap<>();int clocks=0;
        for(Map.Entry<String,Integer> entry:raw.entrySet()) {
            if(!entry.getKey().startsWith("<")){clocks++;continue;}
            if(entry.getValue()<=0||inverse.put(entry.getValue(),entry.getKey())!=null)throw new IllegalStateException("Invalid method index");
            names.put(entry.getKey(),entry.getValue());
        }
        int previous=Integer.MIN_VALUE,enters=0,returns=0;Set<String> entered=new HashSet<>();
        for(Map.Entry<Integer,Integer> event:events.entrySet()) {
            if(event.getKey()<=previous)throw new IllegalStateException("Nonmonotonic event order");previous=event.getKey();
            int value=event.getValue();if(value==Integer.MIN_VALUE||value==Integer.MAX_VALUE)continue;
            String method=inverse.get(Math.abs(value));if(method==null)throw new IllegalStateException("Unknown recorded method ID "+value);
            if(value<0){enters++;entered.add(method);}else returns++;
        }
        if(enters==0||returns==0||!entered.contains(source)||!entered.contains(sink))throw new IllegalStateException("Unobserved source/sink method");
        LinkedHashMap<Integer,Integer> copied=new LinkedHashMap<>(events);
        if(!copied.equals(events)||!new ArrayList<>(copied.entrySet()).equals(new ArrayList<>(events.entrySet())))throw new IllegalStateException("Events changed");
        System.out.println("FLOWDIST_DECODED_TRACE={\"events\":"+events.size()+",\"enters\":"+enters+",\"returns\":"+returns
            +",\"methods\":"+names.size()+",\"separate_clock_entries\":"+clocks+",\"all_event_entries_preserved\":true}");
        HashMap<Integer,Object> result=new HashMap<>();result.put(1,names);result.put(2,copied);return result;
    }
    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        String query=new String(Files.readAllBytes(Paths.get(args[0])),"UTF-8").trim();
        String source=dtStmtUtil.getFirstMethod(query),sink=dtStmtUtil.getSecondMethod(query);
        String first=dtStmtUtil.getFirstStmt(query),last=dtStmtUtil.getSecondStmt(query);
        HashMap<Integer,Object> events=decode(Paths.get(args[1]),source,sink);
        OT3AnalysisAll.applyStatementCoverage=true;OT3AnalysisAll.prePrune=false;OT3AnalysisAll.postPrune=true;
        set("applyMethodCoverage",true);
        if(OT3AnalysisAll.init(args[2])!=0)throw new IllegalStateException("Graph initialization failed");
        DynTransferGraph original=(DynTransferGraph)get("dvtg"),exercised=new DynTransferGraph(),pruned=new DynTransferGraph();
        if(original.buildGraph(exercised,source,false,events)!=0)throw new IllegalStateException("Original graph exercise failed");
        if(exercised.nodeSet().isEmpty()||exercised.edgeSet().isEmpty())throw new IllegalStateException("Empty exercised graph; static fallback forbidden");
        int nodes=exercised.nodeSet().size(),edges=exercised.edgeSet().size();
        List<Integer> covered=(List<Integer>)get("coveredStmts");
        if(covered.isEmpty())throw new IllegalStateException("Missing statement coverage");
        exercised.postPruneByCoverage(pruned,covered);set("dvtgExercised",exercised);set("dvtgPruned",pruned);
        ArrayList statements=(ArrayList)get("stmtStrs");
        int nsource=OT3AnalysisAll.getNodes(source,first,statements).size(),nsink=OT3AnalysisAll.getNodes(sink,last,statements).size();
        OT3AnalysisAll.computeNodes(source,first,sink,last,statements);
        System.out.println("FLOWDIST_ORIGINAL_FLAGS={\"source_nodes\":"+nsource+",\"sink_nodes\":"+nsink
            +",\"exercised_nodes\":"+nodes+",\"exercised_edges\":"+edges
            +",\"is_local\":"+get("isLocal")+",\"no_dependency\":"+get("isNoDependency")+"}");
    }
}
