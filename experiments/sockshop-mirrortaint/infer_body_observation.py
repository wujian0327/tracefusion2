"""Replay the runtime cut guard from raw coordinates and checked certificates."""
from query_observation_planner import require


def hit(value, owners):
    return isinstance(value,dict) and 'value' not in value and value.get('object') in owners


def references(value, owners):
    if isinstance(value,dict):return hit(value,owners) or any(references(v,owners) for v in value.values() if isinstance(v,(dict,list)))
    if isinstance(value,list):return any(references(v,owners) for v in value)
    return False


def safe_read_call(plan,row,objects):
    getter=plan['collection_getters'].get(row['callee'])
    if getter and getter.get('implementation')==row.get('accessor_implementation') and row.get('getter'):
        return True
    return row['callee'] in ('java/util/Map.get(Ljava/lang/Object;)Ljava/lang/Object;',
                            'java/util/HashMap.get(Ljava/lang/Object;)Ljava/lang/Object;') and (
        row.get('argument_types')==['java.lang.String'] and len(row.get('args',[]))==1
        and isinstance(row['args'][0].get('value'),str)
        and objects.get(row.get('receiver',{}).get('object'),{}).get('type') in ('java/util/HashMap','java/util/LinkedHashMap'))


def validate(plan,rows,certificates):
    cfg=plan['execution_kernel'].get('body_observation')
    if not cfg:
        # An explicit precision ablation may consume an uncut FULL capture.
        # Its unused decision annotations are not authentication evidence.
        require(not any('body_observation_call'in r or r.get('body_observation',{}).get('selected') for r in rows),
                'Actual body omissions have no authentication plan')
        return set()
    require(cfg['version'] in (1,2),'Body observation protocol differs')
    if cfg['version']==2:
        import copy
        from plan_body_observation import attach
        checked=copy.deepcopy(plan);checked['execution_kernel'].pop('body_observation')
        attach(checked)
        require(checked['execution_kernel'].get('body_observation')==cfg,
                'Body cut future-state/continuation proof differs')
    starts=[r for r in rows if r['kind']=='start'];footers=[r for r in rows if r['kind']=='metrics']
    require(len(starts)==len(footers)==1 and not footers[0].get('capture_invalid')
            and not any(r['kind']=='problem' for r in rows),'Body observation needs a complete valid capture')
    mode=starts[0]['mode'];frames={};roots={};cuts=set();pending={};tagged={};done=set();cut_frames={}
    for row in rows:
        kind=row['kind'];frame=row.get('frame')
        if kind=='enter':
            require(frame not in frames,'Body observation Frame ID repeated')
            parent=row.get('parent')
            if row['method']==plan['entry']:
                require(parent is None,'Body observation nested root unsupported')
                root=frame;roots[root]={'certificate':None,'call':None,'objects':{},'body':None,'revoked':None,'source_row':None,'decisions':{}}
            else:root=frames.get(parent,{}).get('root')
            frames[frame]={'root':root,'row':row}
            if root is None:continue
            expected=tagged.get(parent)
            if expected is None:
                matches=[call for call in pending.values() if call['root']==root and call['row']['frame']==parent
                         and call['decision'] and call['decision']['selected']
                         and call['decision']['callee']==row['method'] and row.get('callsite')==call['site']]
                require(len(matches)<=1,'Body cut callee occurrence ambiguous')
                if matches:
                    expected=matches[0]['row']['call_id'];cut_frames.setdefault(expected,[]).append(frame)
            require(row.get('body_observation_call')==expected,'Body effect extent differs from guarded call')
            if expected is not None:tagged[frame]=expected
            continue
        root=frames.get(frame,{}).get('root')
        if root is None:continue
        state=roots[root];objects=state['objects'];owners=set(objects)
        def revoke(reason):
            if state['revoked'] is None:state['revoked']=reason
        if kind=='collection-call-enter':
            touches=hit(row.get('receiver'),owners) or references(row.get('args'),owners)
            if touches and not safe_read_call(plan,row,objects):
                require(frame not in tagged,'Effect-only body reached private graph')
                revoke('private-graph-passed-to-call')
            site=row['method']+'@'+str(row['pc']);candidate=cfg['candidates'].get(site);decision=row.get('body_observation')
            if candidate:
                eligible=state['certificate'] is not None and state['revoked'] is None and not hit(row.get('receiver'),owners) and not references(row.get('args'),owners)
                require(decision and decision['version']==1 and decision['root_frame']==root
                        and decision['callee']==candidate['callee']==row['callee']
                        and decision['guard_eligible']==eligible
                        and decision['source_call_id']==state['call']
                        and decision['ownership_id']==(state['source_row']['ownership_id'] if state['source_row'] else None)
                        and decision['source_seq']==(state['source_row']['seq'] if state['source_row'] else None)
                        and decision['body']==state['body'] and decision['private_owners']==sorted(owners),
                        'Body observation prefix/certificate/argument guard differs')
                require(not decision['selected'] or eligible and mode=='selective' and cfg['enabled'],
                        'Uncertified body observation cut')
                if decision['selected']:cuts.add(row['call_id'])
                state['decisions'][row['call_id']]=decision
            else:require(decision is None,'Body cut at an unplanned callsite')
            require(row['call_id'] not in pending,'Body call ID repeated')
            pending[row['call_id']]={'root':root,'row':row,'site':site,'decision':decision}
        elif kind=='locality-end' and row['valid'] and row['call_id'] in certificates:
            call=pending.get(row['call_id']);source=cfg['source']
            if call and all(call['row'][k]==source[v] for k,v in [('method','caller'),('pc','pc'),('callee','callee')]):
                if state['certificate'] is not None:revoke('source-occurrence-repeated')
                else:
                    state.update(certificate=certificates[row['call_id']],call=row['call_id'],
                        objects=certificates[row['call_id']]['objects'],body=row['body'],source_row=row)
        elif kind in ('collection-call-exit','collection-call-throw'):
            require(row['call_id'] in pending,'Body call completion absent/repeated')
            call=pending.pop(row['call_id'])
            require(row['frame']==call['row']['frame'] and row.get('method',call['row']['method'])==call['row']['method'] and row['pc']==call['row']['pc'],
                    'Body call completion coordinates differ')
            if row['call_id'] in cuts:require(len(cut_frames.get(row['call_id'],[]))==1,'Body cut implementation did not enter/entered twice')
        elif kind in ('exit','abort'):
            require(frame not in done,'Body Frame completion repeated');done.add(frame)
            require(row.get('body_observation_call')==tagged.get(frame),'Body completion lost effect mode')
            omissions=row.get('body_observation_omissions')
            if frame in tagged:
                require(omissions and set(omissions)=={'field_reads','branches'} and all(isinstance(n,int) and n>=0 for n in omissions.values()),
                        'Body observation omission counters absent/invalid')
            else:require(omissions is None,'Omissions outside certified body')
        elif state['certificate'] is not None:
            mutation=kind in ('write','write-version') and (row.get('owner') in owners or hit(row.get('observed'),owners))
            capture=kind=='execution-lambda' and references(row.get('captures'),owners)
            array=kind=='execution-array' and row.get('operation')=='store' and references(row.get('value'),owners)
            if mutation or capture or array:
                require(frame not in tagged,'Effect-only body touched/published private graph')
                revoke('private-graph-write-or-store' if mutation else 'private-graph-capture' if capture else 'private-graph-array-store')
            if kind=='binding-return' and any(d['selected'] for d in state['decisions'].values()):
                require(row['result'].get('object')==state['body'],'Body cut root returned another object')
        if frame in tagged:require(kind not in ('read','branch'),'Effect-only body unexpectedly contains value/path observation')
    require(not pending and all(frame in done for frame in tagged),'Body observation extent not closed')
    return cuts
