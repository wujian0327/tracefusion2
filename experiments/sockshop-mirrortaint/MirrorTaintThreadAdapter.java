import com.shadow.taint.agent.model.A;
import com.shadow.taint.agent.model.H;
import com.shadow.taint.agent.runtime.TaintHeap;
import java.util.*;
import java.util.concurrent.*;

/** Explicit per-task heap capture and reachable-result return; no global heap or value matching. */
public final class MirrorTaintThreadAdapter {
    private static final class Heap {
        final Map<Object, A> objects = new IdentityHashMap<>();
        final Map<Object, Map<String, A>> fields = new IdentityHashMap<>();
        Heap(Map<Object, A> objects, Map<Object, Map<String, A>> fields) {
            if (objects != null) for (Map.Entry<Object, A> e : objects.entrySet())
                this.objects.put(e.getKey(), cloneTag(e.getValue()));
            if (fields != null) for (Map.Entry<Object, Map<String, A>> e : fields.entrySet())
                this.fields.put(e.getKey(), cloneFields(e.getValue()));
        }
    }

    private static A cloneTag(A tag) { return tag == null ? null : tag.E(); }
    private static Map<String, A> cloneFields(Map<String, A> fields) {
        Map<String, A> copy = new HashMap<>();
        for (Map.Entry<String, A> e : fields.entrySet()) copy.put(e.getKey(), cloneTag(e.getValue()));
        return copy;
    }

    private static final class ReturnedHeap {
        Heap value;
    }

    public static <T> Future<T> submit(Executor executor, Callable<T> task) {
        if (executor == null || task == null) throw new NullPointerException();
        Map<Object, A> ownerObjects = TaintHeap.available() ? TaintHeap.A.get() : null;
        Map<Object, Map<String, A>> ownerFields = TaintHeap.available() ? TaintHeap.B.get() : null;
        if (ownerObjects == null) {
            FutureTask<T> plain = new FutureTask<>(task);
            executor.execute(plain);
            return plain;
        }
        Heap captured = new Heap(ownerObjects, ownerFields);
        ReturnedHeap returned = new ReturnedHeap();
        Callable<T> managed = () -> {
            Map<Object, A> previousObjects = TaintHeap.A.get();
            Map<Object, Map<String, A>> previousFields = TaintHeap.B.get();
            H previousRegister = com.shadow.taint.agent.runtime.A.A.get();
            Object previousLog = Boolean.getBoolean("tf2.mt.logging") ? MirrorTaintLogAdapter.beginTask() : null;
            TaintHeap.A.set(captured.objects);
            TaintHeap.B.set(captured.fields);
            com.shadow.taint.agent.runtime.A.A.remove();
            try {
                T answer = task.call();
                returned.value = reachableHeap(answer);
                return answer;
            } finally {
                if (previousLog != null) MirrorTaintLogAdapter.endTask(previousLog);
                if (previousObjects == null) TaintHeap.A.remove(); else TaintHeap.A.set(previousObjects);
                if (previousFields == null) TaintHeap.B.remove(); else TaintHeap.B.set(previousFields);
                if (previousRegister == null) com.shadow.taint.agent.runtime.A.A.remove();
                else com.shadow.taint.agent.runtime.A.A.set(previousRegister);
            }
        };
        FutureTask<T> future = new FutureTask<T>(managed) {
            private T receive(T answer) {
                if (TaintHeap.A.get() != ownerObjects || TaintHeap.B.get() != ownerFields)
                    throw new IllegalStateException("Future labels requested outside the submitting taint context");
                if (returned.value != null) {
                    for (Map.Entry<Object, A> e : returned.value.objects.entrySet())
                        ownerObjects.put(e.getKey(), cloneTag(e.getValue()));
                    for (Map.Entry<Object, Map<String, A>> e : returned.value.fields.entrySet())
                        ownerFields.put(e.getKey(), cloneFields(e.getValue()));
                }
                return answer;
            }
            public T get() throws InterruptedException, ExecutionException { return receive(super.get()); }
            public T get(long timeout, TimeUnit unit) throws InterruptedException, ExecutionException, TimeoutException {
                return receive(super.get(timeout, unit));
            }
        };
        executor.execute(future);
        return future;
    }

    private static Heap reachableHeap(Object root) throws Exception {
        Map<Object, A> objects = new IdentityHashMap<>();
        Map<Object, Map<String, A>> fields = new IdentityHashMap<>();
        Set<Object> seen = Collections.newSetFromMap(new IdentityHashMap<Object, Boolean>());
        Deque<Object> pending = new ArrayDeque<>();
        if (root != null) pending.add(root);
        while (!pending.isEmpty()) {
            Object object = pending.removeFirst();
            if (!seen.add(object)) continue;
            if (seen.size() > 100000) throw new IllegalStateException("Returned graph exceeds adapter capture limit");
            A tag = TaintHeap.queryTaint(object);
            if (tag != null) objects.put(object, tag);
            Map<String, A> fieldTags = TaintHeap.B.get().get(object);
            if (fieldTags != null) fields.put(object, fieldTags);
            Class<?> type = object.getClass();
            if (type.isArray()) {
                if (!type.getComponentType().isPrimitive()) for (Object item : (Object[]) object) add(pending, item);
            } else if (object instanceof Collection) {
                for (Object item : (Collection<?>) object) add(pending, item);
            } else if (object instanceof Map) {
                for (Map.Entry<?, ?> entry : ((Map<?, ?>) object).entrySet()) {
                    add(pending, entry.getKey()); add(pending, entry.getValue());
                }
            } else if (!type.getName().startsWith("java.") && !type.isEnum()) {
                for (Class<?> current = type; current != null && current != Object.class; current = current.getSuperclass()) {
                    for (java.lang.reflect.Field field : current.getDeclaredFields()) {
                        if (java.lang.reflect.Modifier.isStatic(field.getModifiers()) || field.getType().isPrimitive()) continue;
                        field.setAccessible(true);
                        add(pending, field.get(object));
                    }
                }
            }
        }
        return new Heap(objects, fields);
    }
    private static void add(Deque<Object> pending, Object value) { if (value != null) pending.add(value); }
}
