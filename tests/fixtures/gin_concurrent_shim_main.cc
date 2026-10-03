struct Frame {
    u64 g[4]{0,0,1024,0};char stack[1024]{};u32 input[3]{11,12,99},output[2]{};pt_regs r;
    Frame(){r.r14=reinterpret_cast<u64>(g);r.sp=reinterpret_cast<u64>(stack+512);r.bx=reinterpret_cast<u64>(input);r.ax=reinterpret_cast<u64>(output);}
};
void enter_read(Frame &f,int fd){
    pt_regs regs=f.r;regs.di=fd;regs.si=reinterpret_cast<u64>(f.input);regs.dx=4;regs.r10=fd*4;regs.orig_ax=__NR_pread64;
    bpf_raw_tracepoint_args raw{{reinterpret_cast<u64>(&regs),__NR_pread64}};
    raw_tracepoint__sys_enter(&raw);
}
void exit_read(Frame &f){
    pt_regs regs=f.r;regs.orig_ax=__NR_pread64;
    bpf_raw_tracepoint_args raw{{reinterpret_cast<u64>(&regs),4}};
    raw_tracepoint__sys_exit(&raw);
}
int main(){
    Frame a,b;b.input[0]=22;
    const u64 ta=(321ULL<<32)|400,tb=(321ULL<<32)|401;
    current_tid=ta;read_scope_enter(&a.r);assert(current_request()->request_id==1);
    current_tid=tb;read_scope_enter(&b.r);assert(current_request()->request_id==2);
    current_tid=ta;enter_read(a,4);assert(current_reads()->pending);
    current_tid=tb;enter_read(b,5);assert(current_reads()->pending);
    exit_read(b);assert(!current_reads()->pending && events.rows.back().fd==5 && events.rows.back().read_data[0]==22);
    current_tid=ta;assert(current_reads()->pending);exit_read(a);
    assert(events.rows.back().fd==4 && events.rows.back().read_data[0]==11);
    record(&a.r,0,0,0,1);
    current_tid=tb;record(&b.r,0,0,0,1);record(&b.r,0,4,1,1);
    assert(events.rows.back().call_id==1 && events.rows.back().sequence==1);
    current_tid=ta;record(&a.r,0,4,1,1);
    assert(events.rows.back().call_id==1 && events.rows.back().sequence==1);
    current_tid=999;const auto count_before=events.rows.size();enter_read(a,7);
    assert(events.rows.size()==count_before);
    current_tid=tb;read_scope_exit(&b.r);current_tid=ta;read_scope_exit(&a.r);
    assert(requests.rows.empty() && states.rows.empty() && metrics.rows[2]==0);
    // Reuse the same thread and G address: counters start fresh, generation changes.
    read_scope_enter(&a.r);assert(current_request()->request_id==3 && current_reads()->io_id==0);
    record(&a.r,0,0,0,1);assert(events.rows.back().call_id==1 && events.rows.back().sequence==0);
    record(&a.r,0,4,1,1);read_scope_exit(&a.r);
    std::map<u64,u64> expected;
    for(size_t i=0;i<events.rows.size();++i){
        const auto &e=events.rows[i];assert(e.observation_sequence==i);
        assert(e.request_sequence==expected[e.request_id]++);
        assert(e.pid_tid==(e.request_id==2?tb:ta));
        assert(e.regs[14]==(e.request_id==2?b.r.r14:a.r.r14));
    }
    assert(requests.rows.empty() && states.rows.empty() && metrics.rows[2]==0);
    read_scope_enter(&a.r);auto id=current_request()->request_id;
    read_scope_enter(&a.r);assert(current_request()->request_id==id && metrics.rows[2]==1);
    auto old_g=a.r.r14;a.r.r14=b.r.r14;read_scope_exit(&a.r);assert(metrics.rows[2]==2 && current_request());
    a.r.r14=old_g;read_scope_exit(&a.r);
    requests.fail_update=true;auto before=events.rows.size();read_scope_enter(&a.r);
    assert(events.rows.size()==before && requests.rows.empty() && metrics.rows[2]==3);
}
