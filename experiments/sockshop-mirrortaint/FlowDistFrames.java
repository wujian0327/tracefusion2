import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;
import java.util.Arrays;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;

/** Recompute verifier frames from unchanged Soot instructions and exception tables.
 * Run with Java 8 and the complete original application/dependency classpath.
 * Missing hierarchy classes cause failure; never substitute Object silently.
 */
public final class FlowDistFrames {
    private static byte[] withoutFrames(byte[] bytes) {
        ClassWriter canonical=new ClassWriter(ClassWriter.COMPUTE_MAXS);
        new ClassReader(bytes).accept(canonical,ClassReader.SKIP_FRAMES);
        return canonical.toByteArray();
    }
    public static void main(String[] args) throws Exception {
        Path input = Paths.get(args[0]), output = Paths.get(args[1]);
        int count = 0;
        try (Stream<Path> paths = Files.walk(input)) {
            for (Path file : (Iterable<Path>)paths.filter(Files::isRegularFile)::iterator) {
                Path target = output.resolve(input.relativize(file));
                Files.createDirectories(target.getParent());
                byte[] bytes = Files.readAllBytes(file);
                if (file.toString().endsWith(".class")) {
                    ClassReader reader = new ClassReader(bytes);
                    ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
                    reader.accept(writer, ClassReader.SKIP_FRAMES);
                    byte[] repaired = writer.toByteArray();
                    if (!Arrays.equals(withoutFrames(bytes),withoutFrames(repaired)))
                        throw new IllegalStateException("Frame repair changed instructions or class data: " + file);
                    bytes = repaired;
                    count++;
                }
                Files.write(target, bytes);
            }
        }
        System.out.println("Recomputed Java 8 verifier frames for " + count + " classes");
    }
}
