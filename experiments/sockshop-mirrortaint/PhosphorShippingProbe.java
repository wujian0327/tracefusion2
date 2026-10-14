import edu.columbia.cs.psl.phosphor.runtime.MultiTainter;
import edu.columbia.cs.psl.phosphor.runtime.Taint;
import edu.columbia.cs.psl.phosphor.struct.LinkedList;
import works.weave.socks.shipping.controllers.ShippingController;
import works.weave.socks.shipping.entities.Shipment;
import java.util.Arrays;
import java.util.Set;
import java.util.TreeSet;

/** Compatibility probes using original Shipping classes; not an HTTP benchmark.
 * No target is tagged. Labels are assigned only at the declared source boundary.
 * Shared-reference object-tag limitations are reported separately from failures.
 */
public final class PhosphorShippingProbe {
    private static int checks;

    private static Set<String> labels(Taint<?> tag) {
        Set<String> found = new TreeSet<String>();
        if (tag == null) return found;
        if (tag.getLabel() != null) found.add(tag.getLabel().toString());
        if (tag.getDependencies() != null) {
            LinkedList.Node<?> node = tag.getDependencies().getFirst();
            while (node != null) {
                if (node.entry != null) found.add(node.entry.toString());
                node = node.next;
            }
        }
        return found;
    }

    private static String source(String value, String label) {
        MultiTainter.taintedObject(value, new Taint<String>(label));
        return value;
    }

    private static void check(String name, Taint<?> actual, String... expected) {
        Set<String> want = new TreeSet<String>(Arrays.asList(expected));
        Set<String> found = labels(actual);
        if (!found.equals(want)) throw new AssertionError(name + ": expected " + want + ", got " + found);
        checks++;
        System.out.println("PROBE_PASS " + name + " " + found);
    }

    public static void main(String[] args) {
        int left = MultiTainter.taintedInt(7, "arithmetic-left");
        int right = MultiTainter.taintedInt(7, "arithmetic-right");
        check("computed-multi-source", MultiTainter.getTaint(left + right), "arithmetic-left", "arithmetic-right");
        ShippingController controller = new ShippingController();
        // The real controller catches the null RabbitTemplate here. This tests
        // its direct return path only; it does not qualify AMQP or Spring HTTP.
        Shipment reused = new Shipment();
        for (int request = 0; request < 2; request++) {
            String prefix = "request-" + request + ":";
            reused.setId(source(new String("equal-value"), prefix + "id-v1"));
            reused.setName(source(new String("equal-value"), prefix + "name-v1"));
            Shipment result = controller.postShipping(reused);
            if (result != reused) throw new AssertionError("Original controller return alias changed");
            check(prefix + "id", MultiTainter.getTaint(result.getId()), prefix + "id-v1");
            check(prefix + "name", MultiTainter.getTaint(result.getName()), prefix + "name-v1");
            String oldName = result.getName();
            reused.setName(source(new String("equal-value"), prefix + "name-v2"));
            Shipment overwritten = controller.postShipping(reused);
            check(prefix + "overwrite", MultiTainter.getTaint(overwritten.getName()), prefix + "name-v2");
            check(prefix + "old-reference", MultiTainter.getTaint(oldName), prefix + "name-v1");
            check(prefix + "unchanged-id", MultiTainter.getTaint(overwritten.getId()), prefix + "id-v1");
        }
        reused.setName(new String("equal-value"));
        check("untainted-overwrite", MultiTainter.getTaint(controller.postShipping(reused).getName()));
        // An object-wide tag API cannot represent two independent source-field
        // labels on the same String object. Report this gate instead of fixing
        // targets or silently cloning business data to obtain a desired answer.
        String shared = new String("shared-reference");
        Shipment aliased = new Shipment(shared, shared);
        source(aliased.getId(), "shared:id");
        source(aliased.getName(), "shared:name");
        Shipment aliasedResult = controller.postShipping(aliased);
        boolean idExact = labels(MultiTainter.getTaint(aliasedResult.getId())).equals(
            new TreeSet<String>(Arrays.asList("shared:id")));
        boolean nameExact = labels(MultiTainter.getTaint(aliasedResult.getName())).equals(
            new TreeSet<String>(Arrays.asList("shared:name")));
        System.out.println("PROBE_SHARED_REFERENCE field_labels_independent=" + (idExact && nameExact)
            + " id=" + labels(MultiTainter.getTaint(aliasedResult.getId()))
            + " name=" + labels(MultiTainter.getTaint(aliasedResult.getName())));
        System.out.println("PROBE_COMPLETE checks=" + checks + " scope=direct-controller-call");
    }
}
