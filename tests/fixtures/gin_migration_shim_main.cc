struct Frame {
    u64 g[4]{0,0,1024,0};char stack[1024]{};u32 input[3]{11,12,99},output[2]{};pt_regs r;
    Frame(){r.r14=reinterpret_cast<u64>(g);r.sp=reinterpret_cast<u64>(stack+512);r.bx=reinterpret_cast<u64>(input);r.ax=reinterpret_cast<u64>(output);}
};
void enter_read(Frame &f,int fd){
    pt_regs regs=f.r;regs.di=fd;regs.si=reinterpret_cast<u64>(f.input);regs.dx=4;regs.r10=fd*4;regs.orig_ax=__NR_pread64;
    bpf_raw_tracepoint_args raw{{reinterpret_cast<u64>(&regs),__NR_pread64}};raw_tracepoint__sys_enter(&raw);
}
void exit_read(Frame &f){
    pt_regs regs=f.r;regs.orig_ax=__NR_pread64;
    bpf_raw_tracepoint_args raw{{reinterpret_cast<u64>(&regs),4}};raw_tracepoint__sys_exit(&raw);
}
int main(){
    Frame a,b,outsider;b.input[0]=22;
    const u64 ta=(321ULL<<32)|400,tb=(321ULL<<32)|401,tc=(321ULL<<32)|402;
    current_tid=ta;read_scope_enter(&a.r);read_scope_enter(&b.r);
    assert(current_request(a.r.r14)->request_id==1 && current_request(b.r.r14)->request_id==2);
    // Two overlapping scopes may share a thread, but have independent reads.
    enter_read(a,4);current_tid=tb;enter_read(b,5);exit_read(b);
    assert(events.rows.back().read_data[0]==22 && current_reads(a.r.r14)->pending);
    current_tid=ta;exit_read(a);assert(events.rows.back().read_data[0]==11);
    // Both invocation stacks follow G, even as two Gs swap the same threads.
    record(&a.r,0,0,0,1);record(&b.r,0,0,0,1);
    current_tid=tc;record(&a.r,0,4,1,1);assert(events.rows.back().call_id==1 && events.rows.back().sequence==1 && events.rows.back().pid_tid==tc);
    current_tid=tb;record(&b.r,0,4,1,1);assert(events.rows.back().call_id==1 && events.rows.back().sequence==1);
    // JSON entry and return can also be on different threads with the same G.
    a.r.ax=17;a.r.bx=0;gin_writer_exit(&a.r);assert(events.rows.back().request_id==1);
    current_tid=tc;gin_render_exit(&b.r);assert(events.rows.back().request_id==2);
    const auto count_before=events.rows.size();
    enter_read(outsider,7);gin_writer_exit(&outsider.r);
    current_tid=(999ULL<<32)|400;enter_read(a,7);gin_writer_exit(&a.r);
    assert(events.rows.size()==count_before);
    current_tid=tc;read_scope_exit(&a.r);current_tid=ta;read_scope_exit(&b.r);
    assert(requests.rows.empty() && states.rows.empty() && metrics.rows[2]==0);
    // Reused G address receives a fresh generation and cleared state.
    read_scope_enter(&a.r);assert(current_request(a.r.r14)->request_id==3 && current_reads(a.r.r14)->io_id==0);
    a.r.ax=reinterpret_cast<u64>(a.output);a.r.bx=reinterpret_cast<u64>(a.input);record(&a.r,0,0,0,1);
    current_tid=tb;record(&a.r,0,4,1,1);assert(events.rows.back().call_id==1);
    read_scope_exit(&a.r);
    std::map<u64,u64> expected;
    for(size_t i=0;i<events.rows.size();++i){
        const auto &e=events.rows[i];assert(e.observation_sequence==i);
        assert(e.request_sequence==expected[e.request_id]++);
        assert(e.regs[14]==(e.request_id==2?b.r.r14:a.r.r14));
    }
    assert(requests.rows.empty() && states.rows.empty() && metrics.rows[2]==0);
    read_scope_enter(&a.r);read_scope_enter(&a.r);assert(metrics.rows[2]==1);
    enter_read(a,4);current_tid=ta;exit_read(a);assert(metrics.rows[2]==2 && current_reads(a.r.r14)->pending);
    current_tid=tb;exit_read(a);read_scope_exit(&a.r);
    requests.fail_update=true;auto before=events.rows.size();read_scope_enter(&a.r);
    assert(events.rows.size()==before && requests.rows.empty() && states.rows.empty() && metrics.rows[2]==3);
}
