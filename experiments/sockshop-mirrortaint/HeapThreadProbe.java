import com.shadow.taint.agent.runtime.TaintHeap;

/** Independent public-JAR lifecycle probe; does not instrument or alter Sock Shop. */
public final class HeapThreadProbe {
    public static void main(String[] args) throws Exception {
        System.out.println("main_before_startup=" + TaintHeap.available());
        TaintHeap.startup();
        System.out.println("main_after_startup=" + TaintHeap.available());
        Thread worker = new Thread(() -> {
            System.out.println("worker_before_startup=" + TaintHeap.available());
            TaintHeap.startup();
            System.out.println("worker_after_startup=" + TaintHeap.available());
            TaintHeap.shutdown();
        });
        worker.start();
        worker.join();
        System.out.println("main_after_worker_shutdown=" + TaintHeap.available());
        TaintHeap.shutdown();
    }
}
