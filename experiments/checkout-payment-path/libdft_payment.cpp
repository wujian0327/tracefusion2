// Diagnostic adapter for pinned AngoraFuzzer/libdft64, not a qualified benchmark.
// Only source tagging and sink reading are ours; propagation stays in libdft64.
#include "pin.H"
#include "libdft_api.h"
#include "tagmap.h"
#include "ins_helper.h"
#include "libdft_known_opcodes.h"
#include <fstream>
#include <map>
#include <set>
#include <vector>

extern ins_desc_t ins_desc[XED_ICLASS_LAST];
KNOB<std::string> Config(KNOB_MODE_WRITEONCE, "pintool", "boundary_config", "", "verified boundary PCs");
KNOB<std::string> Output(KNOB_MODE_WRITEONCE, "pintool", "origin_log", "", "JSONL diagnostic output");
KNOB<std::string> FlowConfig(KNOB_MODE_WRITEONCE, "pintool", "flow_config", "", "diagnostic instruction PCs");
KNOB<std::string> FlowOutput(KNOB_MODE_WRITEONCE, "pintool", "flow_log", "", "byte-tag diagnostics only");
static std::map<ADDRINT, unsigned> sites;
static std::ofstream log_file;
static std::ofstream flow_file;
static std::set<ADDRINT> flow_pcs;
static std::set<tag_t> seen_tags;
static UINT64 flow_steps = 0;
static PIN_LOCK lock;
static ADDRINT owner_g = 0, source_sp = 0;
static THREADID owner_tid;
static unsigned source_hits = 0, sink_hits = 0, end_hits = 0;
static bool active = false, prep_error = false, bad = false;
static std::set<UINT32> missing;
struct Source { ADDRINT pointer; INT64 units; INT32 nanos; };
static std::vector<Source> sources;

static void raw_tags(ADDRINT address, THREADID tid, int reg, unsigned width) {
    flow_file << "[";
    for (unsigned i = 0; i < width; ++i) {
        tag_t t = reg < 0 ? tagmap_getb(address + i) : tagmap_getb_reg(tid, reg, i);
        if (i) flow_file << ",";
        flow_file << t;
        seen_tags.insert(t);
    }
    flow_file << "]";
}

static void source_tags(unsigned index, ADDRINT address) {
    if (!flow_file.is_open()) return;
    flow_file << "{\"kind\":\"source_tag_readback\",\"index\":" << index << ",\"Units\":";
    raw_tags(address + 56, 0, -1, 8);
    flow_file << ",\"Nanos\":";
    raw_tags(address + 64, 0, -1, 4);
    flow_file << "}" << std::endl;
}

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
    source_tags(sources.size() - 1, address);
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

static VOID trace_step(THREADID tid, const CONTEXT *ctx, ADDRINT pc) {
    PIN_GetLock(&lock, tid + 1);
    if (active && PIN_GetContextReg(ctx, REG_R14) == owner_g) {
        if (++flow_steps > 12000) {
            fail("flow_diagnostic_budget_exceeded");
            active = false;
        } else {
            const REG regs[] = {REG_RAX, REG_RBX, REG_RCX, REG_RDX, REG_RSI, REG_RDI, REG_RBP, REG_RSP,
                                REG_R8, REG_R9, REG_R10, REG_R11, REG_R12, REG_R13, REG_R14, REG_R15};
            const char *names[] = {"AX", "BX", "CX", "DX", "SI", "DI", "BP", "SP",
                                   "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15"};
            flow_file << "{\"kind\":\"before_instruction\",\"step\":" << flow_steps << ",\"pc\":" << pc
                      << ",\"tid\":" << tid << ",\"registers\":{";
            for (unsigned i = 0; i < 16; ++i) {
                if (i) flow_file << ",";
                flow_file << "\"" << names[i] << "\":{\"value\":" << PIN_GetContextReg(ctx, regs[i]) << ",\"tags\":";
                raw_tags(0, tid, REG_INDX(regs[i]), 8);
                flow_file << "}";
            }
            flow_file << ",\"X0\":{\"tags\":"; raw_tags(0, tid, DFT_REG_XMM0, 16);
            flow_file << "},\"X15\":{\"tags\":"; raw_tags(0, tid, DFT_REG_XMM15, 16);
            flow_file << "}}}" << std::endl;
        }
    }
    PIN_ReleaseLock(&lock);
}

static VOID trace_memory(THREADID tid, ADDRINT g, ADDRINT pc, ADDRINT address, UINT32 index, UINT32 width) {
    PIN_GetLock(&lock, tid + 1);
    if (active && g == owner_g) {
        unsigned captured = width > 32 ? 32 : width;
        flow_file << "{\"kind\":\"before_memory\",\"step\":" << flow_steps << ",\"pc\":" << pc
                  << ",\"operand\":" << index << ",\"address\":" << address << ",\"width\":" << width
                  << ",\"captured_bytes\":" << captured << ",\"tags\":";
        raw_tags(address, 0, -1, captured);
        flow_file << "}" << std::endl;
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
    if (flow_pcs.count(pc)) {
        INS_InsertCall(ins, IPOINT_BEFORE, AFUNPTR(trace_step), IARG_CALL_ORDER, CALL_ORDER_FIRST + 1,
                       IARG_THREAD_ID, IARG_CONST_CONTEXT, IARG_ADDRINT, pc, IARG_END);
        for (UINT32 i = 0; i < INS_MemoryOperandCount(ins); ++i)
            INS_InsertPredicatedCall(ins, IPOINT_BEFORE, AFUNPTR(trace_memory), IARG_CALL_ORDER, CALL_ORDER_FIRST + 2,
                       IARG_THREAD_ID, IARG_REG_VALUE, REG_R14, IARG_ADDRINT, pc, IARG_MEMORYOP_EA, i,
                       IARG_UINT32, i, IARG_UINT32, INS_MemoryOperandSize(ins, i), IARG_END);
    }
}

static VOID finish(INT32 code, VOID *) {
    if (flow_file.is_open()) {
        for (std::set<tag_t>::const_iterator it = seen_tags.begin(); it != seen_tags.end(); ++it) {
            std::vector<tag_seg> segments = tag_get(*it);
            flow_file << "{\"kind\":\"tag_dictionary\",\"tag\":" << *it << ",\"segments\":[";
            for (size_t i = 0; i < segments.size(); ++i) {
                if (i) flow_file << ",";
                flow_file << "[" << segments[i].begin << "," << segments[i].end << "]";
            }
            flow_file << "]}" << std::endl;
        }
        flow_file << "{\"kind\":\"flow_finish\",\"steps\":" << flow_steps << ",\"exit_code\":" << code << "}" << std::endl;
        flow_file.close();
    }
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
    if (!FlowConfig.Value().empty() || !FlowOutput.Value().empty()) {
        std::ifstream flow_input(FlowConfig.Value().c_str());
        while (flow_input >> std::hex >> pc) flow_pcs.insert(pc);
        flow_file.open(FlowOutput.Value().c_str());
        if (!flow_file || flow_pcs.empty()) return 5;
    }
    PIN_InitLock(&lock);
    if (libdft_init()) return 4;
    // No hook_file_syscall(): only our declared price/shipping sources get tags.
    for (unsigned i = 0; i < XED_ICLASS_LAST; ++i) ins_set_pre(&ins_desc[i], instrument);
    PIN_AddFiniFunction(finish, 0);
    PIN_StartProgram();
    return 0;
}
