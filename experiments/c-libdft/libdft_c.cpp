// Query adapter only. All instruction propagation is unmodified upstream libdft64.
// One selected root invocation per fresh process; no previous invocation is tagged.
#include "pin.H"
#include "libdft_api.h"
#include "libdft_known_opcodes.h"
#include <fstream>
#include <set>
#include <vector>

extern ins_desc_t ins_desc[XED_ICLASS_LAST];
KNOB<UINT32> Target(KNOB_MODE_WRITEONCE, "pintool", "sequence", "1", "root invocation to query, 1..24");
KNOB<std::string> Output(KNOB_MODE_WRITEONCE, "pintool", "origin_log", "", "diagnostic JSONL");
static const char *names[] = {"loop_call_overwrite", "loop_call_accumulate", "loop_call_transform",
                             "read_iteration", "transform_iteration"};
struct Range { ADDRINT begin, end; };
static Range ranges[5] = {};
static std::ofstream out;
static PIN_LOCK lock;
static bool active = false, bad = false;
static unsigned roots = 0, starts = 0, sinks = 0, steps = 0, helpers = 0, contexts = 0, threads = 0;
static THREADID owner;
static unsigned root_id;
static ADDRINT src, dst, sp, return_pc;
static UINT32 source_values[3], count_value;

static void fail(const char *why) {
    bad = true;
    out << "{\"kind\":\"error\",\"reason\":\"" << why << "\"}" << std::endl;
}
template<typename T> static T read_at(ADDRINT p) {
    T value = 0;
    if (!p || PIN_SafeCopy(&value, reinterpret_cast<const void *>(p), sizeof(T)) != sizeof(T))
        fail("short_memory_read");
    return value;
}
static void tags(tag_t t) {
    std::set<unsigned> labels;
    std::vector<tag_seg> segs = tag_get(t);
    for (size_t i = 0; i < segs.size(); ++i) {
        if (segs[i].begin < 1 || segs[i].end > 4 || segs[i].end <= segs[i].begin) {
            bad = true;
            continue;
        }
        for (unsigned j = segs[i].begin; j < segs[i].end; ++j) labels.insert(j);
    }
    out << "[";
    bool first = true;
    for (std::set<unsigned>::iterator it = labels.begin(); it != labels.end(); ++it) {
        if (!first) out << ",";
        out << *it; first = false;
    }
    out << "]";
}
static void bytes(ADDRINT p) {
    out << "[";
    for (unsigned b = 0; b < 4; ++b) {
        if (b) out << ",";
        tags(tagmap_getb(p + b));
    }
    out << "]";
}
static VOID image_load(IMG img, VOID *) {
    if (!IMG_IsMainExecutable(img)) return;
    for (unsigned i = 0; i < 5; ++i) {
        RTN rtn = RTN_FindByName(img, names[i]);
        if (!RTN_Valid(rtn) || !RTN_Size(rtn)) { fail("missing_boundary_symbol"); continue; }
        ranges[i] = {RTN_Address(rtn), RTN_Address(rtn) + RTN_Size(rtn)};
        out << "{\"kind\":\"symbol\",\"id\":" << i << ",\"name\":\"" << names[i]
            << "\",\"begin\":" << ranges[i].begin << ",\"end\":" << ranges[i].end << "}" << std::endl;
    }
}
static VOID observe(THREADID tid, const CONTEXT *ctx, ADDRINT pc, UINT32 opcode, BOOL covered, BOOL is_ret) {
    PIN_GetLock(&lock, tid + 1);
    int fid = -1;
    for (unsigned i = 0; i < 5; ++i)
        if (ranges[i].begin && pc >= ranges[i].begin && pc < ranges[i].end) fid = i;
    bool entry = fid >= 0 && pc == ranges[fid].begin;
    if (entry && fid < 3) {
        if (active) fail("nested_root");
        ++roots;
        if (roots == Target.Value()) {
            active = true; owner = tid; root_id = fid; ++starts;
            src = PIN_GetContextReg(ctx, REG_RSI); dst = PIN_GetContextReg(ctx, REG_RDI);
            sp = PIN_GetContextReg(ctx, REG_RSP); return_pc = read_at<ADDRINT>(sp);
            count_value = static_cast<UINT32>(PIN_GetContextReg(ctx, REG_RDX));
            if (!src || !dst || src + 12 < src || dst + 8 < dst || !(src + 12 <= dst || dst + 8 <= src))
                fail("invalid_or_overlapping_boundary_objects");
            // No file/syscall source hooks: all shadow state must still be empty here.
            bool dirty = false;
            for (unsigned r = 0; r <= GRP_NUM; ++r)
                for (unsigned b = 0; b < TAGS_PER_GPR; ++b)
                    if (!tag_is_empty(tagmap_getb_reg(tid, r, b))) dirty = true;
            for (unsigned b = 0; b < 8; ++b)
                if (!tag_is_empty(tagmap_getb(dst + b))) dirty = true;
            for (unsigned b = 0; b < 12; ++b)
                if (!tag_is_empty(tagmap_getb(src + b))) dirty = true;
            if (dirty) fail("nonempty_shadow_before_source_initialization");
            for (unsigned i = 0; i < 3; ++i) source_values[i] = read_at<UINT32>(src + 4*i);
            out << "{\"kind\":\"source\",\"sequence\":" << roots << ",\"function\":\"" << names[fid]
                << "\",\"tid\":" << tid << ",\"src\":" << src << ",\"dst\":" << dst
                << ",\"count\":" << count_value << ",\"values\":[";
            for (unsigned i = 0; i < 3; ++i) {
                if (i) out << ",";
                out << source_values[i];
                tagmap_setn(src + 4*i, 4, tag_alloc<tag_t>(i + 1));
            }
            out << "],\"byte_labels\":[";
            for (unsigned i = 0; i < 3; ++i) { if (i) out << ","; bytes(src + 4*i); }
            out << "]}" << std::endl;
        }
    }
    if (active) {
        if (tid != owner) fail("concurrent_execution_in_query");
        if (fid < 0) fail("execution_outside_declared_functions");
        if (!covered) fail("opcode_absent_from_upstream_dispatcher");
        if (++steps > 4096) { fail("instruction_budget_exceeded"); active = false; }
        if (entry && fid >= 3) ++helpers;
        out << "{\"kind\":\"instruction\",\"step\":" << steps << ",\"tid\":" << tid
            << ",\"pc\":" << pc << ",\"fid\":" << fid << ",\"opcode\":" << opcode
            << ",\"covered\":" << (covered ? "true" : "false") << "}" << std::endl;
        if (is_ret && fid == static_cast<int>(root_id)) {
            if (PIN_GetContextReg(ctx, REG_RSP) != sp || read_at<ADDRINT>(sp) != return_pc)
                fail("root_return_stack_mismatch");
            for (unsigned i = 0; i < 3; ++i)
                if (read_at<UINT32>(src + 4*i) != source_values[i]) fail("source_was_mutated");
            UINT32 value = read_at<UINT32>(dst);
            out << "{\"kind\":\"sink\",\"sequence\":" << roots << ",\"function\":\"" << names[root_id]
                << "\",\"value\":" << value << ",\"labels\":";
            tags(tagmap_getn(dst, 4));
            out << ",\"byte_labels\":"; bytes(dst);
            out << ",\"helper_calls\":" << helpers << "}" << std::endl;
            ++sinks; active = false;
        }
    }
    PIN_ReleaseLock(&lock);
}
static VOID instrument(INS ins) {
    INS_InsertCall(ins, IPOINT_BEFORE, AFUNPTR(observe), IARG_CALL_ORDER, CALL_ORDER_FIRST,
                   IARG_THREAD_ID, IARG_CONST_CONTEXT, IARG_ADDRINT, INS_Address(ins),
                   IARG_UINT32, INS_Opcode(ins), IARG_BOOL, known_opcode(INS_Opcode(ins)),
                   IARG_BOOL, INS_IsRet(ins), IARG_END);
}
static VOID context_change(THREADID tid, CONTEXT_CHANGE_REASON, const CONTEXT *, CONTEXT *, INT32, VOID *) {
    PIN_GetLock(&lock, tid + 1);
    if (active) { ++contexts; fail("context_change_in_query"); }
    PIN_ReleaseLock(&lock);
}
static VOID thread_start(THREADID tid, CONTEXT *, INT32, VOID *) {
    PIN_GetLock(&lock, tid + 1);
    if (++threads != 1) fail("multiple_application_threads");
    PIN_ReleaseLock(&lock);
}
static VOID finish(INT32 code, VOID *) {
    out << "{\"kind\":\"finish\",\"exit_code\":" << code << ",\"bad\":" << (bad ? "true" : "false")
        << ",\"active\":" << (active ? "true" : "false") << ",\"roots\":" << roots
        << ",\"starts\":" << starts << ",\"sinks\":" << sinks << ",\"steps\":" << steps
        << ",\"contexts\":" << contexts << ",\"threads\":" << threads
        << ",\"performance_eligible\":false}" << std::endl;
}
int main(int argc, char **argv) {
    PIN_InitSymbols();
    if (PIN_Init(argc, argv) || Target.Value() < 1 || Target.Value() > 24) return 1;
    out.open(Output.Value().c_str());
    if (!out) return 2;
    PIN_InitLock(&lock);
    if (libdft_init()) return 3;
    IMG_AddInstrumentFunction(image_load, 0);
    PIN_AddThreadStartFunction(thread_start, 0);
    PIN_AddContextChangeFunction(context_change, 0);
    for (unsigned i = 0; i < XED_ICLASS_LAST; ++i) ins_set_pre(&ins_desc[i], instrument);
    PIN_AddFiniFunction(finish, 0);
    PIN_StartProgram();
    return 0;
}
