"""Validate raw Pin transport before either result is scored. No GIF oracle."""
import hashlib
import json
from pathlib import Path
import query

check = query.check
NAMES = ['GetGifWord','GetByte','GetByteStr','DecodeGifImg','LoadGif']


def read_log(path,plan,data,taint):
    return normalize([json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()],plan,data,taint)


def normalize(rows,plan,data,taint):
    check(rows and [r['record'] for r in rows] == list(range(1,len(rows)+1)), 'Missing/reordered raw record')
    check(rows[-1]['kind']=='finish' and sum(r['kind']=='finish' for r in rows)==1, 'Missing/duplicate completion')
    check(not any(r['kind']=='error' for r in rows), 'Adapter reported an error')
    f=rows[-1]
    check(f['taint'] is taint and f['exit_code']==0 and not f['bad'] and not f['active'] and
          f['threads']==1 and f['contexts']==0 and f['loads']==2 and f['decoders']==1 and
          f['words']==f['sinks'] and f['words']>0 and f['cursor']==f['input_bytes']==len(data) and
          f['performance_eligible'] is False, 'Invalid process or capture completion')
    symbols=rows[:5]
    check([r['kind'] for r in symbols]==['symbol']*5 and [r['name'] for r in symbols]==NAMES, 'Wrong symbol inventory')
    biases=set()
    for r in symbols:
        s=plan['symbols'][r['name']]
        check(r['end']-r['begin']==s['size'],'Symbol size differs from ELF')
        biases.add(r['begin']-s['address'])
    check(len(biases)==1,'Inconsistent image relocation')
    bias=biases.pop(); ins={r['address']:r for r in plan['instructions']}
    seeded=set()
    records=[]; external=[]; diagnostics=[]; active=None; pending_call=None; pending_read=None
    cursor=0; read_index=0; source_version=0; step=0; shift_count=0
    loading=False; decoding=False; load_returns=[]; decoder_returns=[]; owner=None; parent=None; file=None
    def pc(r):return r['pc']-bias
    def in_symbol(r,name):
        s=plan['symbols'][name];check(s['address']<=pc(r)<s['address']+s['size'],'PC outside '+name)
    def registers(r):
        result=r['registers'];check(set(result)==set(query.REGS) and all(type(v)is int and 0<=v<1<<64 for v in result.values()),'Invalid register snapshot')
        return dict(result)
    def canonical_labels(labels):
        check(isinstance(labels,list) and all(type(n)is int and 1<=n<=len(data) for n in labels) and labels==sorted(set(labels)),'Unknown/noncanonical source label')
        result={n-1 for n in labels}
        check(result <= seeded, 'Sink label outside seeded source region')
        return result
    for r in rows[5:-1]:
        kind=r['kind']
        if owner is None:owner=r['tid']
        check(r['tid']==owner,'Thread changed')
        if kind=='load_enter':
            in_symbol(r,'LoadGif');check(not loading and not decoding and active is None and r['cursor']==cursor,'Unexpected load entry')
            loading=True
            if parent is None:parent=r['parent']
            check(parent>0 and parent==r['parent'],'Parent identity changed')
        elif kind=='load_exit':
            in_symbol(r,'LoadGif');check(loading and not decoding and active is None and pending_read is None and r['cursor']==cursor,'Unexpected load exit')
            loading=False;load_returns.append(r['result'])
        elif kind=='decoder_enter':
            in_symbol(r,'DecodeGifImg');check(loading and not decoding and active is None,'Unexpected decoder entry');decoding=True
        elif kind=='decoder_exit':
            in_symbol(r,'DecodeGifImg');check(decoding and active is None and pending_read is None,'Unexpected decoder exit')
            decoding=False;decoder_returns.append(r['result'])
        elif kind=='word_enter':
            check(decoding and active is None and pending_read is None and pc(r)==plan['symbols']['GetGifWord']['address'] and r['sequence']==len(records)+1,'Unexpected word entry')
            check(r['parent_pointer']==parent,'Word parent identity differs')
            registers(r)
            if taint:check(r['metadata_clean'] is True,'Tagged metadata violates declared query projection')
            active=dict(sequence=r['sequence'],context_pointer=r['context_pointer'],image_pointer=r['image_pointer'],
                        parent_pointer=parent,return_pc=r['return_pc'],entry=dict(registers=registers(r),context=r['context']),calls=[])
            diagnostics.append([])
        elif kind=='instruction':
            check(active is not None and r['sequence']==active['sequence'] and r['step']==step+1 and pc(r) in ins,'Missing/wrong instruction diagnostic')
            if taint:check(r['known'] is True,'Undispatched opcode in target function')
            shift=ins[pc(r)]['op'] in ('shl','shr','sar')
            check(r['ignored_shift'] is shift,'Shift diagnostic differs from actual ELF')
            shift_count+=shift;step+=1;diagnostics[-1].append(pc(r))
        elif kind=='call_enter':
            check(active is not None and pending_call is None and pending_read is None and diagnostics[-1][-1]==pc(r),'Unexpected call entry')
            row=ins[pc(r)]
            check(row['op']=='call' and r['name'] in ('GetByte','GetByteStr') and row['args'][0]['value']==plan['symbols'][r['name']]['address'] and r['resume']-bias==row['next'],'Wrong direct call target/resume')
            pending_call=dict(name=r['name'],pc=pc(r),resume=row['next'],before=registers(r))
        elif kind=='read_enter':
            name=r['name'];check(name in ('GetByte','GetByteStr'),'Unknown reader')
            in_symbol(r,name)
            check(loading and pending_read is None and r['read']==read_index+1 and r['offset']==cursor and r['parent']==parent and
                  r['in_word'] is (active is not None) and 0<=r['count']<=255 and cursor+r['count']<=len(data),'Read sequence/identity mismatch')
            if file is None:file=r['file']
            check(file>0 and r['file']==file,'FILE identity changed')
            if name=='GetByte':check(r['count']==1 and r['destination']==0,'Byte read schema mismatch')
            if active is not None:
                check(pending_call is not None and name==pending_call['name'] and r['return_pc']-bias==pending_call['resume'] and
                      r['sp']+8==pending_call['before']['rsp'],'Reader does not match observed call')
                if name=='GetByteStr':
                    check(r['destination']==pending_call['before']['rsi'] and r['count']==pending_call['before']['rdx']&0xffffffff,'Read argument mismatch')
            pending_read=r;read_index+=1
        elif kind=='read_exit':
            check(pending_read is not None and r['read']==read_index and r['offset']==cursor,'Unexpected reader return')
            in_symbol(r,pending_read['name']);chunk=bytes.fromhex(r['data'])
            check(len(chunk)==pending_read['count'] and chunk==data[cursor:cursor+len(chunk)],'Read payload mismatch')
            if pending_read['name']=='GetByteStr':check(r['result']==0,'Read failed')
            else:check(r['result']&255==chunk[0],'Byte result mismatch')
            source=active is not None and pending_read['name']=='GetByteStr'
            check(r['source'] is source,'Wrong source boundary')
            if source:
                source_version+=1
                seeded.update(range(cursor,cursor+len(chunk)))
                check(pending_read['destination']==active['context_pointer']+plan['layout']['ngiflib_decode_context']['byte_buffer'] and chunk,'Source buffer mismatch')
                if taint:
                    check(r['byte_labels']==[[cursor+i+1] for i in range(len(chunk))],'Incorrect original-libdft source seeding')
                else:check(r['byte_labels']==[],'Observer unexpectedly has taint labels')
            else:check(r['byte_labels']==[],'Tags outside declared source boundary')
            check(r['version']==source_version,'Source version discontinuity')
            if active is not None:
                check(pending_call is not None and 'data' not in pending_call,'Duplicated helper read')
                pending_call.update(input_offset=cursor,data=r['data'])
            cursor+=len(chunk);pending_read=None
        elif kind=='call_exit':
            check(pending_call is not None and pending_read is None and active is not None and 'data' in pending_call and
                  pc(r)==pending_call['resume'] and r['call_pc']-bias==pending_call['pc'],'Unexpected helper continuation')
            pending_call['after']=registers(r);active['calls'].append(pending_call);pending_call=None
        elif kind=='word_exit':
            check(active is not None and pending_call is None and pending_read is None and r['sequence']==active['sequence'] and
                  pc(r) in ins and ins[pc(r)]['op']=='ret' and diagnostics[-1][-1]==pc(r),'Unexpected word return')
            active['exit']=dict(registers=registers(r),context=r['context']);records.append(active)
            labels=r['byte_labels']
            if taint:
                check(len(labels)==2,'Missing AX byte labels')
                origins=set().union(*(canonical_labels(x) for x in labels))
                external.append(dict(sequence=active['sequence'],value=r['registers']['rax']&65535,
                                     source_file_offsets=sorted(origins),byte_labels=labels))
            else:check(labels==[],'Observer unexpectedly supplies inference')
            active=None
        else:raise ValueError('Unexpected record kind '+kind)
    check(not loading and not decoding and active is None and pending_call is None and pending_read is None and
          load_returns==[1,0] and decoder_returns==[0] and len(records)==f['words'] and read_index==f['reads'] and
          source_version==f['refills'] and step==f['steps'] and shift_count==f['ignored_shifts'] and cursor==len(data),'Incomplete/counter-mismatched native trace')
    trace=dict(backend='pin-ngif-boundaries-v1',transport_checked=True,synthetic=False,complete=True,errors=[],
               binary_sha256=plan['binary_sha256'],input_sha256=hashlib.sha256(data).hexdigest(),decoder_return=0,records=records)
    detail=dict(instruction_paths=diagnostics,ignored_shift_executions=shift_count,raw_records=len(rows),source_fills=source_version,
                semantic_qualification=False,performance_eligible=False)
    return trace,external,detail
