// Native emulation of BPF maps/helpers, not a verifier or kernel substitute.
#include <cassert>
#include <cstring>
#include <cstdint>
#include <map>
#include <vector>
#include <sys/syscall.h>
using u64=uint64_t;using u32=uint32_t;using u8=uint8_t;using s64=int64_t;using s32=int32_t;
struct pt_regs {u64 ax=0,bx=0,cx=0,dx=0,si=0,di=0,bp=0,sp=0,r8=0,r9=0,r10=0,r11=0,r12=0,r13=0,r14=0,r15=0,ip=0,flags=0,orig_ax=0;};
struct bpf_raw_tracepoint_args {u64 args[2];};
template<class K,class V,size_t N> struct Map {
    std::map<K,V> rows;bool fail_update=false;
    V *lookup(K *key) {auto i=rows.find(*key);return i==rows.end()?nullptr:&i->second;}
    int update(K *key,V *value) {if(fail_update || (rows.size()==N && !rows.count(*key)))return -1;rows[*key]=*value;return 0;}
    V *lookup_or_try_init(K *key,V *value) {auto p=lookup(key);if(p)return p;if(update(key,value))return nullptr;return lookup(key);}
    int erase(K *key) {rows.erase(*key);return 0;}
};
template<class V,size_t N> struct Array {
    V rows[N]{};V *lookup(u32 *key) {return *key<N?&rows[*key]:nullptr;}
};
template<class T> struct Perf {
    std::vector<T> rows;int perf_submit(void*,T *event,unsigned size){assert(size==sizeof(T));rows.push_back(*event);return 0;}
};
#define BPF_HASH(name,key,value,size) Map<key,value,size> name
#define BPF_ARRAY(name,value,size) Array<value,size> name
#define BPF_PERCPU_ARRAY(name,value,size) Array<value,size> name
#define BPF_PERF_OUTPUT(name) Perf<event_t> name
#define RAW_TRACEPOINT_PROBE(name) int raw_tracepoint__##name(struct bpf_raw_tracepoint_args *ctx)
#define PT_REGS_IP(ctx) ((ctx)->ip)
u64 current_tid=0,clock_tick=0;
u64 bpf_get_current_pid_tgid(){return current_tid;}
u64 bpf_ktime_get_ns(){return ++clock_tick;}
int bpf_probe_read_user(void *dst,u64 size,void *src){assert(src);std::memcpy(dst,src,size);return 0;}
int bpf_probe_read_kernel(void *dst,u64 size,void *src){assert(src);std::memcpy(dst,src,size);return 0;}
