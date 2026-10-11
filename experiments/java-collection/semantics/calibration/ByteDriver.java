package calibration;

public final class ByteDriver {
    public static void main(String[] args) {
        byte[] a = {17, 17, 17, 17}, b = {17, 17, 17, 17};
        if (args[0].equals("distinct")) System.out.println(ByteOps.select(a, b, 0));
        else if (args[0].equals("alias")) System.out.println(ByteOps.select(a, a, 0));
        else if (args[0].equals("store")) System.out.println(ByteOps.store(a));
        else System.out.println(ByteOps.lookup(a, Integer.parseInt(args[0])));
    }
}
