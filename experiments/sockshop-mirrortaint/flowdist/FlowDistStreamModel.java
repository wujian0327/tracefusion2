package disttaint;

import java.nio.file.*;
import java.util.*;
import java.lang.reflect.Method;
import MciaUtil.VTEdge.VTEType;

/** Disclosed sequential-stream library summary, applied before native exercise.
 * Uses native return edges; no field/query-specific propagation code.
 */
public final class FlowDistStreamModel {
    static DVTNode node(DynTransferGraph graph,int statement,String variable,String method) {
        List<DVTNode> matches=new ArrayList<>();
        for(DVTNode n:graph.nodeSet())if(n.getStmt()==statement && n.getVar().equals(variable)
            && method.equals(graph.idx2method.get(n.getMethod())))matches.add(n);
        if(matches.size()!=1)throw new IllegalStateException("Ambiguous stream model endpoint: "+method+"/"+statement+"/"+variable+" count="+matches.size());
        return matches.get(0);
    }
    public static void apply(DynTransferGraph graph,Path model) throws Exception {
        int count=0;
        for(String line:Files.readAllLines(model)) {
            if(line.isEmpty())continue;String[] values=line.split("\t",-1);
            if(values.length!=6)throw new IllegalStateException("Invalid stream summary");
            DVTNode source=node(graph,Integer.parseInt(values[0]),values[2],values[4]);
            DVTNode target=node(graph,Integer.parseInt(values[1]),values[3],values[5]);
            graph.addEdge(new DVTEdge(source,target,VTEType.VTE_RET));count++;
        }
        graph.method2nodes.clear();graph.type2edges.clear();
        Method classify=DynTransferGraph.class.getDeclaredMethod("classifyEdgeAndNodes");classify.setAccessible(true);classify.invoke(graph);
        System.out.println("FLOWDIST_SEQUENTIAL_STREAM_LIBRARY_SUMMARIES="+count);
    }
}
