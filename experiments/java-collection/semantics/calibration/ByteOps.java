package calibration;

/** Semantic gates, not an upstream application or performance workload. */
public final class ByteOps {
    public static int select(byte[] left, byte[] right, int which) {
        if (which != 0) return left[0];
        return right[0];
    }
    public static int lookup(byte[] bytes, int key) {
        switch (key) {
            case -3: return bytes[0];
            case 7: return bytes[1];
            case 1000: return bytes[2];
            default: return bytes[3];
        }
    }
    public static int store(byte[] bytes) { bytes[0] = 1; return bytes[0]; }
}
