import soot.Scene;
import soot.SootClass;
import java.lang.reflect.InvocationTargetException;
import java.util.Arrays;

/** Load signatures required unconditionally by the author's P2 library models.
 * The restricted JDK-body configuration otherwise fails on an absent RefType.
 * Do not change the model definitions or the original analysis entry point. */
public final class FlowDistStaticLauncher {
    public static void main(String[] args) throws Exception {
        String[] models={"java.io.File","java.io.FileReader","java.lang.String",
            "java.util.ArrayList","java.util.HashMap","java.util.Hashtable",
            "java.util.List","java.util.Map","java.util.Set","java.util.Stack","java.util.Vector"};
        for (String type:models) Scene.v().addBasicClass(type,SootClass.SIGNATURES);
        try {
            Class.forName(args[0]).getMethod("main",String[].class).invoke(null,(Object)Arrays.copyOfRange(args,1,args.length));
        } catch (InvocationTargetException e) {
            Throwable cause=e.getCause();
            if (cause instanceof Error) throw (Error)cause;
            if (cause instanceof Exception) throw (Exception)cause;
            throw e;
        }
    }
}
