"""Bounded amd64 transport adapter. Uses upstream callbacks, not our provenance engine.

The instruction-to-callback mapping is ours, audited against pinned Pin dispatch.
It is NOT the original Pin dispatcher. Unsupported forms must fail closed.
"""
import json
import subprocess
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_IMM, X86_OP_REG, X86_OP_MEM

REGS = {'rdi': 3, 'rsi': 4, 'rbp': 5, 'rsp': 6, 'rbx': 7, 'rdx': 8,
        'rcx': 9, 'rax': 10, **{'r'+str(i): i+3 for i in range(8,16)}}
ALIASES = {}
for root in REGS:
    variants = ([root, 'e'+root[1:], root[1:]] if len(root)==3 and not root[1].isdigit()
                else [root,root+'d',root+'w'])
    for n in variants: ALIASES[n] = root
SUFFIX = {2: 'w', 4: 'l', 8: 'q'}


def require(ok, message):
    if not ok: raise ValueError(message)


def translate(row):
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    raw = bytes.fromhex(row['bytes'])
    instructions = list(md.disasm(raw, row['pc']))
    require(len(instructions)==1 and instructions[0].size==len(raw), 'instruction bytes')
    ins = instructions[0]; ops = ins.operands; op = ins.mnemonic
    def reg(operand):
        name=ins.reg_name(operand.reg)
        require(name in ALIASES and operand.size in SUFFIX, 'register form: '+name)
        return REGS[ALIASES[name]]
    def address(operand):
        require(not operand.mem.segment, 'segment address unsupported')
        def value(r):
            if not r: return 0
            name=ins.reg_name(r)
            if name=='rip': return ins.address+ins.size
            require(name in REGS, 'address register form')
            return row['registers'][name]
        addr=(value(operand.mem.base)+value(operand.mem.index)*operand.mem.scale+operand.mem.disp)&((1<<64)-1)
        require(0<addr<=0x7fffffffffff-32, 'memory address outside upstream range')
        return addr
    def callback(name, *a): return 'call '+name+' '+' '.join(map(str,a))
    def clear(dst):
        require(dst.size in SUFFIX, 'clear width')
        if dst.type==X86_OP_REG: return callback('r_clr'+SUFFIX[dst.size],reg(dst))
        require(dst.type==X86_OP_MEM,'clear target')
        return f'clear {address(dst)} {dst.size}'
    if op in ('mov','add','sub','xor','and','or'):
        require(len(ops)==2 and ops[0].size in SUFFIX,'binary form')
        dst,src=ops
        if src.type==X86_OP_IMM:
            return [clear(dst)] if op=='mov' else []
        require(dst.size==src.size,'operand width mismatch')
        if op in ('sub','xor') and dst.type==src.type==X86_OP_REG and dst.reg==src.reg:
            return [clear(dst)]
        forms={(X86_OP_REG,X86_OP_REG):'r2r', (X86_OP_REG,X86_OP_MEM):'m2r',
               (X86_OP_MEM,X86_OP_REG):'r2m'}
        route=forms.get((dst.type,src.type)); require(route is not None,'binary operands')
        args=[reg(x) if x.type==X86_OP_REG else address(x) for x in ops]
        return [callback(route+('_xfer_op' if op=='mov' else '_binary_op')+SUFFIX[dst.size],*args)]
    if op in ('push','pop'):
        require(len(ops)==1 and ops[0].type==X86_OP_REG and ops[0].size==8,'stack form')
        r=reg(ops[0]); sp=row['registers']['rsp']
        return [callback('r2m_xfer_opq',sp-8,r)] if op=='push' else [callback('m2r_xfer_opq',r,sp)]
    if op=='lea':
        require(len(ops)==2 and ops[0].type==X86_OP_REG and ops[1].type==X86_OP_MEM,'lea form')
        dst=reg(ops[0]); mem=ops[1].mem
        require(not mem.segment,'lea segment')
        names=[ins.reg_name(r) for r in (mem.base,mem.index) if r]
        require(all(n in REGS for n in names),'lea address registers')
        suf=SUFFIX[ops[0].size]
        if not names: return [clear(ops[0])]
        if len(names)==1: return [callback('r2r_xfer_op'+suf,dst,REGS[names[0]])]
        return [callback('_lea_op'+suf,dst,*(REGS[n] for n in names))]
    # These cases do not update tags in the pinned original dispatcher.
    # Deliberately do not silently admit shifts, SIMD, unknown instructions or calls out of scope.
    if op in ('cmp','test','nop','ret','call','jmp','je','jne','ja','jae','jb','jbe',
              'jg','jge','jl','jle','inc','dec'):
        return []
    raise ValueError('unsupported instruction: '+op+' '+ins.op_str)


def run_core(exe, commands):
    p=subprocess.run([str(exe)],input='\n'.join(commands+['end'])+'\n',text=True,
                     capture_output=True,timeout=30)
    require(p.returncode==0,'core rejected: '+p.stderr)
    rows=[json.loads(s) for s in p.stdout.splitlines()]
    require(rows and rows[-1].get('status')=='complete','missing core completion')
    return rows[:-1]


def replay(exe, trace):
    require(trace['schema']=='libdft-offline-trace-v1' and trace['complete'] is True,'trace contract')
    require(trace['steps']==len(trace['instructions']) and 0<trace['steps']<=4096,'trace count')
    commands=[]
    for s in trace['sources']:
        require(s['width']==4 and 1<=s['label']<=3,'source contract')
        commands.append(f"seed {s['address']} {s['width']} {s['label']}")
    audits=[]
    for i,row in enumerate(trace['instructions'],1):
        require(row['step']==i,'sequence gap')
        require(any(a<=row['pc']<b for a,b in trace['ranges']),'execution outside scope')
        # Sample BEFORE each callback, matching the native Pin adapter's CALL_ORDER_FIRST.
        for reg in REGS.values(): commands.append(f'register {reg} 8')
        commands.append(f"memory {trace['sink']['address']} 4")
        operations=translate(row); commands.extend(operations)
        audits.append({'step':i,'pc':row['pc'],'callbacks':operations})
    commands.append(f"memory {trace['sink']['address']} 4")
    rows=run_core(exe,commands)
    require(len(rows)==(len(REGS)+1)*trace['steps']+1,'core output count')
    labels=sorted({x for byte in rows[-1]['bytes'] for x in byte})
    return {'labels':labels,'byte_labels':rows[-1]['bytes'],'steps':trace['steps'],
            'dispatch':audits,'intermediate_tags_before':rows[:-1]}
