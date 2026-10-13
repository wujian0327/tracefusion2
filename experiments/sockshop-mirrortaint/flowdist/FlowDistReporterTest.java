import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import profile.BranchReporter;

/** The second report must reflect newly hit branches, not cached startup IDs. */
public final class FlowDistReporterTest {
    public static void main(String[] args) throws Exception {
        Files.write(Paths.get("entitystmt.out.branch"),"0\n1\n".getBytes(StandardCharsets.UTF_8));
        BranchReporter reporter=new BranchReporter();
        reporter.writeReportMsg(new int[]{1,0},"reports.out");
        reporter.writeReportMsg(new int[]{1,1},"reports.out");
        String report=new String(Files.readAllBytes(Paths.get("reports.out")),StandardCharsets.UTF_8);
        if (!report.contains("Statements covered (based on branch coverage): 0 1") ||
            !report.contains("Total statements covered: 2/2"))
            throw new AssertionError("Repeated report retained stale startup coverage");
        System.out.println("Passed repeated-report branch-to-statement cache regression");
    }
}
