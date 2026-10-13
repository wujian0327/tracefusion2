import disttaint.OTBetterInstr;
import dua.Forensics;
import soot.Scene;

/** Use the original selected-method instrumenter and original lifecycle probes.
 * Its inline entry-method flush still happens when Spring main returns; the
 * original shutdown hook later writes the business-event Local trace.
 */
public final class FlowDistServiceMethodLauncher extends OTBetterInstr {
    public static void main(String[] args) {
        args=preProcessArgs(opts,args);
        dua.Options.ignoreCatchBlocks=false;
        Scene.v().addBasicClass("disttaint.OTMonitor");
        Forensics.registerExtension(new FlowDistServiceMethodLauncher());
        Forensics.main(args);
    }
}
