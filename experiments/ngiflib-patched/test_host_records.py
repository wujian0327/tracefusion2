"""Transport tests built from synthetic original-ELF records, never host evidence.

Run with --local /path/to/check_query_local_output --validation /path/to/normal.
External labels below are deliberate test doubles, NOT libdft64 outputs.
"""
import argparse
import copy
import json
from pathlib import Path
import query
from host_records import normalize,NAMES


def protocol_fixture(plan,trace,data,taint):
    rows=[];bias=0x550000000000;step=0;reads=0;refills=0;shifts=0;cursor=0
    symbols=plan['symbols'];ins={r['address']:r for r in plan['instructions']}
    parent=trace['records'][0]['parent_pointer'];file=0x60000000
    def emit(kind,pc=0,**kw):
        r=dict(record=len(rows)+1,kind=kind,pc=pc+bias if pc else 0,tid=1,**kw);rows.append(r);return r
    for name in NAMES:
        s=symbols[name];emit('symbol',name=name,begin=s['address']+bias,end=s['address']+s['size']+bias)
    emit('load_enter',symbols['LoadGif']['address'],parent=parent,cursor=cursor)
    emit('decoder_enter',symbols['DecodeGifImg']['address'])
    def read(name,chunk,source=False,call=None,ctx=None):
        nonlocal cursor,reads,refills
        reads+=1
        emit('read_enter',symbols[name]['address'],read=reads,name=name,offset=cursor,count=len(chunk),
             destination=call['before']['rsi'] if name=='GetByteStr' else 0,parent=parent,file=file,
             in_word=call is not None,sp=call['before']['rsp']-8 if call else 0x20010000,
             return_pc=call['resume']+bias if call else symbols['LoadGif']['address']+bias)
        if source:refills+=1
        emit('read_exit',symbols[name]['address'],read=reads,offset=cursor,data=chunk.hex(),source=source,
             version=refills,result=0 if name=='GetByteStr' else chunk[0],
             byte_labels=[[cursor+i+1] for i in range(len(chunk))] if source and taint else [])
        cursor+=len(chunk)
    first_offset=trace['records'][0]['calls'][0]['input_offset']
    while cursor<first_offset:read('GetByte',data[cursor:cursor+1])
    for record in trace['records']:
        emit('word_enter',symbols['GetGifWord']['address'],sequence=record['sequence'],context_pointer=record['context_pointer'],
             image_pointer=record['image_pointer'],parent_pointer=parent,return_pc=record['return_pc']+bias,
             metadata_clean=True,**record['entry'])
        calls={c['pc']:copy.deepcopy(c) for c in record['calls']}
        for pc in record['instruction_pcs']:
            step+=1;ignored=ins[pc]['op'] in ('shr','shl','sar');shifts+=ignored
            emit('instruction',pc,sequence=record['sequence'],step=step,known=True,ignored_shift=ignored)
            if pc in calls:
                c=calls[pc]
                emit('call_enter',pc,name=c['name'],resume=c['resume']+bias,registers=c['before'])
                query.check(c['input_offset']==cursor,'Fixture read cursor')
                read(c['name'],bytes.fromhex(c['data']),c['name']=='GetByteStr',c,record['context_pointer'])
                emit('call_exit',c['resume'],call_pc=pc+bias,registers=c['after'])
        # Empty labels intentionally test transport's separation from scoring.
        emit('word_exit',record['instruction_pcs'][-1],sequence=record['sequence'],byte_labels=[[],[]] if taint else [],**record['exit'])
    emit('decoder_exit',symbols['DecodeGifImg']['address'],result=0)
    while cursor<len(data)-1:read('GetByte',data[cursor:cursor+1])
    emit('load_exit',symbols['LoadGif']['address'],result=1,cursor=cursor)
    emit('load_enter',symbols['LoadGif']['address'],parent=parent,cursor=cursor)
    read('GetByte',data[cursor:cursor+1])
    emit('load_exit',symbols['LoadGif']['address'],result=0,cursor=cursor)
    emit('finish',exit_code=0,taint=taint,bad=False,active=False,threads=1,contexts=0,loads=2,decoders=1,
         words=len(trace['records']),sinks=len(trace['records']),reads=reads,refills=refills,steps=step,
         ignored_shifts=shifts,cursor=cursor,input_bytes=len(data),performance_eligible=False)
    return rows


def run(plan,trace,data):
    passed=[]
    for taint in (False,True):
        rows=protocol_fixture(plan,trace,data,taint)
        transport,external,detail=normalize(rows,plan,data,taint)
        replay=query.infer(plan,transport,data)
        original=query.infer(plan,trace,data)
        query.check([r['source_file_offsets'] for r in replay['queries']]==[r['source_file_offsets'] for r in original['queries']],'Transport changed replay')
        query.check(len(external)==(len(trace['records']) if taint else 0),'Taint/observation separation')
        query.check(detail['instruction_paths']==[r['instruction_pcs'] for r in trace['records']],'PC relocation mismatch')
        passed.append('positive_taint_test_double' if taint else 'positive_observer_transport')
    def reject(name,edit):
        rows=protocol_fixture(plan,trace,data,True);edit(rows)
        try:
            transport,_,_=normalize(rows,plan,data,True)
            query.infer(plan,transport,data)
        except (ValueError,KeyError):passed.append(name)
        else:raise AssertionError('Fault accepted: '+name)
    def first(rows,kind):return next(r for r in rows if r['kind']==kind)
    reject('missing_finish',lambda r:r.pop())
    reject('missing_record',lambda r:r.pop(10))
    reject('error_flag',lambda r:r[-1].update(bad=True))
    reject('lost_thread_identity',lambda r:first(r,'word_enter').update(tid=2))
    reject('context_change',lambda r:r[-1].update(contexts=1))
    reject('symbol_size_mismatch',lambda r:r[0].update(end=r[0]['end']+1))
    reject('wrong_relocation',lambda r:r[1].update(begin=r[1]['begin']+4096,end=r[1]['end']+4096))
    reject('unknown_dispatcher',lambda r:first(r,'instruction').update(known=False))
    reject('shift_coverage_mislabel',lambda r:next(x for x in r if x['kind']=='instruction' and x['ignored_shift']).update(ignored_shift=False))
    reject('wrong_call_target',lambda r:first(r,'call_enter').update(name='GetByteStr'))
    reject('wrong_source_identity',lambda r:first(r,'read_enter').update(offset=1))
    reject('input_contents_changed',lambda r:first(r,'read_exit').update(data='00'))
    reject('failed_reader',lambda r:next(x for x in r if x['kind']=='read_exit' and x['source']).update(result=1))
    reject('missing_source_tags',lambda r:next(x for x in r if x['kind']=='read_exit' and x['source']).update(byte_labels=[]))
    reject('unseeded_sink_tag',lambda r:first(r,'word_exit').update(byte_labels=[[1],[]]))
    reject('wrong_source_version',lambda r:next(x for x in r if x['kind']=='read_exit' and x['source']).update(version=999))
    reject('dirty_metadata',lambda r:first(r,'word_enter').update(metadata_clean=False))
    reject('unterminated_process',lambda r:r[-1].update(active=True))
    reject('truncated_file',lambda r:r[-1].update(cursor=len(data)-1))
    reject('return_value_corruption',lambda r:first(r,'word_exit')['registers'].update(rax=12345))
    return dict(synthetic_transport=True,native_executed=False,libdft_executed=False,checks=passed,total=len(passed))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--local',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path)
    args=p.parse_args();plan=json.loads(args.plan.read_text())
    trace=json.loads((args.local/'blocks-truecolor/trace.json').read_text());data=(args.validation/'blocks/normal.gif').read_bytes()
    result=run(plan,trace,data)
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
