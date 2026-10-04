"""Normalize Gin request lifetimes into the existing byte provenance engine.

Only observed event identity and boundary snapshots enter inference. Client
queries, fixture ticket maps and expected source sets are evaluation-only.
"""
from copy import deepcopy
import json
from byte_provenance import infer as infer_bytes, snapshot
from gin_migration_boundaries import groups as validated_groups
from hybrid_model import require
from go_byte_adapter import REGISTERS


def group_events(document,plan):
    require(not document.get('capture_errors') and document['returncode']==0,'Capture failed')
    require(document['binary_sha256']==plan['binary_sha256'],'Binary hash mismatch')
    events=document['events'];stats=document['stats']
    require(events and stats['submitted']==len(events) and not any(stats[k] for k in ('lost','read_errors','submit_errors')),'Incomplete transport')
    require(sorted(e['sequence'] for e in events)==list(range(len(events))),'Missing or duplicated transport sequence')
    ordered=sorted(events,key=lambda e:(e['timestamp'],e['sequence']))
    specs={s['id']:s for s in plan['sites']};active={};generation=0;rows=[];peak=0
    for event in ordered:
        s=specs[event['site']]
        require((event['op'],event['phase'])==(s['op'],s['phase']),'Site contract mismatch')
        require(event['g']>0 and event['registers']['r14']==event['g'],'Observed G mismatch')
        key=(event['pid'],event['g'])
        enter=event['site']==plan['scope_entry'];leave=event['site'] in plan['scope_exits']
        if enter:
            require(key not in active,'Nested scope for same G')
            generation+=1;active[key]=[generation,0];peak=max(peak,len(active))
        require(key in active,'Event outside observed scope')
        rid,seq=active[key];active[key][1]+=1
        rows.append(dict(event,kind=3 if enter else 4 if leave else 0,request_id=rid,request_sequence=seq,
            regs=[event['registers'][r] for r in REGISTERS],pid_tid=(event['pid']<<32)|event['tid']))
        if leave:del active[key]
    require(not active,'Unclosed request')
    # Reuse the previous Gin process/G/generation validation, preserving real
    # TIDs. The transport differs; request-local numbering is offline here.
    return validated_groups(rows),peak


def namespace(result,prefix):
    names={n['id'] for n in result['graph']['nodes']}|{'source:1','source:2','source:3'}
    names.update(n['id'] for n in result['instruction_steps'])
    def convert(v):
        if isinstance(v,str):return prefix+v if v in names else v
        if isinstance(v,list):return [convert(x) for x in v]
        if isinstance(v,dict):return {k:convert(x) for k,x in v.items()}
        return v
    return convert(result)


def bind(document,plan):
    try:
        groups,peak=group_events(document,plan);results=[]
        for request in groups:
            rid=request[0]['request_id'];body=request[1:-1]
            require(body and all(e['op']!='scope' for e in body),'Nested scope')
            framework=[e for e in body if e['op'] in ('json','marshal','writer','render')]
            require([(e['op'],e['phase']) for e in framework]==[
                ('json','pre'),('marshal','pre'),('json','post'),('writer','pre'),('writer','post'),('render','post')],
                'Missing, nested or reordered framework events')
            r,m,mret,w,wret,rret=framework
            require(body[-6:]==framework,'Computation must finish before serialization')
            rp,rv=snapshot(r['values']['value']);mp,mv=snapshot(m['values']['value'])
            require(rp==mp and rv==mv,'Marshal object differs from render object')
            require(r['registers']['rcx']==m['registers']['rax']!=0,'Marshal object type mismatch')
            require(mret['registers']['rdi']==wret['registers']['rbx']==rret['registers']['rax']==0,'JSON or writer error')
            bp,encoded=snapshot(mret['values']['json']);wp,written=snapshot(w['values']['json'])
            require(bp==wp and encoded==written,'Writer did not receive the Marshal slice')
            require(mret['registers']['rcx']>=len(encoded) and w['registers']['rdi']>=len(encoded),'Invalid slice capacity')
            require(r['registers']['rbx']==w['registers']['rax']!=0,'Writer identity mismatch')
            require(wret['registers']['rax']==len(encoded),'Partial response write')
            projected=[e for e in body if e['op'] in ('source','work','instruction')]+[r,mret]
            local_plan=dict(plan,root_order=plan['root_order']+[mret['site']])
            local_doc=dict(document,events=projected,stats=dict(document['stats'],submitted=len(projected)))
            inferred=infer_bytes(local_doc,local_plan)
            require(inferred['status']=='resolved_under_instruction_model','Byte core: '+str(inferred.get('reason')))
            sources=inferred['sources'];inferred=namespace(inferred,'request:%d:'%rid)
            graph=inferred['graph'];output='request:%d:output:result'%rid;writer='request:%d:writer'%rid
            graph['nodes'].append(dict(id=writer,kind='response-writer-accepted',length=len(encoded)))
            graph['edges'].append(dict(source=output,target=writer,kind='same-slice-response-write'))
            graph['identity_scope']='process/G/scope generation; node IDs include request generation'
            tids=sorted({e['tid'] for e in request})
            results.append(dict(request_id=rid,pid=request[0]['pid'],g=request[0]['g'],observed_tids=tids,
                local_sources=sources,body=encoded.decode(),read_paths=[bytes.fromhex(e['values']['path']['hex']).decode() for e in body if e['op']=='source' and e['phase']=='pre'],
                provenance=inferred))
        return dict(status='resolved',results=results,oracle_used_for_inference=False,
            concurrency={'max_active_scopes':peak,'observed_threads':len({e['tid'] for e in document['events']}),
                         'migrated_requests':sum(len(r['observed_tids'])>1 for r in results)})
    except (ValueError,KeyError,TypeError,IndexError,UnicodeError) as exc:
        return dict(status='unknown',reason=str(exc),results=[])
