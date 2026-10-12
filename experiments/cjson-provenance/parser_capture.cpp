// Read-only native observer. Original libdft propagation and cJSON are unchanged.
// Taint source boundary: successful parse_string allocation return, before decoding.
#include "pin.H"
#include "libdft_api.h"
#include "libdft_known_opcodes.h"
#include <fstream>
#include <set>
#include <vector>
#include <sstream>
#include <iomanip>
extern ins_desc_t ins_desc[XED_ICLASS_LAST];
KNOB<UINT32> Target(KNOB_MODE_WRITEONCE,"pintool","root","0","parse_string ordinal; 0 indexes only");
KNOB<std::string> Output(KNOB_MODE_WRITEONCE,"pintool","origin_log","","JSONL");
struct Buffer { ADDRINT content,length,offset,depth,allocate,deallocate,reallocate; };
static_assert(sizeof(Buffer)==56,"configured private buffer ABI");
static const char *names[]={"parse_string","parse_hex4","utf16_literal_to_utf8","tf_cjson_begin","tf_cjson_sink"};
static ADDRINT begin[5]={},end[5]={};
static REG regs[]={REG_RDI,REG_RSI,REG_RBP,REG_RSP,REG_RBX,REG_RDX,REG_RCX,REG_RAX,REG_R8,REG_R9,REG_R10,REG_R11,REG_R12,REG_R13,REG_R14,REG_R15};
static const char *regnames[]={"rdi","rsi","rbp","rsp","rbx","rdx","rcx","rax","r8","r9","r10","r11","r12","r13","r14","r15"};
static unsigned dregs[]={3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18};
static std::ofstream out;
static PIN_LOCK lock;
static bool bad=false,in_root=false,tracing=false;
static unsigned cases=0,roots=0,steps=0,starts=0,sinks=0,threads=0,contexts=0;
static THREADID owner=0;
static ADDRINT item=0,buffer=0,root_sp=0,return_pc=0,allocation=0,allocation_size=0;
static ADDRINT alloc_return=0,alloc_sp=0,input=0,input_size=0;
static Buffer snapshot={};
static std::string source_hex;
static void fail(const char *s){bad=true;out<<"{\"kind\":\"error\",\"reason\":\""<<s<<"\"}\n";}
template<class T> static T read(ADDRINT address){
    T x={};if(!address||PIN_SafeCopy(&x,reinterpret_cast<void*>(address),sizeof(x))!=sizeof(x))fail("short_read");return x;
}
static std::string bytes(ADDRINT address,size_t n){
    if(n>520){fail("snapshot_bound");return "";}
    unsigned char b[520]={};if(n&&(!address||PIN_SafeCopy(b,reinterpret_cast<void*>(address),n)!=n))fail("short_snapshot");
    std::ostringstream s;for(size_t i=0;i<n;++i)s<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(b[i]);return s.str();
}
static std::string string_bytes(ADDRINT address,size_t limit){
    std::ostringstream s;
    for(size_t i=0;i<limit;++i){unsigned char c=read<unsigned char>(address+i);if(!c)return s.str();
        s<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(c);}
    fail("missing_terminator");return "";
}
static void tags(tag_t t){
    std::set<unsigned> xs;
    for(auto s:tag_get(t)){if(s.begin<1||s.end>257||s.end<s.begin){fail("tag_namespace");continue;}
        for(unsigned x=s.begin;x<s.end;++x)xs.insert(x);}
    out<<'[';bool first=true;for(auto x:xs){if(!first)out<<',';out<<x;first=false;}out<<']';
}
static void memory_tags(ADDRINT p,unsigned n){out<<'[';for(unsigned i=0;i<n;++i){if(i)out<<',';tags(tagmap_getb(p+i));}out<<']';}
static void image(IMG img,VOID*){
    if(!IMG_IsMainExecutable(img))return;
    for(unsigned i=0;i<5;++i){RTN r=RTN_FindByName(img,names[i]);
        if(!RTN_Valid(r)||!RTN_Size(r)){fail("missing_symbol");continue;}
        begin[i]=RTN_Address(r);end[i]=begin[i]+RTN_Size(r);
        out<<"{\"kind\":\"symbol\",\"name\":\""<<names[i]<<"\",\"begin\":"<<begin[i]<<",\"end\":"<<end[i]<<"}\n";}
}
static void observe(THREADID tid,const CONTEXT *ctx,ADDRINT pc,UINT32 size,BOOL iscall,ADDRINT target,BOOL isret,BOOL covered){
    PIN_GetLock(&lock,tid+1);
    if(pc==begin[3]){
        if(in_root||tracing)fail("case_changed_inside_parser");
        ++cases;input=PIN_GetContextReg(ctx,REG_RDI);input_size=PIN_GetContextReg(ctx,REG_RSI);
        out<<"{\"kind\":\"case\",\"case\":"<<cases<<",\"address\":"<<input<<",\"data\":\""<<bytes(input,input_size)<<"\"}\n";
    }
    if(pc==begin[4]){
        ADDRINT node=PIN_GetContextReg(ctx,REG_RSI),p=node?read<ADDRINT>(node+32):0;
        out<<"{\"kind\":\"field\",\"case\":"<<cases<<",\"query\":"<<PIN_GetContextReg(ctx,REG_RDX)
           <<",\"item\":"<<node<<",\"address\":"<<p<<",\"data\":\""<<(p?string_bytes(p,256):"")<<"\"}\n";
    }
    if(pc==begin[0]){
        if(in_root)fail("nested_parser");
        in_root=true;++roots;owner=tid;item=PIN_GetContextReg(ctx,REG_RDI);buffer=PIN_GetContextReg(ctx,REG_RSI);
        root_sp=PIN_GetContextReg(ctx,REG_RSP);return_pc=read<ADDRINT>(root_sp);snapshot=read<Buffer>(buffer);
        allocation=allocation_size=alloc_return=0;
        if(snapshot.content!=input||snapshot.length!=input_size||snapshot.length>256)fail("source_binding");
    }
    if(in_root&&tid!=owner)fail("parser_thread_changed");
    if(in_root&&iscall&&target==snapshot.allocate){
        if(alloc_return||allocation)fail("repeated_allocation");
        alloc_return=pc+size;alloc_sp=PIN_GetContextReg(ctx,REG_RSP);allocation_size=PIN_GetContextReg(ctx,REG_RDI);
        if(!allocation_size||allocation_size>32)fail("allocation_bound");
    }
    if(in_root&&alloc_return&&pc==alloc_return){
        if(PIN_GetContextReg(ctx,REG_RSP)!=alloc_sp)fail("allocator_stack");
        allocation=PIN_GetContextReg(ctx,REG_RAX);alloc_return=0;
        if(!allocation)fail("allocation_failed");
        if(roots==Target.Value()&&!bad){
            bool dirty=false;
            for(unsigned r=0;r<=GRP_NUM;++r)for(unsigned b=0;b<TAGS_PER_GPR;++b)
                if(!tag_is_empty(tagmap_getb_reg(tid,r,b)))dirty=true;
            for(unsigned i=0;i<input_size;++i)if(!tag_is_empty(tagmap_getb(input+i)))dirty=true;
            for(unsigned i=0;i<allocation_size;++i)if(!tag_is_empty(tagmap_getb(allocation+i)))dirty=true;
            if(dirty)fail("initial_shadow_not_empty");
            source_hex=bytes(input,input_size);
            for(unsigned i=0;i<input_size;++i)tagmap_setb(input+i,tag_alloc<tag_t>(i+1));
            tracing=true;++starts;
            out<<"{\"kind\":\"source\",\"case\":"<<cases<<",\"root\":"<<roots<<",\"address\":"<<input
               <<",\"data\":\""<<source_hex<<"\",\"offset\":"<<snapshot.offset<<",\"item\":"<<item<<",\"buffer\":"<<buffer
               <<",\"allocation\":"<<allocation<<",\"allocation_size\":"<<allocation_size<<",\"entry_pc\":"<<pc
               <<",\"root_sp\":"<<root_sp<<",\"return_pc\":"<<return_pc<<",\"snapshots\":[";
            ADDRINT locations[]={root_sp-512,item,buffer,PIN_GetContextReg(ctx,REG_SEG_FS_BASE)+40};
            unsigned lengths[]={520,64,56,8};
            for(unsigned j=0;j<4;++j){if(j)out<<',';out<<"{\"address\":"<<locations[j]<<",\"data\":\""<<bytes(locations[j],lengths[j])<<"\"}";}
            out<<"]}\n";
        }
    }
    if(tracing){
        bool inside=false;for(unsigned i=0;i<3;++i)if(pc>=begin[i]&&pc<end[i])inside=true;
        if(!inside||!covered)fail("unqualified_instruction_or_call");
        if(++steps>8192){fail("instruction_budget");tracing=false;}
        out<<"{\"kind\":\"state\",\"step\":"<<steps<<",\"pc\":"<<pc<<",\"bytes\":\""<<bytes(pc,size)<<"\",\"registers\":{";
        for(unsigned i=0;i<16;++i){if(i)out<<',';out<<'"'<<regnames[i]<<"\":"<<PIN_GetContextReg(ctx,regs[i]);}
        out<<"},\"fs_base\":"<<PIN_GetContextReg(ctx,REG_SEG_FS_BASE)<<",\"tag_bytes\":[";
        for(unsigned r=0;r<16;++r){if(r)out<<',';out<<'[';for(unsigned b=0;b<8;++b){if(b)out<<',';tags(tagmap_getb_reg(tid,dregs[r],b));}out<<']';}
        out<<"],\"allocation_tags\":";memory_tags(allocation,allocation_size);out<<"}\n";
    }
    if(in_root&&isret&&pc>=begin[0]&&pc<end[0]){
        if(PIN_GetContextReg(ctx,REG_RSP)!=root_sp||read<ADDRINT>(root_sp)!=return_pc)fail("root_return_frame");
        unsigned ok=PIN_GetContextReg(ctx,REG_RAX)&0xffffffff;
        ADDRINT p=ok?read<ADDRINT>(item+32):0;
        out<<"{\"kind\":\"parser_end\",\"case\":"<<cases<<",\"root\":"<<roots<<",\"offset\":"<<snapshot.offset
           <<",\"item\":"<<item<<",\"address\":"<<p<<",\"success\":"<<(ok?"true":"false")<<",\"data\":\""
           <<(p?string_bytes(p,32):"")<<"\"}\n";
        if(tracing){
            if(ok!=1||p!=allocation||bytes(input,input_size)!=source_hex)fail("parser_result_contract");
            out<<"{\"kind\":\"sink\",\"item\":"<<item<<",\"address\":"<<p<<",\"data\":\""<<string_bytes(p,allocation_size)
               <<"\",\"allocation_tags\":";memory_tags(p,allocation_size);out<<"}\n";
            ++sinks;tracing=false;
        }
        in_root=false;
    }
    PIN_ReleaseLock(&lock);
}
static void instrument(INS ins){
    if(INS_IsCall(ins)) INS_InsertCall(ins,IPOINT_BEFORE,AFUNPTR(observe),IARG_CALL_ORDER,CALL_ORDER_FIRST,
        IARG_THREAD_ID,IARG_CONST_CONTEXT,IARG_ADDRINT,INS_Address(ins),IARG_UINT32,INS_Size(ins),IARG_BOOL,true,
        IARG_BRANCH_TARGET_ADDR,IARG_BOOL,INS_IsRet(ins),IARG_BOOL,known_opcode(INS_Opcode(ins)),IARG_END);
    else INS_InsertCall(ins,IPOINT_BEFORE,AFUNPTR(observe),IARG_CALL_ORDER,CALL_ORDER_FIRST,
        IARG_THREAD_ID,IARG_CONST_CONTEXT,IARG_ADDRINT,INS_Address(ins),IARG_UINT32,INS_Size(ins),IARG_BOOL,false,
        IARG_ADDRINT,ADDRINT(0),IARG_BOOL,INS_IsRet(ins),IARG_BOOL,known_opcode(INS_Opcode(ins)),IARG_END);
}
static void thread(THREADID tid,CONTEXT*,INT32,VOID*){PIN_GetLock(&lock,tid+1);if(++threads!=1)fail("multiple_threads");PIN_ReleaseLock(&lock);}
static void context(THREADID tid,CONTEXT_CHANGE_REASON,const CONTEXT*,CONTEXT*,INT32,VOID*){
    PIN_GetLock(&lock,tid+1);if(in_root){++contexts;fail("context_change");}PIN_ReleaseLock(&lock);
}
static void finish(INT32 code,VOID*){
    out<<"{\"kind\":\"finish\",\"exit_code\":"<<code<<",\"bad\":"<<(bad?"true":"false")
       <<",\"active\":"<<((in_root||tracing)?"true":"false")<<",\"cases\":"<<cases<<",\"roots\":"<<roots
       <<",\"steps\":"<<steps<<",\"starts\":"<<starts<<",\"sinks\":"<<sinks<<",\"threads\":"<<threads<<",\"contexts\":"<<contexts<<"}\n";
}
int main(int argc,char **argv){
    PIN_InitSymbols();if(PIN_Init(argc,argv))return 1;
    out.open(Output.Value().c_str());if(!out)return 2;
    PIN_InitLock(&lock);if(libdft_init())return 3;
    IMG_AddInstrumentFunction(image,0);PIN_AddThreadStartFunction(thread,0);PIN_AddContextChangeFunction(context,0);
    for(unsigned i=0;i<XED_ICLASS_LAST;++i)ins_set_pre(&ins_desc[i],instrument);
    PIN_AddFiniFunction(finish,0);PIN_StartProgram();return 0;
}
