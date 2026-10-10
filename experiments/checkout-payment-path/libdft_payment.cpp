// Diagnostic adapter for pinned AngoraFuzzer/libdft64, not a qualified benchmark.
// Only source tagging and sink reading are ours; propagation stays in libdft64.
#include "pin.H"
#include "libdft_api.h"
#include "tagmap.h"
#include "libdft_known_opcodes.h"
#include <fstream>
#include <map>
#include <set>
#include <vector>

extern ins_desc_t ins_desc[XED_ICLASS_LAST];
KNOB<std::string> Config(KNOB_MODE_WRITEONCE, "pintool", "boundary_config", "", "verified boundary PCs");
KNOB<std::string> Output(KNOB_MODE_WRITEONCE, "pintool", "origin_log", "", "JSONL diagnostic output");
static std::map<ADDRINT, unsigned> sites;
static std::ofstream log_file;
static PIN_LOCK lock;
static ADDRINT owner_g = 0, source_sp = 0;
static THREADID owner_tid;
static unsigned source_hits = 0, sink_hits = 0, end_hits = 0;
static bool active = false, prep_error = false, bad = false;
static std::set<UINT32> missing;
struct Source { ADDRINT pointer; INT64 units; INT32 nanos; };
static std::vector<Source> sources;

static void fail(const char *reason) {
    bad = true;
    log_file << "{\"kind\":\"error\",\"reason\":\"" << reason << "\"}" << std::endl;
}

template<typename T> static T read_at(ADDRINT address) {
    T result = 0;
    if (!address || PIN_SafeCopy(&result, reinterpret_cast<const void *>(address), sizeof(T)) != sizeof(T))
        fail("short_or_invalid_memory_read");
    return result;
}

static void add_source(ADDRINT address) {
    if (!address) { fail("nil_source"); return; }
    for (size_t i = 0; i < sources.size(); ++i)
        if (sources[i].pointer == address) { fail("aliased_source"); return; }
    Source s = { address, read_at<INT64>(address + 56), read_at<INT32>(address + 64) };
    unsigned id = 1 + 2 * sources.size();
    sources.push_back(s);
    tagmap_setn(address + 56, 8, tag_alloc<tag_t>(id));
    tagmap_setn(address + 64, 4, tag_alloc<tag_t>(id + 1));
    log_file << "{\"kind\":\"source_field_pair\",\"index\":" << sources.size() - 1
             << ",\"pointer\":" << address << ",\"units\":" << s.units << ",\"nanos\":" << s.nanos << "}" << std::endl;
}

static void write_tags(ADDRINT address, unsigned width) {
    // Do not compare numeric values to determine origins.
    std::vector<tag_seg> segments = tag_get(tagmap_getn(address, width));
    std::set<unsigned> labels;
    for (size_t i = 0; i < segments.size(); ++i) {
        if (segments[i].begin == 0 || segments[i].end > 1 + 2 * sources.size() || segments[i].end < segments[i].begin) {
            // This line is completed before a separate error is emitted by the caller.
            bad = true;
            continue;
        }
        for (unsigned n = segments[i].begin; n < segments[i].end; ++n) labels.insert(n);
    }
    log_file << "[";
    bool first = true;
    for (std::set<unsigned>::const_iterator it = labels.begin(); it != labels.end(); ++it) {
        if (!first) log_file << ",";
        log_file << *it;
        first = false;
    }
    log_file << "]";
}

static VOID observe(THREADID tid, const CONTEXT *ctx, ADDRINT pc, UINT32 opcode, UINT32 role, BOOL covered) {
    PIN_GetLock(&lock, tid + 1);
    ADDRINT g = PIN_GetContextReg(ctx, REG_R14);
    if (role == 1) {
        ++source_hits;
        if (source_hits != 1 || !g) fail("multiple_invocations_or_missing_g");
        owner_g = g; owner_tid = tid;
        source_sp = PIN_GetContextReg(ctx, REG_RSP);
        prep_error = PIN_GetContextReg(ctx, REG_R10) != 0;
        active = !prep_error;
        log_file << "{\"kind\":\"source_boundary\",\"g\":" << g << ",\"tid\":" << tid
                 << ",\"preparation_error\":" << (prep_error ? "true" : "false") << "}" << std::endl;
        if (active && !bad) {
            ADDRINT count = PIN_GetContextReg(ctx, REG_RBX);
            ADDRINT items = PIN_GetContextReg(ctx, REG_RAX);
            if (count > 32) fail("source_count_exceeds_32");
            else {
                add_source(PIN_GetContextReg(ctx, REG_R9));
                for (ADDRINT i = 0; i < count && !bad; ++i) {
                    ADDRINT item = read_at<ADDRINT>(items + 8 * i);
                    if (!item) { fail("nil_order_item"); break; }
                    add_source(read_at<ADDRINT>(item + 48));
                }
            }
        }
    }
    if (active && g == owner_g) {
        if (tid != owner_tid) { fail("goroutine_thread_migration_unqualified"); active = false; }
        if (!covered && missing.insert(opcode).second)
            log_file << "{\"kind\":\"unhandled_opcode\",\"opcode\":" << opcode << ",\"pc\":" << pc << "}" << std::endl;
    }
    if (role == 2 && g == owner_g) {
        ++sink_hits;
        if (!active || prep_error || sink_hits != 1) fail("invalid_sink_sequence");
        if (PIN_GetContextReg(ctx, REG_RSP) != source_sp) fail("caller_stack_relocation_unqualified");
        for (size_t i = 0; i < sources.size(); ++i)
            if (read_at<INT64>(sources[i].pointer + 56) != sources[i].units ||
                read_at<INT32>(sources[i].pointer + 64) != sources[i].nanos) fail("source_numeric_values_changed");
        ADDRINT amount = PIN_GetContextReg(ctx, REG_RDI);
        INT64 units = read_at<INT64>(amount ? amount + 56 : 0);
        INT32 nanos = read_at<INT32>(amount ? amount + 64 : 0);
        if (!bad && amount) {
            log_file << "{\"kind\":\"sink\",\"output\":[" << units << "," << nanos << "],\"Units\":";
            write_tags(amount + 56, 8);
            log_file << ",\"Nanos\":";
            write_tags(amount + 64, 4);
            log_file << "}" << std::endl;
        }
        active = false;
    }
    if (role == 3 && g == owner_g && source_hits) {
        ++end_hits;
        if (end_hits != 1 || (!prep_error && sink_hits != 1)) fail("invalid_return_sequence");
        active = false;
    }
    PIN_ReleaseLock(&lock);
}

static VOID instrument(INS ins) {
    ADDRINT pc = INS_Address(ins);
    std::map<ADDRINT, unsigned>::const_iterator it = sites.find(pc);
    UINT32 role = it == sites.end() ? 0 : it->second;
    // Called by libdft's pre-instrumentation API, before its taint callbacks.
    // Expensive per-instruction diagnostic: NEVER a performance configuration.
    INS_InsertCall(ins, IPOINT_BEFORE, AFUNPTR(observe), IARG_CALL_ORDER, CALL_ORDER_FIRST,
                   IARG_THREAD_ID, IARG_CONST_CONTEXT, IARG_ADDRINT, pc,
                   IARG_UINT32, INS_Opcode(ins), IARG_UINT32, role,
                   IARG_BOOL, known_opcode(INS_Opcode(ins)), IARG_END);
}

static VOID finish(INT32 code, VOID *) {
    log_file << "{\"kind\":\"finish\",\"exit_code\":" << code << ",\"source_hits\":" << source_hits
             << ",\"sink_hits\":" << sink_hits << ",\"end_hits\":" << end_hits
             << ",\"bad\":" << (bad ? "true" : "false") << ",\"unhandled_opcode_kinds\":" << missing.size()
             << ",\"performance_eligible\":false}" << std::endl;
    log_file.close();
}

int main(int argc, char **argv) {
    PIN_InitSymbols();
    if (PIN_Init(argc, argv)) return 1;
    std::ifstream input(Config.Value().c_str());
    unsigned role; ADDRINT pc;
    while (input >> role >> std::hex >> pc >> std::dec) sites[pc] = role;
    if (sites.size() < 3) return 2;
    log_file.open(Output.Value().c_str());
    if (!log_file) return 3;
    PIN_InitLock(&lock);
    if (libdft_init()) return 4;
    // No hook_file_syscall(): only our declared price/shipping sources get tags.
    for (unsigned i = 0; i < XED_ICLASS_LAST; ++i) ins_set_pre(&ins_desc[i], instrument);
    PIN_AddFiniFunction(finish, 0);
    PIN_StartProgram();
    return 0;
}
