// Boundary adapter/diagnostics only; upstream libdft64 propagation is unchanged.
#include "pin.H"
#include "libdft_api.h"
#include "libdft_known_opcodes.h"
#include <fstream>
#include <iterator>
#include <set>
#include <vector>
#include <string>

// ABI_CONTRACT -- replaced by header offsets verified against target ELF DWARF.

extern ins_desc_t ins_desc[XED_ICLASS_LAST];
KNOB<BOOL> Taint(KNOB_MODE_WRITEONCE,"pintool","enable_taint","1","original libdft propagation; 0 = observation only");
KNOB<std::string> Output(KNOB_MODE_WRITEONCE,"pintool","origin_log","","raw JSONL");
KNOB<std::string> Input(KNOB_MODE_WRITEONCE,"pintool","input_file","","immutable input identity");
const char *names[]={"GetGifWord","GetByte","GetByteStr","DecodeGifImg","LoadGif"};
const char *regnames[]={"rax","rbx","rcx","rdx","rsi","rdi","rbp","rsp","r8","r9","r10","r11","r12","r13","r14","r15"};
const REG regids[]={REG_RAX,REG_RBX,REG_RCX,REG_RDX,REG_RSI,REG_RDI,REG_RBP,REG_RSP,REG_R8,REG_R9,REG_R10,REG_R11,REG_R12,REG_R13,REG_R14,REG_R15};
struct Range {ADDRINT begin,end;} ranges[5]={};
std::ofstream out;
std::vector<unsigned char> input;
PIN_LOCK mutex;
bool bad=false,load_active=false,decoder_active=false,word_active=false,read_active=false,call_active=false;
unsigned serial=0,threads=0,contexts=0,loads=0,decoders=0,words=0,sinks=0,reads=0,refills=0,steps=0,ignored_shifts=0;
ADDRINT parent=0,file=0,word_ctx=0,word_img=0,word_sp=0,word_ret=0,call_pc=0,call_resume=0;
ADDRINT read_dst=0,read_sp=0,read_ret=0;
unsigned cursor=0,read_start=0,read_count=0,read_fid=0;
THREADID owner=0;

void prefix(const char *kind,ADDRINT pc=0,THREADID tid=0) {
    out<<"{\"record\":"<<++serial<<",\"kind\":\""<<kind<<"\",\"pc\":"<<pc<<",\"tid\":"<<tid;
}
void fail(const char *reason) {bad=true;prefix("error");out<<",\"reason\":\""<<reason<<"\"}"<<std::endl;}
template<typename T> T get(ADDRINT address) {
    T v=0;
    if(!address || PIN_SafeCopy(&v,reinterpret_cast<const void*>(address),sizeof(T))!=sizeof(T))fail("short_memory_read");
    return v;
}
std::vector<unsigned char> memory(ADDRINT p,unsigned n) {
    std::vector<unsigned char> v(n);
    if(n && (!p || PIN_SafeCopy(&v[0],reinterpret_cast<const void*>(p),n)!=n))fail("short_snapshot");
    return v;
}
void hexbytes(const std::vector<unsigned char> &v) {
    static const char *h="0123456789abcdef";
    out<<'"';for(unsigned char x:v)out<<h[x>>4]<<h[x&15];out<<'"';
}
void registers(const CONTEXT *ctx) {
    out<<'{';for(unsigned i=0;i<16;i++){if(i)out<<',';out<<'"'<<regnames[i]<<"\":"<<PIN_GetContextReg(ctx,regids[i]);}out<<'}';
}
std::set<unsigned> labels(tag_t tag) {
    std::set<unsigned> result;
    for(auto s:tag_get(tag)) {
        if(s.begin<1 || s.end>input.size()+1 || s.end<=s.begin){bad=true;continue;}
        for(unsigned j=s.begin;j<s.end;j++)result.insert(j);
    }
    return result;
}
void label_json(const std::set<unsigned> &v) {out<<'[';bool first=true;for(unsigned n:v){if(!first)out<<',';out<<n;first=false;}out<<']';}
void check_parent(ADDRINT p) {
    ADDRINT f=get<ADDRINT>(p+GIF_INPUT);
    if(!parent){parent=p;file=f;}
    if(!p || p!=parent || !f || f!=file || (get<unsigned char>(p+GIF_MODE)&2))fail("reader_identity_or_file_mode");
}
void image_load(IMG img,VOID*) {
    if(!IMG_IsMainExecutable(img))return;
    for(unsigned i=0;i<5;i++) {
        RTN r=RTN_FindByName(img,names[i]);
        if(!RTN_Valid(r)||!RTN_Size(r)){fail("missing_symbol");continue;}
        ranges[i]={RTN_Address(r),RTN_Address(r)+RTN_Size(r)};
        prefix("symbol");out<<",\"name\":\""<<names[i]<<"\",\"begin\":"<<ranges[i].begin<<",\"end\":"<<ranges[i].end<<"}"<<std::endl;
    }
}
void observe(THREADID tid,const CONTEXT *ctx,ADDRINT pc,UINT32 opcode,BOOL known,BOOL is_ret,BOOL is_call,ADDRINT target,ADDRINT next) {
    PIN_GetLock(&mutex,tid+1);
    int fid=-1;for(unsigned i=0;i<5;i++)if(ranges[i].begin<=pc && pc<ranges[i].end)fid=i;
    const bool entry=fid>=0 && pc==ranges[fid].begin;
    if(entry && fid==4) {
        if(load_active || word_active || read_active)fail("nested_load");
        if(!loads)owner=tid;
        load_active=true;++loads;check_parent(PIN_GetContextReg(ctx,REG_RDI));
        prefix("load_enter",pc,tid);out<<",\"parent\":"<<parent<<",\"cursor\":"<<cursor<<"}"<<std::endl;
    }
    if(load_active && tid!=owner)fail("thread_changed");
    if(entry && fid==3) {
        if(!load_active || decoder_active)fail("decoder_scope");
        decoder_active=true;++decoders;
        prefix("decoder_enter",pc,tid);out<<"}"<<std::endl;
    }
    if(word_active && call_active && pc==call_resume) {
        if(read_active)fail("reader_did_not_return");
        prefix("call_exit",pc,tid);out<<",\"call_pc\":"<<call_pc<<",\"registers\":";registers(ctx);out<<"}"<<std::endl;
        call_active=false;
    }
    if(entry && fid==0) {
        if(!decoder_active || word_active || read_active)fail("word_scope");
        word_active=true;++words;
        word_ctx=PIN_GetContextReg(ctx,REG_RSI);word_img=PIN_GetContextReg(ctx,REG_RDI);
        word_sp=PIN_GetContextReg(ctx,REG_RSP);word_ret=get<ADDRINT>(word_sp);
        check_parent(get<ADDRINT>(word_img+IMG_PARENT));
        if(Taint.Value() && words==1) {
            bool dirty=false;
            for(unsigned r=0;r<=GRP_NUM;r++)for(unsigned b=0;b<TAGS_PER_GPR;b++)dirty|=!tag_is_empty(tagmap_getb_reg(tid,r,b));
            for(unsigned b=0;b<CTX_SIZE;b++)dirty|=!tag_is_empty(tagmap_getb(word_ctx+b));
            if(dirty)fail("nonempty_initial_shadow");
        }
        // Record, do not clear, metadata tags. A tagged width/mask would violate
        // the fixed-metadata comparison contract and must remain visible.
        bool metadata_clean=true;
        const unsigned offsets[]={CTX_NBBIT,CTX_MAX,CTX_MAX+1,CTX_RESTBITS,CTX_RESTBYTE};
        if(Taint.Value())for(unsigned off: offsets)
            metadata_clean &= tag_is_empty(tagmap_getb(word_ctx+off));
        std::vector<unsigned char> bytes=memory(word_ctx,CTX_SIZE);
        prefix("word_enter",pc,tid);out<<",\"sequence\":"<<words<<",\"context_pointer\":"<<word_ctx<<",\"image_pointer\":"<<word_img
            <<",\"parent_pointer\":"<<parent<<",\"return_pc\":"<<word_ret<<",\"metadata_clean\":"<<(metadata_clean?"true":"false")<<",\"registers\":";
        registers(ctx);out<<",\"context\":";hexbytes(bytes);out<<"}"<<std::endl;
    }
    if(entry && (fid==1 || fid==2)) {
        if(!load_active || read_active)fail("nested_or_unscoped_reader");
        read_active=true;++reads;read_fid=fid;read_start=cursor;
        check_parent(PIN_GetContextReg(ctx,REG_RDI));
        read_dst=fid==2?PIN_GetContextReg(ctx,REG_RSI):0;
        read_count=fid==2?static_cast<UINT32>(PIN_GetContextReg(ctx,REG_RDX)):1;
        read_sp=PIN_GetContextReg(ctx,REG_RSP);read_ret=get<ADDRINT>(read_sp);
        if(read_count>255 || cursor+read_count>input.size())fail("input_read_out_of_bounds");
        prefix("read_enter",pc,tid);out<<",\"read\":"<<reads<<",\"name\":\""<<names[fid]<<"\",\"offset\":"<<read_start<<",\"count\":"<<read_count
            <<",\"destination\":"<<read_dst<<",\"parent\":"<<parent<<",\"file\":"<<file<<",\"in_word\":"<<(word_active?"true":"false")
            <<",\"sp\":"<<read_sp<<",\"return_pc\":"<<read_ret<<"}"<<std::endl;
    }
    if(is_ret && (fid==1 || fid==2)) {
        if(!read_active || static_cast<unsigned>(fid)!=read_fid || PIN_GetContextReg(ctx,REG_RSP)!=read_sp || get<ADDRINT>(read_sp)!=read_ret)fail("reader_return_mismatch");
        if(read_count>255 || read_start+read_count>input.size()) {read_active=false;PIN_ReleaseLock(&mutex);return;}
        ADDRINT rax=PIN_GetContextReg(ctx,REG_RAX);
        std::vector<unsigned char> data=fid==1?std::vector<unsigned char>(1,static_cast<unsigned char>(rax)):memory(read_dst,read_count);
        if(fid==2 && static_cast<UINT32>(rax)!=0)fail("short_or_failed_read");
        for(unsigned i=0;i<data.size();i++)if(data[i]!=input[read_start+i])fail("sequential_file_content_mismatch");
        bool source=word_active && fid==2;
        if(source) {
            if(read_dst!=word_ctx+CTX_BUFFER || !read_count)fail("unexpected_source_buffer");
            ++refills;
            if(Taint.Value())for(unsigned i=0;i<data.size();i++)tagmap_setb(read_dst+i,tag_alloc<tag_t>(read_start+i+1));
        }
        prefix("read_exit",pc,tid);out<<",\"read\":"<<reads<<",\"offset\":"<<read_start<<",\"data\":";hexbytes(data);
        out<<",\"source\":"<<(source?"true":"false")<<",\"version\":"<<refills<<",\"result\":"<<static_cast<UINT32>(rax)<<",\"byte_labels\":[";
        if(Taint.Value() && source)for(unsigned i=0;i<data.size();i++){if(i)out<<',';label_json(labels(tagmap_getb(read_dst+i)));}
        out<<"]}"<<std::endl;cursor+=read_count;read_active=false;
    }
    if(word_active && fid==0) {
        if(!known && Taint.Value())fail("opcode_absent_from_upstream_dispatcher");
        bool ignored=opcode==XED_ICLASS_SHL || opcode==XED_ICLASS_SHR || opcode==XED_ICLASS_SAR;
        if(ignored)++ignored_shifts;
        if(++steps>1000000)fail("instruction_budget");
        prefix("instruction",pc,tid);out<<",\"sequence\":"<<words<<",\"step\":"<<steps<<",\"known\":"<<(known?"true":"false")<<",\"ignored_shift\":"<<(ignored?"true":"false")<<"}"<<std::endl;
        if(is_call) {
            if(call_active || (target!=ranges[1].begin && target!=ranges[2].begin))fail("unconfigured_call");
            call_active=true;call_pc=pc;call_resume=next;
            prefix("call_enter",pc,tid);out<<",\"name\":\""<<(target==ranges[1].begin?names[1]:names[2])<<"\",\"resume\":"<<next<<",\"registers\":";registers(ctx);out<<"}"<<std::endl;
        }
        if(is_ret) {
            if(call_active || read_active || PIN_GetContextReg(ctx,REG_RSP)!=word_sp || get<ADDRINT>(word_sp)!=word_ret)fail("word_return_mismatch");
            std::vector<unsigned char> bytes=memory(word_ctx,CTX_SIZE);
            prefix("word_exit",pc,tid);out<<",\"sequence\":"<<words<<",\"registers\":";registers(ctx);out<<",\"context\":";hexbytes(bytes);
            out<<",\"byte_labels\":[";
            if(Taint.Value()){label_json(labels(tagmap_getb_reg(tid,DFT_REG_RAX,0)));out<<',';label_json(labels(tagmap_getb_reg(tid,DFT_REG_RAX,1)));}
            out<<"]}"<<std::endl;word_active=false;++sinks;
        }
    }
    if(is_ret && fid==3) {
        if(!decoder_active || word_active || read_active)fail("decoder_return_scope");
        decoder_active=false;prefix("decoder_exit",pc,tid);out<<",\"result\":"<<static_cast<UINT32>(PIN_GetContextReg(ctx,REG_RAX))<<"}"<<std::endl;
    }
    if(is_ret && fid==4) {
        if(!load_active || word_active || read_active || decoder_active)fail("load_return_scope");
        prefix("load_exit",pc,tid);out<<",\"result\":"<<static_cast<UINT32>(PIN_GetContextReg(ctx,REG_RAX))<<",\"cursor\":"<<cursor<<"}"<<std::endl;load_active=false;
    }
    PIN_ReleaseLock(&mutex);
}
void instrument(INS ins) {
    int fid=-1;ADDRINT pc=INS_Address(ins);
    for(unsigned i=0;i<5;i++)if(ranges[i].begin<=pc && pc<ranges[i].end)fid=i;
    if(fid<0 || (fid!=0 && pc!=ranges[fid].begin && !INS_IsRet(ins)))return;
    INS_InsertCall(ins,IPOINT_BEFORE,AFUNPTR(observe),IARG_CALL_ORDER,CALL_ORDER_FIRST,IARG_THREAD_ID,IARG_CONST_CONTEXT,IARG_ADDRINT,pc,
                   IARG_UINT32,INS_Opcode(ins),IARG_BOOL,known_opcode(INS_Opcode(ins)),IARG_BOOL,INS_IsRet(ins),IARG_BOOL,INS_IsCall(ins),
                   IARG_ADDRINT,INS_IsDirectControlFlow(ins)?INS_DirectControlFlowTargetAddress(ins):0,IARG_ADDRINT,INS_NextAddress(ins),IARG_END);
}
void plain_instrument(INS ins,VOID*){instrument(ins);}
void context_change(THREADID tid,CONTEXT_CHANGE_REASON,const CONTEXT*,CONTEXT*,INT32,VOID*) {
    PIN_GetLock(&mutex,tid+1);if(load_active){++contexts;fail("context_change_in_load");}PIN_ReleaseLock(&mutex);
}
void thread_start(THREADID tid,CONTEXT*,INT32,VOID*) {
    PIN_GetLock(&mutex,tid+1);if(++threads!=1)fail("multiple_application_threads");PIN_ReleaseLock(&mutex);
}
void syscall_entry(THREADID tid,CONTEXT *ctx,SYSCALL_STANDARD standard,VOID*) {
    PIN_GetLock(&mutex,tid+1);
    if(load_active && PIN_GetSyscallNumber(ctx,standard)==8)fail("lseek_during_sequential_load");
    PIN_ReleaseLock(&mutex);
}
void finish(INT32 code,VOID*) {
    prefix("finish");out<<",\"exit_code\":"<<code<<",\"taint\":"<<(Taint.Value()?"true":"false")<<",\"bad\":"<<(bad?"true":"false")
        <<",\"active\":"<<((load_active||decoder_active||word_active||read_active||call_active)?"true":"false")<<",\"threads\":"<<threads<<",\"contexts\":"<<contexts
        <<",\"loads\":"<<loads<<",\"decoders\":"<<decoders<<",\"words\":"<<words<<",\"sinks\":"<<sinks<<",\"reads\":"<<reads<<",\"refills\":"<<refills
        <<",\"steps\":"<<steps<<",\"ignored_shifts\":"<<ignored_shifts<<",\"cursor\":"<<cursor<<",\"input_bytes\":"<<input.size()<<",\"performance_eligible\":false}"<<std::endl;
}
int main(int argc,char **argv) {
    PIN_InitSymbols();if(PIN_Init(argc,argv))return 1;
    std::ifstream in(Input.Value().c_str(),std::ios::binary);input.assign(std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>());
    if(!in || input.empty() || input.size()>65536)return 2;
    out.open(Output.Value().c_str());if(!out)return 3;
    PIN_InitLock(&mutex);
    if(Taint.Value() && libdft_init())return 4;
    IMG_AddInstrumentFunction(image_load,0);PIN_AddThreadStartFunction(thread_start,0);
    PIN_AddContextChangeFunction(context_change,0);PIN_AddSyscallEntryFunction(syscall_entry,0);PIN_AddFiniFunction(finish,0);
    if(Taint.Value())for(unsigned i=0;i<XED_ICLASS_LAST;i++)ins_set_pre(&ins_desc[i],instrument);
    else INS_AddInstrumentFunction(plain_instrument,0);
    PIN_StartProgram();return 0;
}
