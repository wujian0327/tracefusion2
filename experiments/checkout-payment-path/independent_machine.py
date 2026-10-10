"""Independent bounded amd64 execution plus SSA backward dependency queries.

No import of payment_adapter, Frame, numeric-flow analysis, selection functions,
fixture cases or truth. ABI/callee contracts belong to the separate binder.
Both method controls share this engine; they are not published-tool reproductions.
"""
from dataclasses import dataclass
import copy
import re

GPRS = ('AX','BX','CX','DX','DI','SI','R8','R9','R10','R11','R12','R13','R14','R15','BP','SP')
REGS = GPRS + tuple('X'+str(i) for i in range(16))
AGG = ('AX','BX','CX','DI','SI','R8','R9','R10','R11')
COND = {'JE','JNE','JG','JGE','JL','JLE','JBE','JA'}
LOW = {'AL':'AX','BL':'BX','CL':'CX','DL':'DX'}
MEM = re.compile(r'(-?(?:0x[0-9a-f]+|\d+))?\((\w+)\)(?:\((\w+)\*([1248])\))?')

def check(ok, reason):
    if not ok: raise ValueError(reason)

def split(asm):
    op, _, args = asm.partition(' ')
    return op, [x.strip() for x in args.split(',')] if args else []

def memory(arg):
    m = MEM.fullmatch(arg)
    if not m: return None
    offset = int(m[1] or '0', 0)
    if 0x80000000 <= offset <= 0xffffffff: offset -= 1 << 32
    return offset, m[2], m[3], int(m[4] or 1)

def signed(v, width):
    v &= (1 << width)-1
    return v-(1 << width) if v & (1 << (width-1)) else v

def taken(op, flags):
    z,s,o,c = (bool(flags & (1 << k)) for k in (6,7,11,0))
    return {'JE':z,'JNE':not z,'JG':not z and s==o,'JGE':s==o,'JL':s!=o,'JLE':z or s!=o,'JBE':c or z,'JA':not c and not z}[op]

def flags(op, left, right, width, previous=None):
    mask=(1 << width)-1; left &= mask; right &= mask
    subtract=op in ('cmp','sub','dec')
    value=(left-right if subtract else left & right if op=='test' else left ^ right if op=='xor' else left+right)&mask
    sign=1 << (width-1)
    carry=left<right if subtract else left+right>mask if op in ('add','inc') else False
    overflow=bool((left^right)&(left^value)&sign) if subtract else bool(~(left^right)&(left^value)&sign) if op in ('add','inc') else False
    result=int(carry)|int(value==0)<<6|int(bool(value&sign))<<7|int(overflow)<<11
    if op in ('inc','dec'): result=(result&~1)|((previous or 0)&1)
    return result

class Graph:
    def __init__(self):
        self.nodes=[dict(parents=(),label=None,pc=None),dict(parents=(),label='<unknown>',pc=None)]
        self.cache={}
    def make(self, pc, parents=(), label=None):
        parents=tuple(sorted(set(parents)-{0}))
        if not parents and label is None: return 0
        key=pc,parents,label
        if key not in self.cache:
            self.cache[key]=len(self.nodes); self.nodes.append(dict(parents=parents,label=label,pc=pc))
        return self.cache[key]
    def backward(self, roots):
        todo=list(roots); seen=set(); labels=set(); instructions=set()
        while todo:
            n=todo.pop()
            if n in seen: continue
            seen.add(n); row=self.nodes[n]
            if row['label']: labels.add(row['label'])
            if row['pc'] is not None: instructions.add(row['pc'])
            todo.extend(row['parents'])
        return dict(origins=sorted(labels),instructions=sorted(instructions),nodes=len(seen))

@dataclass(frozen=True)
class Byte:
    value: object
    definition: int

def word(value, size, definition=0):
    return [Byte(None if value is None else (value >> (8*i))&255, definition) for i in range(size)]

def number(data):
    return None if any(x.value is None for x in data) else sum(x.value << (8*i) for i,x in enumerate(data))

class State:
    def __init__(self, graph, heap=None):
        self.graph=graph; self.heap={} if heap is None else heap; self.reg={r:word(None,16 if r.startswith('X') else 8,1) for r in REGS}
        self.reg['X15']=word(0,16); self.flags=None; self.stack={}; self.base=0; self.frame=0
        self.regions=[]; self.private=[]
    def clone(self):
        s=copy.copy(self); s.heap=self.heap.copy(); s.reg={r:list(v) for r,v in self.reg.items()}; s.stack=self.stack.copy(); s.regions=list(self.regions); s.private=list(self.private)
        return s
    def rnum(self,r,width=8): return number(self.reg[LOW.get(r,r)][:1 if r in LOW else width])
    def setreg(self,r,data):
        check(r!='X15','Mutation of Go zero SIMD register')
        actual=LOW.get(r,r); n=len(data); self.reg[actual][:n]=list(data)
        if n==4 and actual in GPRS: self.reg[actual][4:]=word(0,4)
    def region(self, base, size, clean=False, private=False):
        check(base and size>=0,'Invalid region')
        if private: self.private.append((base,size))
        else: self.regions.append((base,size))
        for i in range(size): self.heap.setdefault(base+i,Byte(None,0 if clean else 1))
    def location(self,arg,event=None):
        m=memory(arg); check(m is not None,'Unsupported memory operand '+arg)
        off,base,index,scale=m
        if base=='SP' and index is None: return self.stack,off
        check(base!='IP','Unmodeled PC-relative data read')
        if event is not None:
            regs=event['registers']; addr=(regs[base]+off+(regs[index]*scale if index else 0))&((1<<64)-1)
            if regs['SP']<=addr<regs['SP']+self.frame+16: return self.stack,addr-regs['SP']
        else:
            b=self.rnum(base); ix=0 if index is None else self.rnum(index)
            check(b is not None and ix is not None,'Unknown effective address '+arg)
            addr=(b+off+ix*scale)&((1<<64)-1)
            if self.base<=addr<self.base+self.frame+16: return self.stack,addr-self.base
        check(any(a<=addr and addr< a+n for a,n in self.regions+self.private),'Read/write outside declared region '+hex(addr))
        return self.heap,addr
    def read(self,arg,size,event=None):
        if arg.startswith('$'): return word(int(arg[1:],0),size)
        if arg in REGS or arg in LOW: return self.reg[LOW.get(arg,arg)][:size]
        if '(SB)' in arg:
            check('money.ErrInvalidValue' in arg or 'money.ErrMismatchingCurrency' in arg,'Unknown global '+arg)
            return word(1,size)  # explicit configured non-nil initialized error metadata
        store,offset=self.location(arg,event)
        if store is self.heap: check(any(a<=offset and offset+size<=a+n for a,n in self.regions+self.private),'Read spans undeclared region')
        return [store.get(offset+i,Byte(None,1)) for i in range(size)]
    def write(self,arg,data,event=None):
        if arg in REGS or arg in LOW: self.setreg(arg,data); return
        store,offset=self.location(arg,event)
        if store is self.heap: check(any(a<=offset and offset+len(data)<=a+n for a,n in self.regions+self.private),'Write spans undeclared region')
        for i,b in enumerate(data): store[offset+i]=b
    def clobber(self, barrier=False):
        for r in REGS:
            if r in ('SP','BP','R14','X15'): continue
            if barrier and r in GPRS and r!='R11': continue
            self.reg[r]=word(None,len(self.reg[r]),1)
        self.flags=None
    def apply(self,row,event=None):
        op,args=split(row['asm']); pc=row['address']
        if op in ('MOVQ','MOVL','MOVUPS'):
            n={'MOVQ':8,'MOVL':4,'MOVUPS':16}[op]
            data=self.read(args[0],n,event)
            self.write(args[1],[Byte(b.value,self.graph.make(pc,[b.definition])) for b in data],event)
        elif op=='MOVSXD':
            d=self.read(args[0],4,event); v=number(d)
            hi=word(None if v is None else (0xffffffff if v&0x80000000 else 0),4,d[-1].definition)
            self.write(args[1],d+hi,event)
        elif op=='LEAQ':
            m=memory(args[0])
            if m and m[1]=='IP': value=row['address']+len(bytes.fromhex(row['code']))+m[0]
            elif m:
                off,base,index,scale=m; b=self.rnum(base); ix=0 if index is None else self.rnum(index)
                value=None if b is None or ix is None else b+off+ix*scale
            else: value=None  # SB type symbol; only opaque runtime allocation metadata
            self.write(args[1],word(value,8))
        elif op.startswith(('CMP','TEST')):
            if args[0]=='runtime.writeBarrier(SB)': self.flags='barrier'; return
            n=8 if op.endswith('Q') else 1 if any(x in LOW for x in args) else 4
            left=number(self.read(args[0],n,event)); right=number(self.read(args[1],n,event))
            self.flags=None if left is None or right is None else flags('test' if op.startswith('TEST') else 'cmp',left,right,n*8)
        elif op in ('SETL','SETLE'):
            check(isinstance(self.flags,int),'Unknown SET condition')
            # Condition influence is not a queried direct numeric source.
            self.write(args[0],word(int(taken('JL' if op=='SETL' else 'JLE',self.flags)),1))
        elif op in ('XORL','XORQ','ADDQ','ADDL','SUBQ','SUBL','INCQ','INCL','DECQ','DECL','IMULQ','IMULL','SARQ'):
            n=8 if op.endswith('Q') else 4
            if args[-1]=='SP':
                check(op=='ADDQ' and args[0]=='$'+hex(self.frame),'Unexpected stack adjustment'); return
            if op.startswith('XOR'):
                check(args[0]==args[1],'Only zero XOR supported'); self.write(args[1],word(0,n)); self.flags=flags('xor',0,0,n*8); return
            if len(args)==1:
                left=self.read(args[0],n,event); right=word(1,n)
            elif len(args)==3:
                check(op.startswith('IMUL'),'Unsupported ternary op'); left=self.read(args[0],n,event); right=self.read(args[1],n,event)
            else:
                left=self.read(args[-1],n,event); right=self.read(args[0],n,event)
            l,r=number(left),number(right); kind=op[:-1].lower()
            node=self.graph.make(pc,[x.definition for x in left+right])
            value=None
            if l is not None and r is not None:
                value=l+r if kind in ('add','inc') else l-r if kind in ('sub','dec') else signed(l,n*8)*signed(r,n*8) if kind=='imul' else signed(l,n*8) >> (r&63)
                if kind in ('add','inc','sub','dec'): self.flags=flags(kind,l,r,n*8,self.flags if isinstance(self.flags,int) else None)
                else: self.flags=None
            else: self.flags=None
            self.write(args[-1],word(value,n,node),event)
        elif op.startswith('NOP') or op=='POPQ': pass
        else: raise ValueError('Unsupported independent instruction '+row['asm'])

def live_registers(model, call_effect):
    rows=model['rows']; by={r['address']:r for r in rows}; live={a:set() for a in by}
    def regs(arg):
        if arg in REGS or arg in LOW: return {LOW.get(arg,arg)}
        m=memory(arg)
        return set() if not m else {r for r in (m[1],m[2]) if r in REGS}
    changed=True
    while changed:
        changed=False
        for row in reversed(rows):
            op,args=split(row['asm']); uses=set(); kills=set()
            successors=[]
            if op in COND or op=='JMP':
                target=int(args[0],16)
                if target in by: successors.append(target)
                if op in COND and row.get('next') in by: successors.append(row['next'])
                if op in COND: uses.add('FLAGS')
            elif op!='RET' and row.get('next') in by: successors.append(row['next'])
            if op=='RET': uses.update(AGG)
            elif op=='CALL':
                u,k=call_effect(args[0]); uses.update(u); kills.update(k); kills.add('FLAGS')
            elif op.startswith('MOV') or op=='LEAQ':
                uses.update(regs(args[0])); uses.update(regs(args[1]) if memory(args[1]) else ())
                if args[1] in REGS: kills.add(args[1])
            elif op.startswith(('CMP','TEST')):
                uses.update(set().union(*(regs(x) for x in args))); kills.add('FLAGS')
            elif op.startswith(('XOR','ADD','SUB','INC','DEC','IMUL','SAR')):
                if not(op.startswith('XOR') and args[0]==args[-1]): uses.update(set().union(*(regs(x) for x in args)))
                kills.update((args[-1],'FLAGS'))
            following=set().union(*(live[a] for a in successors))
            value=uses|(following-kills)
            if value!=live[row['address']]: live[row['address']]=value; changed=True
    return live
