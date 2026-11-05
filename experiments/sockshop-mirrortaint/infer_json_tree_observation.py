"""Validate physical JSON containers; never infer a DTO decoding edge."""
from query_observation_planner import require
from collections import defaultdict

def validate(plan,rows):
    proofs=[r for r in rows if r['kind']=='json-tree-container']
    require(len({r['seq']for r in proofs})==len(proofs),'Duplicate JSON container proof')
    config=plan.get('json_tree_observation')
    require(not proofs or config,'Unplanned JSON tree observation')
    classes=[r for r in rows if r['kind']=='json-tree-class']
    class_index=defaultdict(list)
    for row in classes:class_index[(row['class'],row['loader'])].append(row)
    proof_index={p['seq']:p for p in proofs}  # uniqueness was checked above
    for proof in proofs:
        require(proof['runtime']in config['profiles'] and config['class_sha256'].get(proof['class'])==proof['class_sha256'],'JSON tree implementation/runtime differs')
        loaded=class_index[(proof['class'],proof['loader'])]
        require(len(loaded)==1 and loaded[0]['class_sha256']==proof['class_sha256'] and loaded[0]['seq']<proof['seq'],'JSON tree loaded class evidence absent/ambiguous')
        require(type(proof['epoch'])is int and type(proof['contents'])is list and len(proof['contents'])<=10000,'JSON tree content/version shape differs')
    for source in (r for r in rows if r['kind']in ('binding-source','binding-input')):
        refs=source.get('json_tree_proofs',[])
        require(len(set(refs))==len(refs),'Duplicate JSON snapshot proof reference')
        selected=[proof_index[s]for s in refs if s in proof_index]
        require(len(selected)==len(refs),'Missing JSON snapshot proof reference')
        require(all(p['seq']<source['seq'] and p['frame']==source['frame'] and p['source_capture']and
                    p['thread']==source['thread']and p.get('message')==source.get('message')and
                    (source['kind']=='binding-input' or p.get('call_id')==source.get('source_call_id'))for p in selected),'JSON source snapshot/call scope differs')
        owner_index=defaultdict(list)
        for proof in selected:owner_index[proof['owner']].append(proof)
        for field in source['fields']:
            if not field.get('json_tree'):continue
            candidates=[p for p in owner_index[field['owner']]if field['path'].startswith(p['path']+'/')]
            require(candidates,'JSON source lacks actual source-container proof')
            proof=max(candidates,key=lambda p:p['seq']);require(field['version']==proof['epoch'],'JSON source version differs')
            require(field['path'].startswith(proof['path']+'/'),'JSON source path differs')
            if field['field'].startswith('@map:'):
                key=field['field'][5:];values=[v['observed']for v in proof['contents']if v['key']==key]
                require(field['path']==proof['path']+'/'+key.replace('~','~0').replace('/','~1'),'JSON source key/path differs')
            else:
                require(field['field'].startswith('@list:'),'Unsupported JSON source field')
                index=int(field['field'][6:]);values=proof['contents'][index:index+1]if index>=0 else[]
                require(field['path']==proof['path']+'/'+str(index),'JSON source member/path differs')
            require(values==[field['observed']],'JSON source physical value/member differs')
