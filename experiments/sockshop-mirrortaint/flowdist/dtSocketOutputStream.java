package disttaint;

import java.io.IOException;
import java.io.OutputStream;

/** Preserve the author wire header, using the method-event monitor's clock. */
public final class dtSocketOutputStream extends OutputStream {
    public static boolean intercept=true;
    public static void __link() {}
    private final OutputStream out;
    public dtSocketOutputStream(OutputStream out) { this.out=out; }
    @Override public synchronized void write(byte[] b,int off,int len) throws IOException {
        if (b==null) throw new NullPointerException();
        if (off<0 || len<0 || off>b.length-len) throw new IndexOutOfBoundsException();
        if (len==0) return;
        if (len>64*1024*1024-4108) throw new IOException("FlowDist adapter payload exceeds frame limit");
        if (intercept) OTMonitor.g_lgclock.packClock(out,len);
        out.write(b,off,len);
    }
    @Override public void write(byte[] b) throws IOException { write(b,0,b.length); }
    @Override public synchronized void write(int b) throws IOException {
        if (intercept) OTMonitor.g_lgclock.packClock(out,1);
        out.write(b);
    }
    @Override public void flush() throws IOException { out.flush(); }
    @Override public void close() throws IOException { out.close(); }
}
