import com.shadow.taint.agent.model.A;
import com.shadow.taint.agent.model.H;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.stream.DoubleStream;

/** Sequential DoubleStream.sum rule: fold actual instrumented mapper-return labels. */
public final class MirrorTaintStreamAdapter {
    private static final ThreadLocal<Deque<A>> FOLDS = new ThreadLocal<Deque<A>>() {
        protected Deque<A> initialValue() { return new ArrayDeque<>(); }
    };
    public static double sum(DoubleStream stream) {
        if (stream.isParallel()) {
            System.err.println("TF2_MT_ADAPTER error mode=streams cause=parallel-stream-unsupported");
            return stream.sum();
        }
        Deque<A> folds = FOLDS.get();
        A total = new A(org.stack.taint.asm.Type.DOUBLE);
        folds.push(total);
        try {
            double result = stream.sum();
            H register = new H();
            register.B(total);
            com.shadow.taint.agent.runtime.A.A.set(register);
            return result;
        } finally {
            folds.pop();
            if (folds.isEmpty()) FOLDS.remove();
        }
    }
    public static void mapperReturned() {
        Deque<A> folds = FOLDS.get();
        if (folds.isEmpty()) { FOLDS.remove(); return; }
        H register = com.shadow.taint.agent.runtime.A.A.get();
        if (register != null && register.B() != null)
            folds.peek().A(register.B(), new StackTraceElement("MirrorTaintStreamAdapter", "sum", "MirrorTaintStreamAdapter.java", -1),
                "sequential DoubleStream.sum mapper return");
    }
}
