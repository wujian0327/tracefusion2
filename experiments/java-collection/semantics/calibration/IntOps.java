package calibration;
/** JVM arithmetic calibration; not a new application benchmark. */
public final class IntOps {
    public static int add(int a, int b) { return a + b; }
    public static int sub(int a, int b) { return a - b; }
    public static int mul(int a, int b) { return a * b; }
    public static int div(int a, int b) { return a / b; }
    public static int rem(int a, int b) { return a % b; }
    public static int neg(int a) { return -a; }
    public static int shl(int a, int b) { return a << b; }
    public static int shr(int a, int b) { return a >> b; }
    public static int ushr(int a, int b) { return a >>> b; }
    public static int and(int a, int b) { return a & b; }
    public static int or(int a, int b) { return a | b; }
    public static int xor(int a, int b) { return a ^ b; }
    public static int asByte(int a) { return (byte)a; }
    public static int asChar(int a) { return (char)a; }
    public static int asShort(int a) { return (short)a; }
}
