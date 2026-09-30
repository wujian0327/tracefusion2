/* BCC socket filter. Observation only: returning 0 discards the observer's
 * packet copy, never application traffic. Constants are supplied by the runner.
 * Capture all TCP segments (including SYN/FIN), not just HTTP-looking packets. */
#include <uapi/linux/bpf.h>
#include <bcc/proto.h>

BPF_ARRAY(counters, u64, 2);

int capture_http(struct __sk_buff *skb) {
    if (load_half(skb, 12) != 0x0800) return 0;
    if ((load_byte(skb, 14) >> 4) != 4) return 0;
    if (load_byte(skb, 23) != 6) return 0;
    u32 src = load_word(skb, 26), dst = load_word(skb, 30);
    if (!(TF2_IP_FILTER)) return 0;
    u32 key = 1;
    if (load_half(skb, 20) & 0x3fff) {
        u64 *count = counters.lookup(&key);
        if (count) __sync_fetch_and_add(count, 1);
        return 0; /* IP fragmentation is explicitly unsupported. */
    }
    u32 ihl = (load_byte(skb, 14) & 15) * 4;
    if (ihl < 20) return 0;
    u16 sport = load_half(skb, 14 + ihl), dport = load_half(skb, 16 + ihl);
    if (sport != 80 && sport != 8079 && dport != 80 && dport != 8079) return 0;
    key = 0;
    u64 *count = counters.lookup(&key);
    if (count) __sync_fetch_and_add(count, 1);
    return skb->len;
}
