import com.google.gson.Gson;
import com.shadow.taint.agent.runtime.TaintHeap;
import com.shadow.taint.agent.runtime.TaintTagger;
import java.util.*;
import java.util.concurrent.*;
import works.weave.socks.calibration.SyncLabelOps;
import works.weave.socks.calibration.SyncLabelOps.Item;
import works.weave.socks.calibration.SyncLabelOps.Result;

/** Controlled thread adapter verification; output labels come only from the original agent. */
public final class AsyncLabelDriver {
    private static Item source(String id) {
        Item input = new Item();
        input.name = new String("same-content"); input.quantity = 2; input.unitPrice = 5.0F;
        TaintTagger.tagDbQueryResult("fixture.rpc", id, input);
        return input;
    }
    private static Result calculate(Item first, Item second) {
        Result output = new Result();
        SyncLabelOps.copy(first, output);
        SyncLabelOps.amount(first, second, output);
        SyncLabelOps.combineNames(first, second, output);
        return output;
    }
    private static void snapshot(String stage, Object object) throws Exception {
        Map<String, Object> fields = new LinkedHashMap<>();
        for (java.lang.reflect.Field field : object.getClass().getDeclaredFields()) {
            if (java.lang.reflect.Modifier.isStatic(field.getModifiers())) continue;
            field.setAccessible(true);
            Map<String, Object> data = new LinkedHashMap<>();
            Object value = field.get(object);
            data.put("value", value);
            data.put("tag", field.getType().isPrimitive() ? TaintHeap.queryPrimitiveFieldTaint(object, field.getName())
                                                        : TaintHeap.queryTaint(value));
            fields.put(field.getName(), data);
        }
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("stage", stage); record.put("available", TaintHeap.available()); record.put("fields", fields);
        synchronized (System.out) { System.out.println("TF2_SYNC_SNAPSHOT " + new Gson().toJson(record)); }
    }
    private static void check(String name, boolean passed) {
        System.out.println("TF2_ASYNC_CHECK " + name + "=" + passed);
        if (!passed) throw new IllegalStateException(name);
    }
    private static void cleanWorkers(ExecutorService workers, String stage) throws Exception {
        CountDownLatch entered = new CountDownLatch(2);
        Callable<Boolean> clean = () -> {
            entered.countDown();
            if (!entered.await(5, TimeUnit.SECONDS)) return false;
            return !TaintHeap.available() && com.shadow.taint.agent.runtime.A.A.get() == null;
        };
        Future<Boolean> first = workers.submit(clean), second = workers.submit(clean);
        check(stage, first.get(5, TimeUnit.SECONDS) && second.get(5, TimeUnit.SECONDS));
    }
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);
        ExecutorService callers = Executors.newFixedThreadPool(2);
        TaintHeap.startup();
        try {
            Item a = source("item-a"), b = source("item-b");
            snapshot("source-a", a); snapshot("source-b", b);
            snapshot("async-captured", MirrorTaintThreadAdapter.submit(workers, () -> calculate(a, b)).get(5, TimeUnit.SECONDS));
            Future<Result> produced = MirrorTaintThreadAdapter.submit(workers, () -> {
                Item c = source("item-c"), d = source("item-d");
                snapshot("source-c", c); snapshot("source-d", d);
                return calculate(c, d);
            });
            snapshot("async-produced", produced.get(5, TimeUnit.SECONDS));
            cleanWorkers(workers, "normal-worker-cleanup");

            CountDownLatch overlap = new CountDownLatch(2);
            List<Future<Boolean>> concurrent = new ArrayList<>();
            for (String key : Arrays.asList("e", "f")) concurrent.add(callers.submit(() -> {
                TaintHeap.startup();
                try {
                    Item input = source("item-" + key);
                    snapshot("source-" + key, input);
                    Future<Result> result = MirrorTaintThreadAdapter.submit(workers, () -> {
                        overlap.countDown();
                        if (!overlap.await(5, TimeUnit.SECONDS)) throw new IllegalStateException("No worker overlap");
                        return calculate(input, input);
                    });
                    snapshot("concurrent-" + key, result.get(5, TimeUnit.SECONDS));
                    return true;
                } finally { TaintHeap.shutdown(); }
            }));
            check("two-caller-concurrency", concurrent.get(0).get(10, TimeUnit.SECONDS) && concurrent.get(1).get(10, TimeUnit.SECONDS));
            cleanWorkers(workers, "concurrent-worker-cleanup");

            Future<Result> failed = MirrorTaintThreadAdapter.submit(workers, () -> { throw new IllegalArgumentException("fixture-error"); });
            boolean exception = false;
            try { failed.get(5, TimeUnit.SECONDS); } catch (ExecutionException expected) {
                exception = expected.getCause() instanceof IllegalArgumentException;
            }
            check("exception-preserved", exception);
            cleanWorkers(workers, "exception-worker-cleanup");

            CountDownLatch started = new CountDownLatch(1), finished = new CountDownLatch(1);
            Future<Result> cancelled = MirrorTaintThreadAdapter.submit(workers, () -> {
                started.countDown();
                try { new CountDownLatch(1).await(); return null; } finally { finished.countDown(); }
            });
            check("cancellation-started", started.await(5, TimeUnit.SECONDS));
            boolean cancelledSuccessfully = cancelled.cancel(true);
            boolean cancellation = false;
            try { cancelled.get(); } catch (CancellationException expected) { cancellation = true; }
            check("cancellation-preserved", cancelledSuccessfully && cancellation && finished.await(5, TimeUnit.SECONDS));
            cleanWorkers(workers, "cancel-worker-cleanup");

            Map<Object, com.shadow.taint.agent.model.A> ownerA = TaintHeap.A.get();
            Map<Object, Map<String, com.shadow.taint.agent.model.A>> ownerB = TaintHeap.B.get();
            Future<Result> oldContext = MirrorTaintThreadAdapter.submit(workers, () -> calculate(a, b));
            TaintHeap.startup();
            boolean rejected = false;
            try { oldContext.get(5, TimeUnit.SECONDS); } catch (IllegalStateException expected) { rejected = true; }
            check("cross-context-get-rejected", rejected);
            TaintHeap.A.set(ownerA); TaintHeap.B.set(ownerB);
            check("parent-context-still-available", TaintHeap.available());
            cleanWorkers(workers, "final-worker-cleanup");
        } finally {
            TaintHeap.shutdown(); workers.shutdownNow(); callers.shutdownNow();
        }
    }
}
