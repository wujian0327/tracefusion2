package demo;
public final class Unsupported {
    public static int array(int[] values) { return values[0]; }
    public static final class External {
        public static int abs(int value) { return Math.abs(value); }
    }
    public static final class Handler {
        public static int divide(int value) {
            try { return 1 / value; } catch (ArithmeticException e) { return 0; }
        }
    }
    public static final class VolatileCell { public volatile int value = 17; }
    public static final class VolatileRead {
        public static int read(VolatileCell cell) { return cell.value; }
    }
}
