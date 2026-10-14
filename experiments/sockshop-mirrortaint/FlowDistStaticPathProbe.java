import java.nio.file.*;
import java.util.ArrayList;
import disttaint.OT3AnalysisAll;
import disttaint.dtStmtUtil;

/** Diagnostic only: native search on the pre-trace graph, never an accuracy score. */
public final class FlowDistStaticPathProbe {
    public static void main(String[] args) throws Exception {
        String query=new String(Files.readAllBytes(Paths.get(args[0])),"UTF-8").trim();
        FlowDistFieldDecision.set("applyMethodCoverage",true);
        if(OT3AnalysisAll.init(args[1])!=0)throw new IllegalStateException("Cannot initialize diagnostic graph");
        FlowDistFieldDecision.set("dvtgPruned",FlowDistFieldDecision.get("dvtg"));
        OT3AnalysisAll.computeNodes(dtStmtUtil.getFirstMethod(query),dtStmtUtil.getFirstStmt(query),
            dtStmtUtil.getSecondMethod(query),dtStmtUtil.getSecondStmt(query),(ArrayList)FlowDistFieldDecision.get("stmtStrs"));
        System.out.println("STATIC_ONLY_DIAGNOSTIC_LOCAL_PATH="+FlowDistFieldDecision.get("isLocal"));
    }
}
