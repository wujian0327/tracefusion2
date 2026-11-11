import edu.neu.ccs.prl.galette.internal.transform.GaletteTransformer;
import java.nio.file.Files;
import java.nio.file.Paths;

/** Diagnostic only: compare the official transform's two hosting contexts. */
public final class GaletteTemplateAnalysis {
    public static void main(String[] args) throws Exception {
        byte[] raw = Files.readAllBytes(Paths.get(args[0]));
        byte[] ordinary = new GaletteTransformer().transform(raw, false);
        byte[] hosted = new GaletteTransformer().transform(raw, true);
        if (ordinary == null || hosted == null) throw new AssertionError("raw template not transformed");
        Files.write(Paths.get(args[1], "ordinary.class"), ordinary);
        Files.write(Paths.get(args[1], "hosted.class"), hosted);
        byte[] again = new GaletteTransformer().transform(ordinary, true);
        Files.write(Paths.get(args[1], "ordinary-then-hosted.class"), again == null ? ordinary : again);
        System.out.println("already_instrumented_hosted_transform_returned_null=" + (again == null));
    }
}
