"""Byte-level copy state for observed, bounded amd64 call/loop executions.

No source code or expected answer is read here. Stack locations are frame-relative
so Go stack relocation does not turn an old physical stack address into identity.
Indirect memory operands require an observation of their effective address.
Arithmetic is explicit dependency union, not symbolic numerical evaluation.
"""
import re

UNKNOWN=frozenset({'<unknown>'})
EMPTY=frozenset()
GPRS=('AX','BX','CX','DX','DI','SI','R8','R9','R10','R11','R12','R13','R14','R15','BP','SP')
MEM=re.compile(r'^(?:(-?0x[0-9a-f]+|-?\d+))?\((\w+)\)(?:\((\w+)\*(\d+)\))?$')


def operands(asm):
    parts=asm.split(None,1)
    return parts[0],[] if len(parts)==1 else [s.strip() for s in parts[1].split(',')]


def memory(operand):
    m=MEM.fullmatch(operand)
    if not m:return None
    off=int(m[1] or '0',0)
    if 0x80000000<=off<=0xffffffff:off-=1<<32
    return off,m[2],m[3],int(m[4] or 1)


def indirect_operands(asm):
    op,args=operands(asm)
    if op.startswith('NOP') or op=='LEAQ':return []
    return [a for a in args if memory(a) and memory(a)[1] not in ('SP','IP')]


def union(data):return frozenset().union(*data)


class Frame:
    def __init__(self,name,frame_size,heap,registers=None):
        self.name=name;self.size=frame_size;self.heap=heap;self.stack={}
        self.reg={r:[UNKNOWN]*8 for r in GPRS}
        self.reg.update({f'X{i}':[UNKNOWN]*16 for i in range(15)})
        self.reg['X15']=[EMPTY]*16
        if registers:
            for k,v in registers.items():self.reg[k]=list(v)

    def location(self,arg,e):
        m=memory(arg)
        if not m:raise ValueError('Unsupported memory operand: '+arg)
        off,base,index,scale=m
        if base=='SP' and index is None:return self.stack,off
        if base=='IP':raise ValueError('Unmodeled PC-relative memory: '+arg)
        if e is None:raise ValueError('Missing indirect-address observation: '+arg)
        regs=e['registers'];address=(regs[base]+off+(regs[index]*scale if index else 0))&((1<<64)-1)
        sp=regs['SP']
        if sp<=address<sp+self.size+16:return self.stack,address-sp
        return self.heap,address

    def read(self,arg,n,e=None):
        if arg.startswith('$'):return [EMPTY]*n
        if arg in self.reg:return self.reg[arg][:n]
        if '(SB)' in arg:return [UNKNOWN]*n
        store,offset=self.location(arg,e)
        return [store.get(offset+i,UNKNOWN) for i in range(n)]

    def write(self,arg,data,e=None):
        data=list(data);n=len(data)
        if arg in self.reg:
            if arg=='X15':raise ValueError('Write to zero SIMD register')
            self.reg[arg][:n]=data
            if n==4 and arg in GPRS:self.reg[arg][4:]=[EMPTY]*4
            return
        store,offset=self.location(arg,e)
        for i,v in enumerate(data):store[offset+i]=v

    def clobber(self):
        for r in self.reg:
            if r not in ('R14','SP','BP','X15'):self.reg[r]=[UNKNOWN]*len(self.reg[r])

    def apply(self,row,e=None):
        op,args=operands(row['asm'])
        if op in ('MOVQ','MOVL','MOVUPS'):
            n={'MOVQ':8,'MOVL':4,'MOVUPS':16}[op]
            self.write(args[1],self.read(args[0],n,e),e)
        elif op=='LEAQ':self.write(args[1],[UNKNOWN]*8)
        elif op.startswith(('CMP','TEST','NOP')) or op=='POPQ':pass
        elif op in ('XORL','XORQ') and args[0]==args[1]:self.write(args[1],[EMPTY]*(4 if op=='XORL' else 8))
        elif op in ('INCQ','INCL','DECQ','DECL','ADDQ','ADDL','SUBQ','SUBL'):
            if args[-1]=='SP':
                if op!='ADDQ' or args[0]!='$'+hex(self.size):raise ValueError('Unexpected stack adjustment')
                return
            n=8 if op.endswith('Q') else 4
            deps=union([tag for arg in args for tag in self.read(arg,n,e)])
            self.write(args[-1],[deps]*n,e)
        else:raise ValueError('Unsupported copy-machine instruction: '+row['asm'])

    def field(self,arg,width):return union(self.read(arg,width))

    def money_registers(self):return {'Units':self.field('R10',8),'Nanos':self.field('R11',4)}

    def money_stack(self,base=0):
        return {'Units':union([self.stack.get(base+56+i,UNKNOWN) for i in range(8)]),
                'Nanos':union([self.stack.get(base+64+i,UNKNOWN) for i in range(4)])}

    def set_money(self,origins):
        self.clobber()
        self.write('R10',[origins['Units']]*8)
        self.write('R11',[origins['Nanos']]*4)
