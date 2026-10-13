import disttaint.OTMonitor;
import disttaint.dtSocketInputStream;
import disttaint.dtSocketOutputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.InputStream;
import java.io.IOException;
import java.util.Arrays;

/** Exercise TCP fragmentation, coalescing and simultaneous input streams. */
public final class FlowDistSocketProtocolTest {
    private static int passed;
    private static byte[] frame(byte[] payload) throws Exception {
        ByteArrayOutputStream raw=new ByteArrayOutputStream();
        new dtSocketOutputStream(raw).write(payload);
        return raw.toByteArray();
    }
    private static void check(boolean yes,String name) {
        if (!yes) throw new AssertionError(name);
        passed++;
    }
    private static byte[] drain(InputStream in) throws Exception {
        ByteArrayOutputStream b=new ByteArrayOutputStream();byte[] buf=new byte[1024];int n;
        while ((n=in.read(buf))!=-1) { if (n==0) throw new AssertionError("nonempty read returned zero");b.write(buf,0,n); }
        return b.toByteArray();
    }
    public static void main(String[] args) throws Exception {
        OTMonitor.initialize();
        byte[] one={0,1,2,3,4},two={8,9,10};
        byte[] f1=frame(one),f2=frame(two);
        ByteArrayOutputStream joined=new ByteArrayOutputStream();joined.write(f1);joined.write(f2);
        check(Arrays.equals(drain(new dtSocketInputStream(new ByteArrayInputStream(joined.toByteArray()))),new byte[]{0,1,2,3,4,8,9,10}),"coalesced frames must not expose headers");
        InputStream fragmented=new ByteArrayInputStream(f1) {
            @Override public synchronized int read(byte[] b,int off,int len) { return super.read(b,off,Math.min(len,1)); }
        };
        check(Arrays.equals(drain(new dtSocketInputStream(fragmented)),one),"fragmented header/payload");
        dtSocketInputStream a=new dtSocketInputStream(new ByteArrayInputStream(f1));
        dtSocketInputStream b=new dtSocketInputStream(new ByteArrayInputStream(f2));
        check(a.read()==0 && b.read()==8 && a.read()==1 && b.read()==9,"remaining bytes must be per stream, zero payload byte is valid");
        ByteArrayOutputStream single=new ByteArrayOutputStream();new dtSocketOutputStream(single).write(0);
        check(Arrays.equals(drain(new dtSocketInputStream(new ByteArrayInputStream(single.toByteArray()))),new byte[]{0}),"single byte framing");
        dtSocketInputStream empty=new dtSocketInputStream(new ByteArrayInputStream(new byte[0]));
        check(empty.read(new byte[1],0,0)==0 && empty.read()==-1,"zero-length read and clean EOF");
        try { drain(new dtSocketInputStream(new ByteArrayInputStream(Arrays.copyOf(f1,3))));throw new AssertionError("truncated header accepted"); }
        catch (EOFException expected) { passed++; }
        dtSocketInputStream skipped=new dtSocketInputStream(new ByteArrayInputStream(f1));
        check(skipped.skip(2)==2 && skipped.read()==2,"skip consumes payload, not metadata");
        dtSocketInputStream zeroRead=new dtSocketInputStream(new ByteArrayInputStream(f1));
        check(zeroRead.read(new byte[1],0,0)==0 && zeroRead.read()==0,"zero-length read must not consume frame metadata");
        try { drain(new dtSocketInputStream(new ByteArrayInputStream(Arrays.copyOf(f1,f1.length-1))));throw new AssertionError("truncated payload accepted"); }
        catch (EOFException expected) { passed++; }
        byte[] invalid=f1.clone();Arrays.fill(invalid,0,4,(byte)255);
        try { drain(new dtSocketInputStream(new ByteArrayInputStream(invalid)));throw new AssertionError("invalid frame reported as clean EOF"); }
        catch (IOException expected) { passed++; }
        System.out.println("FLOWDIST_PROTOCOL_TESTS passed="+passed);
    }
}
