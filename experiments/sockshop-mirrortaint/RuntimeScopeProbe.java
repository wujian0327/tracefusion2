import com.shadow.taint.agent.runtime.TaintHeap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Public-JAR runtime scope diagnostic. Does not create or propagate taint labels. */
public final class RuntimeScopeProbe {
    private static void require(boolean value, String message) {
        if (!value) throw new IllegalStateException(message);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        Object sentinel = new Object();
        TaintHeap.startup();
        try {
            boolean parentAvailable = TaintHeap.available();
            boolean workerInitiallyAvailable = worker.submit(() -> TaintHeap.available()).get();
            boolean initializedWorkerAvailable = worker.submit(() -> {
                TaintHeap.startup();
                try {
                    // A null map slot is a scope sentinel, NOT a provenance tag.
                    TaintHeap.A.get().put(sentinel, null);
                    return TaintHeap.available() && TaintHeap.A.get().containsKey(sentinel);
                } finally {
                    TaintHeap.shutdown();
                }
            }).get();
            boolean parentSeesWorkerSlot = TaintHeap.A.get().containsKey(sentinel);
            boolean workerAfterCleanupAvailable = worker.submit(() -> TaintHeap.available()).get();
            require(parentAvailable, "Parent initialization failed");
            require(!workerInitiallyAvailable, "Unexpected automatic worker initialization");
            require(initializedWorkerAvailable, "Explicit worker initialization failed");
            require(!parentSeesWorkerSlot, "Unexpected automatic worker-to-parent heap sharing");
            require(!workerAfterCleanupAvailable, "Reused worker retained active heap after shutdown");
            require(TaintHeap.available(), "Worker cleanup damaged parent heap");
            System.out.println("{\"parent_available\":" + parentAvailable
                + ",\"worker_initially_available\":" + workerInitiallyAvailable
                + ",\"initialized_worker_available\":" + initializedWorkerAvailable
                + ",\"parent_sees_worker_slot\":" + parentSeesWorkerSlot
                + ",\"worker_after_cleanup_available\":" + workerAfterCleanupAvailable
                + ",\"parent_still_available\":" + TaintHeap.available()
                + ",\"taint_labels_created\":false,\"field_propagation_tested\":false}");
        } finally {
            TaintHeap.shutdown();
            worker.shutdownNow();
        }
    }
}
