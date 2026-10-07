"""Go ABI and objdump-to-IR adapter for a bounded leaf byte function.

Only region/ABI contracts are configured. No transform input/output relation
or source index mapping is supplied to the instruction interpreter.
"""
import hashlib
import re
import subprocess
from go_string_adapter import file_offset, physical_probes
from hybrid_model import BRANCHES, require

REGISTERS=['rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp']+['r'+str(i) for i in range(8,16)]
GO_REGS=dict(zip(['AX','BX','CX','DX','SI','DI','BP','SP']+['R'+str(i) for i in range(8,16)],REGISTERS))
LOW={'AL':'rax','BL':'rbx','CL':'rcx','DL':'rdx'}
PT_REGS={r:r[1:] if r in REGISTERS[:8] else r for r in REGISTERS}


def assembly_rows(text):
    rows=[]
    for line in text.splitlines():
        m=re.match(r'\s*(\S+:\d+)\s+(0x[0-9a-f]+)\s+([0-9a-f]+)\s+(.+)',line)
        if m:rows.append({'location':m[1],'address':int(m[2],16),'code':m[3],'asm':m[4].strip()})
    return rows


def operand(text,width):
    text=text.strip()
    if text in GO_REGS or text in LOW:
        return {'kind':'reg','reg':(GO_REGS|LOW)[text],'width':8 if text in LOW else width}
    if text.startswith('$'):return {'kind':'imm','value':int(text[1:],0),'width':width}
    m=re.fullmatch(r'(-?(?:0x[0-9a-f]+|\d+))?\((\w+)\)(?:\((\w+)\*([1248])\))?',text)
    require(m is not None and m[2] in GO_REGS and (not m[3] or m[3] in GO_REGS),'Unsupported operand: '+text)
    return {'kind':'mem','base':GO_REGS[m[2]],'index':GO_REGS.get(m[3]),
            'scale':int(m[4] or 1),'offset':int(m[1] or '0',0),'width':width}


def decode_function(rows):
    require(0<len(rows)<=64,'Leaf function outside instruction budget')
    result=[]
    for i,row in enumerate(rows):
        op,_,args=row['asm'].partition(' ')
        n=dict(row,op=op.lower(),args=[],next=rows[i+1]['address'] if i+1<len(rows) else None)
        if op.lower() in BRANCHES|{'jmp'}:
            require(re.fullmatch(r'0x[0-9a-f]+',args) is not None,'Indirect branch unsupported')
            n['target']=int(args,16)
        elif op=='RET':n['op']='ret'
        elif op.startswith('NOP'):n['op']='nop'
        elif op=='MOVZX':
            require(row['code'].startswith('0fb6'),'Only byte-to-32-bit zero extension supported')
            left,right=args.split(',')
            n.update(op='movzx',args=[operand(left,8),operand(right,32)])
            require(n['args'][0]['kind']=='mem' and n['args'][1]['kind']=='reg','Expected byte load')
        elif op in ('MOVB','MOVL','MOVQ','LEAQ','XORL','XORQ','SUBQ','ADDQ','CMPQ','CMPL','CMPB','TESTB','TESTL','TESTQ','INCQ'):
            width={'B':8,'L':32,'Q':64}[op[-1]]
            # Go objdump can print TESTL SI, SI for 40 84 f6 (TEST SIL,SIL).
            # For register TEST derive width from the actual opcode, not that mnemonic.
            if op.startswith('TEST') and '(' not in args:
                code=bytes.fromhex(row['code']);raw=code[1:] if 0x40<=code[0]<=0x4f else code
                require(len(raw)==2 and raw[0] in (0x84,0x85) and raw[1]&0xc0==0xc0,'Unsupported register TEST encoding')
                width=8 if raw[0]==0x84 else 64 if len(code)==3 and code[0]&8 else 32
                require(not (width==8 and len(code)==2 and (raw[1]&7>=4 or (raw[1]>>3)&7>=4)),
                        'High byte register TEST unsupported')
            parsed=[operand(a,width) for a in args.split(',')]
            n.update(op=op[:-1].lower(),width=width,args=parsed)
            require(len(parsed)==(1 if op=='INCQ' else 2),'Wrong operand count')
            if n['op']=='mov':
                require((parsed[1]['kind']=='reg' and width in (32,64)) or
                        (width==8 and parsed[1]['kind']=='mem' and parsed[0]['kind']=='reg'),'Unsupported move/partial register write')
                require(parsed[0]['kind']!='mem','Loads must use explicit byte MOVZX')
            elif n['op']=='lea':require(parsed[0]['kind']=='mem' and parsed[1]['kind']=='reg','Unsupported LEA')
            elif n['op']=='cmp':
                require(all(a['kind'] in ('reg','imm') for a in parsed) or
                        (width==8 and parsed[0]['kind']=='mem' and parsed[1]['kind']=='imm'),'Unsupported comparison')
            elif n['op']=='test':require(parsed[0]['kind']=='reg' and parsed[1]['kind'] in ('mem','reg'),'Unsupported TEST')
            else:require(parsed[-1]['kind']=='reg' and all(a['kind'] in ('reg','imm') for a in parsed),'Unsupported arithmetic')
        else:raise ValueError('Unsupported leaf instruction: '+row['asm'])
        result.append(n)
    addresses={n['address'] for n in result}
    for n in result:
        if 'target' in n:require(n['target'] in addresses,'Branch leaves leaf function')
        if n['op'] not in ('ret','jmp'):require(n['next'] in addresses,'Fallthrough outside function')
    require(sum(n['op']=='ret' for n in result)==1,'Requires one leaf return')
    return result


def plan_binary(binary,go,env,out):
    data=binary.read_bytes();sites=[];texts=[];root_ops=[]
    contracts={
        'main.readValue':('source',{'path':{'pointer':'rax','length_reg':'rbx'}},{'value':{'pointer':'rax','length':4}}),
        'main.transform':('work',{'dst':{'pointer':'rax','length':4},'src':{'pointer':'rbx','length':4}},{}),
        'main.marshalResult':('json',{'value':{'pointer':'rax','length':4}},{'json':{'pointer':'rax','length_reg':'rbx'}}),
    }
    def disasm(name):
        text=subprocess.check_output([go,'tool','objdump','-s','^'+re.escape(name)+'$',str(binary)],env=env,text=True)
        texts.append(text);return assembly_rows(text)
    def site(row,op,phase,pair,snapshots):
        offset=file_offset(data,row['address']);code=bytes.fromhex(row['code'])
        require(data[offset:offset+len(code)]==code,'ELF bytes differ from disassembly')
        s=dict(id=len(sites),address=row['address'],file_offset=offset,op=op,phase=phase,pair=pair,snapshots=snapshots)
        sites.append(s);return s['id']
    root=disasm('main.run');by_address={r['address']:r for r in root}
    pair=0
    for row in root:
        if not row['asm'].startswith('CALL '):continue
        callee=row['asm'].split(None,1)[1].strip().removesuffix('(SB)').removeprefix('local.')
        if callee in ('runtime.newobject','runtime.morestack_noctxt.abi0'):continue
        require(callee in contracts,'Unmodeled root call: '+callee)
        op,pre,post=contracts[callee];root_ops.append(op)
        code=bytes.fromhex(row['code']);resume=row['address']+len(code)
        require(code[0]==0xe8 and resume in by_address,'Expected CALL/continuation')
        site(row,op,'pre',pair,pre);site(by_address[resume],op,'post',pair,post);pair+=1
    require(root_ops==['source','source','source','work','json'],'Root operation contract changed')
    ir=decode_function(disasm('main.transform'))
    for n in ir:
        snapshots={}
        if n['op']=='movzx':snapshots={'load':{'address':n['args'][0],'length':1}}
        if n['op']=='test' and n['args'][1]['kind']=='mem':snapshots={'load':{'address':n['args'][1],'length':1}}
        n['site']=site(n,'instruction','step',-1,snapshots)
    (out/'disassembly.txt').write_text('\n'.join(texts))
    return {'adapter':'go-amd64-byte-instructions-v2','binary':str(binary),
            'binary_sha256':hashlib.sha256(data).hexdigest(),'sites':sites,
            'event_order':[s['id'] for s in sites], # physical attachment order, not the dynamic trace
            'root_order':list(range(10)),'instructions':ir,'entry':ir[0]['address'],
            'abi':{'dst_register':'rax','src_register':'rbx','aux_register':'rcx'},
            'region_bytes':4,'max_steps':256,
            'scope':'Configured boundaries; automatic leaf instruction/CFG decoding; one request/goroutine; separate four-byte regions'}
