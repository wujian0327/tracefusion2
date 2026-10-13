import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Set;
import disttaint.OT3AnalysisAll;

/** Read the original analyzer's decision flags; do not implement a new search. */
public final class FlowDistStatementDecision {
    private static Object value(String name) throws Exception {
        Field field=OT3AnalysisAll.class.getDeclaredField(name);field.setAccessible(true);return field.get(null);
    }
    public static void main(String[] args) throws Exception {
        OT3AnalysisAll.main(args);
        Method get=OT3AnalysisAll.class.getDeclaredMethod("getNodes",String.class,String.class,ArrayList.class);
        get.setAccessible(true);
        int source=((Set<?>)get.invoke(null,value("method1"),value("stmt1"),value("stmtStrs"))).size();
        int sink=((Set<?>)get.invoke(null,value("method2"),value("stmt2"),value("stmtStrs"))).size();
        System.out.println("FLOWDIST_ORIGINAL_FLAGS={\"source_nodes\":"+source+",\"sink_nodes\":"+sink
            +",\"is_local\":"+value("isLocal")+",\"no_dependency\":"+value("isNoDependency")+"}");
    }
}
