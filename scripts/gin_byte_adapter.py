"""Gin 1.11 boundary adapter reusing the established Go scope planner."""
from copy import deepcopy
import hashlib
import re
import subprocess
from pathlib import Path
from go_byte_adapter import assembly_rows, decode_function, file_offset
from go_provenance import parse_nm
from go_read_provenance import scope_plan
from gin_api_provenance import BOUNDARIES
from hybrid_model import require


def select_observation(plan,mode):
    require(mode in ('full','boundary','selective'),'Unknown observation mode')
    result=deepcopy(plan)
    require(plan.get('observation_mode','full')=='full','Select from a full plan')
    result['observation_mode']=mode
    if mode in ('boundary','selective'):
        selected=set(plan.get('runtime_input_sites',[])) if mode=='selective' else set()
        result['sites']=[s for s in result['sites'] if s['op']!='instruction' or s['id'] in selected]
        ids={s['id'] for s in result['sites']}
        result['event_order']=[s for s in result['event_order'] if s in ids]
        for n in result['instructions']:
            if n.get('site') not in selected:n.pop('site',None)
        result['selected_instruction_sites']=sorted(selected)
        result['replay_contract']='runtime-byte-input-v1' if plan.get('runtime_inputs') else 'closed-four-byte-leaf-v1'
        result['scope']+='; modeled replay between retained observations, within declared input regions'
    return result


def plan_binary(binary,go,env,out,*,cross_role=None,tracing='forward',observation='full',runtime_inputs=None):
    data=binary.read_bytes();sites=[];texts=[]
    nm=subprocess.check_output([go,'tool','nm','-size',str(binary)],env=env,text=True)
    assembly=subprocess.check_output(['objdump','-d','-M','intel','--no-show-raw-insn',str(binary)],text=True)
    symbols=parse_nm(nm)
    config={'functions':['main.transform'],'read_boundary':{'scope_function':'main.run'}}
    def rows(name):
        text=subprocess.check_output([go,'tool','objdump','-s','^'+re.escape(name)+'$',str(binary)],env=env,text=True)
        texts.append(text);return assembly_rows(text)
    def add(row,op,phase,snaps=None):
        offset=file_offset(data,row['address']);code=bytes.fromhex(row['code'])
        require(data[offset:offset+len(code)]==code,'ELF/disassembly mismatch')
        site=dict(id=len(sites),address=row['address'],file_offset=offset,op=op,phase=phase,pair=-1,snapshots=snaps or {})
        sites.append(site);return site['id']
    root=rows('main.run');by_addr={r['address']:r for r in root};ops=[];core_order=[]
    contracts={
        'main.readValue':('source',{'path':{'pointer':'rax','length_reg':'rbx'}},{'value':{'pointer':'rax','length':4}}),
        'main.transform':('work',{'dst':{'pointer':'rax','length':4},'src':{'pointer':'rbx','length':4}},{}),
    }
    if cross_role:
        require(cross_role in ('upstream','downstream'),'Unknown cross-service role')
        contracts['github.com/gin-gonic/gin.(*Context).GetHeader']=('trace',{}, {'trace':{'pointer':'rax','length_reg':'rbx'}})
        if cross_role=='downstream':
            contracts['main.readRemote']=('source',{'path':{'pointer':'rax','length_reg':'rbx'},'trace':{'pointer':'rcx','length_reg':'rdi'}},{'value':{'pointer':'rax','length':4}})
            if tracing=='otel':
                contracts['main.readRemote']=('source',{'path':{'pointer':'rcx','length_reg':'rdi'}},{'value':{'pointer':'rax','length':4}})
    for row in root:
        if not row['asm'].startswith('CALL '):continue
        name=row['asm'].split(None,1)[1].removesuffix('(SB)').removeprefix('local.')
        if name in ('runtime.newobject','runtime.morestack_noctxt.abi0','github.com/gin-gonic/gin.(*Context).JSON'):continue
        if cross_role=='downstream' and name=='main.remoteURL':continue
        if tracing=='otel' and name=='net/http.(*Request).Context':continue
        if runtime_inputs and name=='main.readControl':continue
        require(name in contracts,'Unmodeled business call: '+name)
        op,pre,post=contracts[name];ops.append(op)
        pair=[add(row,op,'pre',pre),add(by_addr[row['address']+len(bytes.fromhex(row['code']))],op,'post',post)]
        if op!='trace':core_order.extend(pair)
    require(ops==(['trace'] if cross_role else [])+['source','source','source','work'],'Business boundary contract changed')
    if cross_role=='downstream':
        remote=rows('main.readRemote');lookup={r['address']:r for r in remote};seen=[]
        transfer={
            'net/http.Header.Set':('http_header',{'key':{'pointer':'rbx','length_reg':'rcx'},'trace':{'pointer':'rdi','length_reg':'rsi'}},{}),
            'io.ReadAll':('http_body',{}, {'body':{'pointer':'rax','length_reg':'rbx'}}),
            'encoding/json.Unmarshal':('decode',{'body':{'pointer':'rax','length_reg':'rbx'}},{}),
        }
        if tracing=='otel':del transfer['net/http.Header.Set']
        for row in remote:
            if not row['asm'].startswith('CALL '):continue
            name=row['asm'].split(None,1)[1].removesuffix('(SB)').removeprefix('local.')
            if name not in transfer:continue
            seen.append(name);op,pre,post=transfer[name]
            add(row,op,'pre',pre);add(lookup[row['address']+len(bytes.fromhex(row['code']))],op,'post',post)
        require(seen==list(transfer),'HTTP decode summary calls changed')
    scopes={}
    def boundary(name,enter_op,enter_snap,exit_op,exit_snap):
        rr=rows(name);lookup={r['address']:r for r in rr}
        scope=scope_plan(assembly,symbols,config,function=name);scopes[name]=scope;base=symbols[name][0]
        entry=add(lookup[base+scope['entry_offset']],enter_op,'pre',enter_snap)
        exits=[add(lookup[base+off],exit_op,'post',exit_snap) for off in scope['return_offsets']]
        return entry,exits
    if cross_role=='downstream' and tracing=='otel':
        boundary('go.opentelemetry.io/otel/propagation.HeaderCarrier.Set','http_header',
                 {'key':{'pointer':'rbx','length_reg':'rcx'},'trace':{'pointer':'rdi','length_reg':'rsi'}},'http_header',{})
    scope_entry,scope_exits=boundary('main.run','scope',{},'scope',{})
    render_entry,_=boundary(BOUNDARIES['render'],'json',{'value':{'pointer':'rdi','length':4}},'render',{})
    boundary(BOUNDARIES['marshal'],'marshal',{'value':{'pointer':'rbx','length':4}},'json',{'json':{'pointer':'rax','length_reg':'rbx'}})
    boundary(BOUNDARIES['writer'],'writer',{'json':{'pointer':'rbx','length_reg':'rcx'}},'writer',{})
    ir=decode_function(rows('main.transform'))
    for n in ir:
        snapshots={}
        if n['op']=='movzx':snapshots={'load':{'address':n['args'][0],'length':1}}
        if n['op']=='test':snapshots={'load':{'address':n['args'][1],'length':1}}
        if n['op']=='cmp' and n['args'][0]['kind']=='mem':snapshots={'load':{'address':n['args'][0],'length':1}}
        n['site']=add(n,'instruction','step',snapshots)
    (out/'disassembly.txt').write_text('\n'.join(texts))
    plan=dict(adapter='gin-byte-array-v1',binary=str(binary),binary_sha256=hashlib.sha256(data).hexdigest(),
        sites=sites,event_order=[s['id'] for s in sites],
        instructions=ir,entry=ir[0]['address'],root_order=core_order+[render_entry],
        abi={'dst_register':'rax','src_register':'rbx','aux_register':'rcx'},region_bytes=4,max_steps=256,
        json_model='gin-byte-array-v1',scope_entry=scope_entry,scope_exits=scope_exits,scopes=scopes,
        cross_role=cross_role,
        trace_mode=tracing,
        scope='Default Gin scheduling; process/G/scope lifetimes; fixed four-byte array JSON summary')

    if runtime_inputs:
        require(runtime_inputs==[dict(register='rdi',length=1)],'Only the declared fourth-argument control byte is supported')
        plan['runtime_inputs']=runtime_inputs
        candidates=[n for n in ir if n['op']=='cmp' and n['args'][0]['kind']=='mem' and
                    n['args'][0]['base']=='rdi' and not n['args'][0]['index'] and n['args'][0]['offset']==0]
        require(len(candidates)==1,'Expected one control-byte comparison site')
        plan['runtime_input_sites']=[n['site'] for n in candidates]

    return select_observation(plan,observation)
