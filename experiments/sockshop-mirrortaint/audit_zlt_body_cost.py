"""Independent measurement attribution and dependency receipts, not inference."""
import argparse,collections,csv,hashlib,json,statistics
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,load,save,sha
from run_zlt_body_cost import BASE,MALL,COMMIT,verify


def mapper_hash(jar):
    with ZipFile(jar)as z:
        names=[n for n in z.namelist()if n.startswith('BOOT-INF/lib/jackson-databind-')and n.endswith('.jar')]
        assert len(names)==1
        with ZipFile(BytesIO(z.read(names[0])))as lib:
            return names[0],hashlib.sha256(lib.read('com/fasterxml/jackson/databind/ObjectMapper.class')).hexdigest()


def dependencies(home):
    verify();proof=[]
    for task in('orders','mall'):
        captures=home/('cal-'+task+'-mirrortaint')
        roles=('orders','carts')if task=='orders'else('mall-admin',)
        for role in roles:
            app=BASE/role/'original.jar'if task=='orders'else ROOT/'artifacts/portability-first-20261028/business-jars/mall-admin.jar'
            entry,digest=mapper_hash(app)
            witness=captures/'sockshop'/role/'native-library.jsonl'if task=='orders'else captures/'capture/native-library.jsonl'
            rows=[json.loads(s)for s in witness.read_text().splitlines()]
            assert len(rows)==1 and rows[0]['sha256']==digest,(task,role,rows,digest)
            proof.append({'task':task,'role':role,'business_jar_sha256':sha(app),'original_library':entry,
                'original_ObjectMapper_sha256':digest,'actual_witness':rows[0],'witness_sha256':sha(witness)})
    for mode in('full','selective','mirrortaint'):
        s=load(home/('cal-orders-'+mode)/'calibration.json');assert s['passed']and s['summary']['exact']==s['summary']['queries']
        s=load(home/('cal-mall-'+mode)/'offline-single-pass/summary.json');assert s['targets']==s['correct']==24
    # Preserve complete mount/config receipts, rather than claiming arbitrary
    # native instrumentation transparency from one mapper definition witness.
    save(home/'dependency-calibration.json',{'passed':True,'native_JAR_unchanged':True,'mapper_witnesses':proof,
        'scope':'Same original per-task JAR/JDK/image/fixtures; actual mapper definition matches that original. Known target and source coordinates independently calibrated. Not a proof of arbitrary MT propagation equivalence.',
        'Orders_MT_adapter_sha256':sha(home/'orders-mt-adapter/build.json'),
        'Mall_MT_adapter':'Unchanged B0; original task boundary, one scored field per deployment, other exported fields remain charged.',
        'native_sha256':sha(ROOT/'artifacts/external-tools/mirrortaint/mirrorTaint.jar')})


def attributable(events,lines,measured,all_messages,parents):
    """Concrete Frame/call/message lineage; no value/time-window matching."""
    frames={}
    for r in events:
        # A transport event can name its RPC child message while referring to
        # the caller Frame. Only root binding facts establish Frame ownership.
        if r['kind']in('binding-input','binding-return','binding-source','binding-opaque-touch')and r.get('frame') and r.get('message'):
            old=frames.get(r['frame']);assert old in(None,r['message']);frames[r['frame']]=r['message']
    for _ in range(len(events)+1):
        changed=False
        for r in events:
            if r['kind']=='enter'and not frames.get(r['frame'])and frames.get(r.get('parent')):
                frames[r['frame']]=frames[r['parent']];changed=True
        if not changed:break
    calls={r['call_id']:frames.get(r.get('frame'))for r in events if r['kind']=='collection-call-enter'}
    roots={r['root']:r.get('context',{}).get('message')for r in events if r['kind']=='target'}
    c=collections.Counter()
    for r,line in zip(events,lines):
        message=r.get('message')or r.get('context',{}).get('message')or frames.get(r.get('frame'))or frames.get(r.get('caller_frame'))or calls.get(r.get('call_id'))or roots.get(r.get('root'))
        seen=set()
        while message and message not in all_messages and message in parents:
            assert message not in seen,'Message parent cycle';seen.add(message);message=parents[message]
        c['batch_events']+=1;c['batch_bytes']+=len(line)
        prefix='measure'if message in measured else'warmup'if message in all_messages else'shared_unattributed'
        c[prefix+'_events']+=1;c[prefix+'_bytes']+=len(line)
    return dict(c)


def counts(trial,task,mode):
    if task=='mall':
        warm=load(trial/'warmup.json')['requests'];measure=load(trial/'measure.json')['requests']
        measured={c['message']for c in measure};messages=measured|{c['message']for c in warm}
        files=[trial/'capture'/n for n in (('native-capability.jsonl','instances.jsonl','native-library.jsonl')if mode=='mirrortaint'else('events.jsonl',))]
    else:
        cases=load(trial/'sockshop/run.json')['cases'];measured={c['message']for c in cases if c['case'].startswith('steady-')};messages={c['message']for c in cases}
        name='instances.jsonl'if mode=='mirrortaint'else'events.jsonl'
        files=[trial/'sockshop'/r/name for r in ('orders','carts')]
        if mode=='mirrortaint':files+=list((trial/'sockshop/orders').rglob('adapted-events.jsonl'))+list((trial/'sockshop').glob('*/native-library.jsonl'))
    # Build cross-role RPC parent relations before classifying any file.
    parents={}
    for f in files:
        for line in f.read_bytes().splitlines():
            r=json.loads(line);message=r.get('message');parent=r.get('parent_message')
            if message and parent:
                assert parents.get(message,parent)==parent,'Ambiguous message parent'
                parents[message]=parent
    result=collections.Counter();decisions=[];kinds=collections.Counter()
    for f in files:
        lines=f.read_bytes().splitlines(keepends=True);events=[json.loads(s)for s in lines]
        # Native exported snapshots have phases instead of protocol kind. Their
        # explicit instance context supplies message ownership.
        normalized=[dict(r,kind=r.get('kind','native-'+str(r.get('phase'))),context=r.get('context',r.get('instance_context',{})))for r in events]
        result.update(attributable(normalized,lines,measured,messages,parents));kinds.update(r['kind']for r in normalized)
        decisions.extend(r['body_observation']for r in events if r.get('body_observation'))
        result['omitted_field_reads']+=sum(r.get('body_observation_omissions',{}).get('field_reads',0)for r in events)
        result['omitted_branches']+=sum(r.get('body_observation_omissions',{}).get('branches',0)for r in events)
    result['selected_body_extents']=sum(bool(d['selected'])for d in decisions)
    result['eligible_body_extents']=sum(bool(d['guard_eligible'])for d in decisions)
    capture=trial/'capture'if task=='mall'else trial/'sockshop'
    if task=='mall':allfiles={str(p.relative_to(capture)):p.stat().st_size for p in capture.rglob('*')if p.is_file()}
    else:
        allfiles={str(p.relative_to(capture)):p.stat().st_size for role in('orders','carts')for p in(capture/role).rglob('*')if p.is_file()}
    result['all_capture_file_bytes']=sum(allfiles.values())
    return {'counts':dict(result),'kind_counts':dict(kinds),'capture_files':allfiles,'scope':'Actual lineage attribution, unmatched/shared retained; not maximum disk I/O. Native diagnostic/class dump files charged separately.'}


def summarize(home):
    assert load(home/'formal-complete.json')['complete'];rows=[]
    for job in load(home/'protocol-before-calibration.json')['jobs']:
        task,mode=job['task'],job['mode'];trial=home/('round-%02d-%s-%s'%(job['round'],task,mode));row=dict(job)
        if task=='mall':
            from run_sockshop_cost import percentiles
            cases=load(trial/'measure.json')['requests'];phase=load(trial/'measure.json');lat=[c['http_seconds']*1000 for c in cases];rs=load(trial/'resource-summary.json')
            row.update(p50_ms=percentiles(lat)['p50'],p95_ms=percentiles(lat)['p95'],p99_ms=percentiles(lat)['p99'],
                completed_rps=len(cases)/60,error_rate=sum(not c['business_passed']for c in cases)/len(cases))
            assert load(trial/'result.json')['business_passed']==180
        else:
            m=load(trial/'metrics.json');rs=m['resources'];p=m['online_latency_ms'];row.update(p50_ms=p['p50'],p95_ms=p['p95'],p99_ms=p['p99'],completed_rps=m['throughput_rps'],error_rate=m['error_rate'])
            assert len(load(trial/'sockshop/run.json')['cases'])==180 and m['status']=='passed'
        # Sampler uses the same fields and one-core CPU convention in both tasks.
        row['resources']=rs
        for prefix,group in [('business','observed_jvms'),('deployment','deployment')]:
            row[prefix+'_cpu_one_core_percent']=rs[group]['cpu_one_core_percent_mean']
            row[prefix+'_RSS_MiB']=rs[group]['rss_bytes_mean']/2**20
            row[prefix+'_peak_RSS_MiB']=rs[group]['rss_bytes_peak']/2**20
        if mode!='original':
            c=counts(trial,task,mode);save(trial/'attribution.json',c);row.update(c['counts'])
            summary=load(trial/'offline-single-pass/process.json')if task=='mall'else load(trial/'offline-single-pass/summary.json')
            assert summary['correct']==summary['targets']==180
            row.update(offline_core_seconds=summary['core_seconds'],offline_VmHWM_MiB=summary['VmHWM_KiB']/1024,
                offline_process_wall_seconds=summary.get('process_wall_seconds',load(trial/'metrics.json')['offline']['subprocess_wall_seconds'])if task=='orders'else summary['process_wall_seconds'])
            row['phases_seconds']=summary['phases_seconds']
            row['targets']=summary['targets'];row['correct']=summary['correct'];row['positive']=summary.get('positive')
            if 'process_cpu_seconds'in summary:row['offline_process_cpu_seconds']=summary['process_cpu_seconds']
        rows.append(row)
    save(home/'results-before-report.json',{'algorithm':COMMIT,'rows':rows,'formal_deployments':40})


def precision(home):
    """Untimed same-capture precision/mandatory-evidence ablations."""
    import copy
    from infer_execution_kernel import infer_execution
    out=home/'precision-ablation';out.mkdir(exist_ok=False);records=[]
    for repeat in range(1,6):
        for mode in('full','selective'):
            trial=home/('round-%02d-mall-%s'%(repeat,mode));raw=trial/'capture/events.jsonl';rows=[json.loads(s)for s in raw.read_text().splitlines()]
            off=copy.deepcopy(load(MALL/'planning-first/mall-swarm-3/002-plan.json'));off['execution_kernel'].pop('source_locality',None);off['execution_kernel'].pop('body_observation',None)
            save(out/('%02d-%s-disabled-plan.json'%(repeat,mode)),off)
            if mode=='full':
                result=infer_execution(off,rows);answers=[a for a in result['answers']if a['path']=='/data/expiresIn']
                assert len(answers)==180 and not any(a['known']for a in answers)
                r={'round':repeat,'mode':mode,'targets':180,'known_without_certificate':0,'state':'unknown'}
            else:
                try:infer_execution(off,rows)
                except ValueError as e:r={'round':repeat,'mode':mode,'state':'rejected_missing_necessary_cut_proof','error':str(e)}
                else:raise AssertionError('Actual cut accepted without its necessary proof')
            r['original_capture_sha256']=sha(raw);records.append(r)
    save(out/'summary.json',{'all_passed':True,'full_targets':900,'full_known_without_certificate':0,
        'selective_cut_batches_rejected_without_proof':5,'timed':False,'same_complete_captures':True,'records':records})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['dependencies','summarize','precision']);p.add_argument('--home',type=Path,required=True);a=p.parse_args();globals()[a.stage](a.home.resolve())
