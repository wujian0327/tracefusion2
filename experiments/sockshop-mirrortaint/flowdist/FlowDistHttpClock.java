package disttaint;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

/** Disclosed HTTP encoding of the original process clock and first-receive rule.
 * No trace/span ID or payload/value matching participates in correlation. */
public final class FlowDistHttpClock {
    public static final String HEADER = "X-FlowDist-Clock";
    private FlowDistHttpClock() {}
    public static String send() {
        synchronized (OTMonitor.class) {
            String process = OTMonitor.getProcessID().replace("\0", "");
            return "1:" + OTMonitor.g_lgclock.getLTS() + ":" +
                Base64.getUrlEncoder().withoutPadding().encodeToString(process.getBytes(StandardCharsets.UTF_8));
        }
    }
    public static boolean receive(String header) {
        if (header == null) return false;
        if (header.length() > 8192) throw new IllegalArgumentException("Oversized FlowDist header");
        String[] parts = header.split(":", -1);
        if (parts.length != 3 || !parts[0].equals("1") || !parts[1].matches("[0-9]{1,10}"))
            throw new IllegalArgumentException("Invalid FlowDist header");
        int clock = Integer.parseInt(parts[1]);
        if (clock == Integer.MAX_VALUE) throw new IllegalArgumentException("Clock overflow");
        byte[] bytes = Base64.getUrlDecoder().decode(parts[2]);
        String process = new String(bytes, StandardCharsets.UTF_8);
        if (bytes.length == 0 || bytes.length > 4096 || !process.matches("[0-9]+@[^\\s\\p{Cntrl}]+"))
            throw new IllegalArgumentException("Invalid process identity");
        synchronized (OTMonitor.class) {
            OTMonitor.g_lgclock.updateClock(clock);
            if (!OTMonitor.S.containsKey(process)) OTMonitor.S.put(process, OTMonitor.g_lgclock.getLTS());
        }
        return true;
    }
}
