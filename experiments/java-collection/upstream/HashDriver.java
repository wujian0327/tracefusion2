package upstream;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;
import org.apache.commons.codec.digest.MurmurHash2;

/** Input setup only; the hash implementation is loaded from the unchanged release JAR. */
public final class HashDriver {
    public static void main(String[] args) throws Exception {
        if (args[0].equals("null")) {
            System.out.println(MurmurHash2.hash32((byte[])null, 0, 17)); return;
        }
        if (args[0].equals("oversize")) {
            System.out.println(MurmurHash2.hash32(new byte[4097], 0, 17)); return;
        }
        if (args[0].equals("bounds")) {
            try { MurmurHash2.hash32(new byte[1], 4, 17); }
            catch (ArrayIndexOutOfBoundsException expected) { System.out.println("caught-bounds"); }
            return;
        }
        var lines = Files.readAllLines(Path.of(args[0]));
        long checksum = 0;
        for (int r = 0; r < Integer.parseInt(args[1]); r++) {
            for (String line : lines) {
                String[] parts = line.split(",", -1);
                byte[] bytes = HexFormat.of().parseHex(parts[0]); // Fresh identity for each invocation.
                checksum += MurmurHash2.hash32(bytes, Integer.parseInt(parts[1]), Integer.parseInt(parts[2]));
            }
        }
        System.out.println(checksum);
    }
}
