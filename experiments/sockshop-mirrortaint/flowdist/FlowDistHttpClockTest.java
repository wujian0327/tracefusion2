package disttaint;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

/** Validate that HTTP encoding retains the original Lamport/first-peer rule. */
public final class FlowDistHttpClockTest {
    private static void check(boolean value) {
        if (!value) throw new AssertionError();
    }
    public static void main(String[] args) throws Exception {
        OTMonitor.initialize();
        check(!FlowDistHttpClock.receive(null));
        String peer = "999@http-test-peer";
        String encoded = Base64.getUrlEncoder().withoutPadding().encodeToString(peer.getBytes(StandardCharsets.UTF_8));
        check(FlowDistHttpClock.receive("1:100:" + encoded));
        check(OTMonitor.g_lgclock.getLTS() == 101);
        int first = OTMonitor.S.get(peer);
        check(FlowDistHttpClock.receive("1:200:" + encoded));
        check(OTMonitor.g_lgclock.getLTS() == 201 && OTMonitor.S.get(peer) == first);
        check(FlowDistHttpClock.receive("1:1:" + encoded));
        check(OTMonitor.g_lgclock.getLTS() == 202);
        for (String malformed : new String[]{"", "2:1:" + encoded, "1:-1:" + encoded,
                "1:2147483647:" + encoded, "1:10:!", "1:10:"}) {
            int clock = OTMonitor.g_lgclock.getLTS();
            int size = OTMonitor.S.size();
            boolean rejected = false;
            try { FlowDistHttpClock.receive(malformed); }
            catch (IllegalArgumentException expected) { rejected = true; }
            check(rejected && clock == OTMonitor.g_lgclock.getLTS() && size == OTMonitor.S.size());
        }
        String sent = FlowDistHttpClock.send();
        check(sent.startsWith("1:202:") && sent.indexOf('\0') == -1);
        System.out.println("FLOWDIST_HTTP_CLOCK_CHECKS_PASSED");
        OTMonitor.terminate("HTTP clock checks completed");
    }
}
