package works.weave.socks.calibration;

/** Controlled synchronous operations instrumented by the unmodified public agent. */
public final class SyncLabelOps {
    public static final class Item {
        public String name;
        public int quantity;
        public float unitPrice;
    }

    public static final class Result {
        public String name;
        public int quantity;
        public float unitPrice;
        public float total;
        public String combined;
    }

    public static final class AccessorItem {
        private String name;
        private int quantity;
        private float unitPrice;
        public AccessorItem(String name, int quantity, float unitPrice) {
            this.name = name; this.quantity = quantity; this.unitPrice = unitPrice;
        }
        public String getName() { return name; }
        public int getQuantity() { return quantity; }
        public float getUnitPrice() { return unitPrice; }
    }

    public static final class AccessorResult {
        private String name;
        private int quantity;
        private float unitPrice;
        private float total;
        public void setName(String value) { name = value; }
        public void setQuantity(int value) { quantity = value; }
        public void setUnitPrice(float value) { unitPrice = value; }
        public void setTotal(float value) { total = value; }
    }

    public static void copyAccessors(AccessorItem input, AccessorResult output) {
        output.setName(input.getName());
        output.setQuantity(input.getQuantity());
        output.setUnitPrice(input.getUnitPrice());
    }

    public static void amountAccessors(AccessorItem first, AccessorItem second, AccessorResult output) {
        output.setTotal(first.getQuantity() * first.getUnitPrice()
            + second.getQuantity() * second.getUnitPrice() + 4.99F);
    }

    public static void copy(Item input, Result output) {
        output.name = input.name;
        output.quantity = input.quantity;
        output.unitPrice = input.unitPrice;
    }

    public static void amount(Item first, Item second, Result output) {
        output.total = first.quantity * first.unitPrice + second.quantity * second.unitPrice + 4.99F;
    }

    public static void overwrite(Item replacement, Result output) {
        output.name = replacement.name;
        output.quantity = replacement.quantity;
        output.unitPrice = replacement.unitPrice;
    }

    public static void combineNames(Item first, Item second, Result output) {
        output.combined = first.name + second.name;
    }

    public static void streamAmount(java.util.List<Item> items, Result output) {
        float amount = 0F;
        amount += items.stream().mapToDouble(i -> i.quantity * i.unitPrice).sum();
        amount += 4.99F;
        output.total = amount;
    }
}
