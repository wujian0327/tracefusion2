package demo;
/** Unmodified business methods: no tracing API, labels, or expected answers. */
public final class Subject {
    public static int choose(Cell left, Cell right, int pick) {
        if (pick != 0) return left.value;
        return right.value;
    }
    public static int overwrite(Cell left, Cell right) {
        left.value = right.value;
        return left.value;
    }
    public static int twice(int value) { return value * 2; }
    public static int nested(Cell left, Cell right, int pick) {
        return twice(choose(left, right, pick));
    }
    public static int sum(Cell left, Cell right, int count) {
        int total = left.value;
        for (int i = 0; i < count; i++) total += right.value;
        return total;
    }
}
