import java.lang.reflect.Method;
import java.util.Arrays;
import works.weave.socks.orders.controllers.OrdersController;
import works.weave.socks.orders.entities.Item;

/** Execute the original private calculation with a nonzero and a zero product. */
public final class ZeroCallbackDriver {
    public static void main(String[] args) throws Exception {
        Method calculate = OrdersController.class.getDeclaredMethod("calculateTotal", java.util.List.class);
        calculate.setAccessible(true);
        Object result = calculate.invoke(new OrdersController(), Arrays.asList(
            new Item("paid-record", "paid-item", 2, 5F),
            new Item("zero-record", "zero-item", 3, 0F)));
        System.out.println("TF2_ZERO_CONTROL_RESULT " + result);
    }
}
