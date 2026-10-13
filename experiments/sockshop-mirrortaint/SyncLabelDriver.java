package syncprobe;

import com.google.gson.Gson;
import com.shadow.taint.agent.runtime.TaintHeap;
import com.shadow.taint.agent.runtime.TaintTagger;
import com.shadow.taint.agent.runtime.TaintCollector;
import java.util.LinkedHashMap;
import java.util.Map;
import works.weave.socks.calibration.SyncLabelOps;
import works.weave.socks.calibration.SyncLabelOps.Item;
import works.weave.socks.calibration.SyncLabelOps.Result;

/** Uninstrumented fixture/oracle driver. Does not write or synthesize result labels. */
public final class SyncLabelDriver {
    private static void snapshot(String stage, Object object) throws Exception {
        Map<String, Object> fields = new LinkedHashMap<>();
        for (java.lang.reflect.Field field : object.getClass().getDeclaredFields()) {
            if (java.lang.reflect.Modifier.isStatic(field.getModifiers())) continue;
            field.setAccessible(true);
            Map<String, Object> data = new LinkedHashMap<>();
            Object value = field.get(object);
            data.put("value", value);
            data.put("tag", field.getType().isPrimitive()
                ? TaintHeap.queryPrimitiveFieldTaint(object, field.getName())
                : TaintHeap.queryTaint(value));
            fields.put(field.getName(), data);
        }
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("stage", stage);
        record.put("available", TaintHeap.available());
        record.put("fields", fields);
        System.out.println("TF2_SYNC_SNAPSHOT " + new Gson().toJson(record));
    }

    public static void main(String[] args) throws Exception {
        TaintHeap.startup();
        try {
            Item a = new Item();
            a.name = new String("same-content"); a.quantity = 2; a.unitPrice = 5.0F;
            Item b = new Item();
            b.name = new String("same-content"); b.quantity = 2; b.unitPrice = 5.0F;
            TaintTagger.tagDbQueryResult("fixture.rpc", "item-a", a);
            TaintTagger.tagDbQueryResult("fixture.rpc", "item-b", b);
            snapshot("source-a", a);
            snapshot("source-b", b);
            Result result = new Result();
            SyncLabelOps.copy(a, result);
            snapshot("copy-a", result);
            TaintCollector.collect("syncprobe", "copy-a", (Object) result);
            SyncLabelOps.amount(a, b, result);
            snapshot("sum-a-b", result);
            TaintCollector.collect("syncprobe", "sum-a-b", (Object) result);
            SyncLabelOps.combineNames(a, b, result);
            snapshot("combine-names", result);
            TaintCollector.collect("syncprobe", "combine-names", (Object) result);
            SyncLabelOps.overwrite(b, result);
            snapshot("overwrite-b", result);
            TaintCollector.collect("syncprobe", "overwrite-b", (Object) result);
            SyncLabelOps.AccessorItem c = new SyncLabelOps.AccessorItem(new String("same-content"), 2, 5.0F);
            SyncLabelOps.AccessorItem d = new SyncLabelOps.AccessorItem(new String("same-content"), 2, 5.0F);
            TaintTagger.tagDbQueryResult("fixture.rpc", "item-c", c);
            TaintTagger.tagDbQueryResult("fixture.rpc", "item-d", d);
            snapshot("source-c", c);
            snapshot("source-d", d);
            SyncLabelOps.AccessorResult accessorResult = new SyncLabelOps.AccessorResult();
            SyncLabelOps.copyAccessors(c, accessorResult);
            snapshot("accessor-copy-c", accessorResult);
            SyncLabelOps.amountAccessors(c, d, accessorResult);
            snapshot("accessor-sum-c-d", accessorResult);
            TaintCollector.collect("syncprobe", "accessor-sum-c-d", (Object) accessorResult);
            Result stream = new Result();
            SyncLabelOps.streamAmount(java.util.Arrays.asList(a, b), stream);
            snapshot("stream-a-b", stream);
            SyncLabelOps.streamAmount(java.util.Collections.emptyList(), stream);
            snapshot("stream-empty", stream);
        } finally {
            TaintHeap.shutdown();
        }
    }
}
