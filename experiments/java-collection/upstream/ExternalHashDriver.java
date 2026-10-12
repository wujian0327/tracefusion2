package upstream;

import edu.neu.ccs.prl.galette.internal.runtime.Tag;
import edu.neu.ccs.prl.galette.internal.runtime.Tainter;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HexFormat;
import org.apache.commons.codec.digest.MurmurHash2;

/** Shared workload. Only source binding and return-tag extraction are tool-specific. */
public final class ExternalHashDriver {
    private static String labels(Tag tag) {
        Object[] objects = Tag.getLabels(tag);
        String[] strings = new String[objects.length];
        for (int i = 0; i < objects.length; i++) strings[i] = (String) objects[i];
        Arrays.sort(strings);
        return String.join(",", strings);
    }

    public static void main(String[] args) throws Exception {
        var lines = Files.readAllLines(Path.of(args[0]));
        int rounds = Integer.parseInt(args[1]);
        int warmup = Integer.parseInt(args[2]);
        boolean galette = args[3].equals("galette");
        boolean audit = args[4].equals("audit");
        var os = (com.sun.management.OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
        StringBuilder output = new StringBuilder();
        int root = 0;
        long wall = 0, cpu = 0;
        for (int round = 0; round < warmup + rounds; round++) {
            if (round == warmup) { cpu = os.getProcessCpuTime(); wall = System.nanoTime(); }
            for (String line : lines) {
                root++;
                String[] parts = line.split(",", -1);
                byte[] data = HexFormat.of().parseHex(parts[0]);
                int length = Integer.parseInt(parts[1]), seed = Integer.parseInt(parts[2]);
                if (galette) {
                    for (int i = 0; i < data.length; i++) {
                        data[i] = Tainter.setTag(data[i], Tag.of("r" + root + ".byte" + i));
                        if (audit) output.append("SOURCE\t").append(root).append("\tbyte")
                            .append(i).append('\t').append(data[i]).append('\t')
                            .append(labels(Tainter.getTag(data[i]))).append('\n');
                    }
                    length = Tainter.setTag(length, Tag.of("r" + root + ".length"));
                    seed = Tainter.setTag(seed, Tag.of("r" + root + ".seed"));
                    if (audit) {
                        output.append("SOURCE\t").append(root).append("\tlength\t").append(length)
                            .append('\t').append(labels(Tainter.getTag(length))).append('\n');
                        output.append("SOURCE\t").append(root).append("\tseed\t").append(seed)
                            .append('\t').append(labels(Tainter.getTag(seed))).append('\n');
                    }
                }
                int value = MurmurHash2.hash32(data, length, seed);
                String sources = galette ? labels(Tainter.getTag(value)) : "-";
                output.append("RESULT\t").append(root).append('\t').append(value)
                    .append('\t').append(sources).append('\n');
            }
        }
        wall = System.nanoTime() - wall;
        cpu = os.getProcessCpuTime() - cpu;
        System.out.print(output);
        System.out.println("WINDOW\t" + wall + "\t" + cpu + "\t" + (rounds * lines.size()));
    }
}
