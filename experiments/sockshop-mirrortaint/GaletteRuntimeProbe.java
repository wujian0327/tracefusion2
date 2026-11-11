import edu.neu.ccs.prl.galette.internal.runtime.Tag;
import edu.neu.ccs.prl.galette.internal.runtime.Tainter;

/** Independent API smoke test, not a calibrated business source adapter. */
public final class GaletteRuntimeProbe {
    static final class Box { long value; }
    static Box published;
    public static void main(String[] args) {
        long a = Tainter.setTag(7L, Tag.of("read-1/field-a/version-1"));
        long b = Tainter.setTag(7L, Tag.of("read-2/field-b/version-1"));
        Tag sum = Tainter.getTag(a + b);
        if (sum == null || sum.size() != 2 || !sum.contains("read-1/field-a/version-1")
                || !sum.contains("read-2/field-b/version-1")) throw new AssertionError("distinct equal sources");
        Box box = new Box(); box.value = a;
        Box alias = box; alias.value = 7L;
        Tag overwritten = Tainter.getTag(box.value);
        if (overwritten != null && !overwritten.isEmpty()) throw new AssertionError("constant overwrite");
        published = box; published.value = b;
        Tag later = Tainter.getTag(box.value);
        if (later == null || later.size() != 1 || !later.contains("read-2/field-b/version-1"))
            throw new AssertionError("published alias write");
        System.out.println("GALETTE_RUNTIME_API_PROBE_OK");
    }
}
