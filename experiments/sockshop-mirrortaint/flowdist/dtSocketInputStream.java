package disttaint;

import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/** Disclosed compatibility wrapper: author token format, OTMonitor clock,
 * complete header reads and per-stream payload accounting. */
public final class dtSocketInputStream extends InputStream {
    public static boolean debugOut=false,usingToken=true,intercept=true;
    public static void __link() {}
    private final InputStream in;
    private int remaining;
    public dtSocketInputStream(InputStream in) { this.in=in; }

    private void readFully(byte[] b) throws IOException {
        int off=0;
        while (off<b.length) {
            int n=in.read(b,off,b.length-off);
            if (n<0) throw new EOFException("FlowDist metadata truncated");
            if (n==0) { int one=in.read();if (one<0) throw new EOFException("FlowDist metadata truncated");b[off++]=(byte)one; }
            else off+=n;
        }
    }
    private long readWord(boolean allowEof) throws IOException {
        int first=in.read();
        if (first<0) { if (allowEof) return -1;throw new EOFException("FlowDist header truncated"); }
        byte[] rest=new byte[3];readFully(rest);
        long value=first;
        for (int i=1;i<4;i++) value |= (long)(rest[i-1]&255) << (i*8);
        return value;
    }
    private boolean nextFrame() throws IOException {
        if (!usingToken) throw new IOException("Adapter requires FlowDist token framing");
        while (remaining==0) {
            long totalValue=readWord(true);
            if (totalValue==-1) return false;
            long clockValue=readWord(false),sizeValue=readWord(false);
            if (totalValue<12 || totalValue>64*1024*1024 || sizeValue<1 || sizeValue>4096 || sizeValue>totalValue-12 || clockValue>Integer.MAX_VALUE)
                throw new IOException("Invalid FlowDist frame header");
            int total=(int)totalValue,clock=(int)clockValue,size=(int)sizeValue;
            byte[] sender=new byte[size];
            readFully(sender);
            String id=new String(sender,StandardCharsets.UTF_8).trim();
            synchronized (OTMonitor.class) {
                OTMonitor.g_lgclock.updateClock(clock);
                // Same first-receive rule as OTMonitor.onRecvSenderID.
                if (!OTMonitor.S.containsKey(id)) OTMonitor.S.put(id,OTMonitor.g_lgclock.getLTS());
            }
            remaining=total-12-size;
        }
        return true;
    }
    @Override public int read() throws IOException {
        if (!intercept) return in.read();
        if (!nextFrame()) return -1;
        int b=in.read();if (b<0) throw new EOFException("FlowDist payload truncated");remaining--;return b;
    }
    @Override public int read(byte[] b,int off,int len) throws IOException {
        if (b==null) throw new NullPointerException();
        if (off<0 || len<0 || off>b.length-len) throw new IndexOutOfBoundsException();
        if (len==0) return 0;
        if (!intercept) return in.read(b,off,len);
        if (!nextFrame()) return -1;
        int n=in.read(b,off,Math.min(len,remaining));
        if (n<0) throw new EOFException("FlowDist payload truncated");
        if (n==0) { b[off]=(byte)read();return 1; }
        remaining-=n;return n;
    }
    @Override public long skip(long n) throws IOException {
        if (n<=0) return 0;
        long consumed=0;byte[] b=new byte[1024];
        while (consumed<n) { int got=read(b,0,(int)Math.min(b.length,n-consumed));if (got<0) break;consumed+=got; }
        return consumed;
    }
    @Override public int available() throws IOException { return intercept?Math.min(remaining,in.available()):in.available(); }
    @Override public void close() throws IOException { in.close(); }
}
