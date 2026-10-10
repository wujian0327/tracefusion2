package upstream;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.apache.commons.lang3.math.NumberUtils;

/** Harness only. The NumberUtils implementation comes directly from the release JAR. */
public final class CommonsDriver {
    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Path.of(args[1]));
        int[][] inputs = new int[lines.size()][3];
        for (int i = 0; i < inputs.length; i++) {
            String[] fields = lines.get(i).split(",");
            for (int j = 0; j < 3; j++) inputs[i][j] = Integer.parseInt(fields[j]);
        }
        long checksum = 0;
        for (int repeat = 0; repeat < Integer.parseInt(args[2]); repeat++) {
            for (int[] v : inputs) {
                if (args[0].equals("max")) checksum += NumberUtils.max(v[0], v[1], v[2]);
                else if (args[0].equals("min")) checksum += NumberUtils.min(v[0], v[1], v[2]);
                else if (args[0].equals("array-max")) checksum += NumberUtils.max(v);
                else throw new IllegalArgumentException(args[0]);
            }
        }
        System.out.println(checksum);
    }
}
