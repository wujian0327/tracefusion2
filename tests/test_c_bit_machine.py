"""ISA differential and source-identity checks for the bounded C bit machine."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from c_bit_machine import Machine, Value, value, decode, REGS, UNKNOWN
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64
from unicorn import x86_const as x86


class CBitMachineTests(unittest.TestCase):
    def run_both(self, raw, registers):
        code = bytes.fromhex(raw)
        m = Machine(dict.fromkeys(REGS,0))
        cpu = Uc(UC_ARCH_X86,UC_MODE_64); cpu.mem_map(0x1000,4096); cpu.mem_write(0x1000,code)
        for name,v in registers.items():
            m.reg[name] = value(v,64)
            cpu.reg_write(getattr(x86,'UC_X86_REG_'+name.upper()),v)
        for row in decode(code,0x1000).values():
            m.step(row)
        cpu.emu_start(0x1000,0x1000+len(code))
        for name in REGS:
            self.assertEqual(m.reg[name].number,cpu.reg_read(getattr(x86,'UC_X86_REG_'+name.upper())))
        return m

    def test_partial_registers_and_shift_values_against_isa(self):
        # Includes 16/32/64-bit destinations, high-bit preservation, zero
        # extension, sign extension by SAR, and x86 shift-count masking.
        for raw in ('66 89 d0','89 d0','0f b7 c2','0f b6 c2','d3 e0','66 d3 e0','48 d3 e0',
                    'd3 e8','d3 f8','66 d3 f8','48 d3 f8','66 09 d0','66 21 d0','66 31 d0','01 d0','29 d0'):
            for n in (0,1,7,8,9,15,16,31,32,63,64):
                self.run_both(raw,dict(rax=0xfedcba9876543210,rdx=0x800100ff,rcx=n))

    def test_shift_mask_origins_match_bit_perturbation(self):
        # For each independent byte, enumerate its bit flips against real ISA
        # output. No reference to the interpreter's propagation implementation.
        code = bytes.fromhex('d3 e8 66 21 d0')  # shr eax,cl; and ax,dx
        for shift,mask in ((0,0xff),(3,0x1ff),(8,0x3ff),(15,0x7f),(24,0xff),(31,0x1)):
            m = Machine(dict.fromkeys(REGS,0))
            m.reg['rax'] = Value(0x965a3cc3,tuple(frozenset({str(i//8)}) if i<32 else frozenset() for i in range(64)))
            m.reg['rcx'] = value(shift,64); m.reg['rdx'] = value(mask,64)
            for row in decode(code,0x1000).values(): m.step(row)
            cpu = Uc(UC_ARCH_X86,UC_MODE_64);cpu.mem_map(0x1000,4096);cpu.mem_write(0x1000,code)
            def run(v):
                cpu.reg_write(x86.UC_X86_REG_RAX,v);cpu.reg_write(x86.UC_X86_REG_RCX,shift);cpu.reg_write(x86.UC_X86_REG_RDX,mask)
                cpu.emu_start(0x1000,0x1000+len(code));return cpu.reg_read(x86.UC_X86_REG_RAX)&65535
            baseline = run(0x965a3cc3)
            relevant = {str(i//8) for i in range(32) if run(0x965a3cc3 ^ (1<<i)) != baseline}
            self.assertEqual(m.regread('ax').origins,relevant)

    def test_equal_values_overwrite_identity_and_partial_kill(self):
        m=Machine(dict.fromkeys(REGS,0));m.region(0x2000,8)
        m.store(0x2000,value(0x7777,16,frozenset({'old'})))
        m.store(0x2000,value(0x77,8,frozenset({'new'})))
        self.assertEqual(m.load(0x2000,8).origins,{'new'})
        self.assertEqual(m.load(0x2001,8).origins,{'old'})
        m.reg['rax']=value(0x1234,64,frozenset({'old'}))
        m.regwrite('ax',value(0x1234,16,frozenset({'new'})))
        self.assertEqual(m.regread('ax').origins,{'new'})
        self.assertEqual(m.reg['rax'].origins,{'old','new'})
        m.regwrite('eax',value(0,32))
        self.assertFalse(m.reg['rax'].origins)

    def test_unknown_and_outside_regions_rejected(self):
        m=Machine(dict.fromkeys(REGS,0));m.region(0x2000,2)
        with self.assertRaises(ValueError):m.load(0x2000,16)
        m.store(0x2000,value(1,16))
        with self.assertRaises(ValueError):m.load(0x2001,16)
        with self.assertRaises(ValueError):m.address(dict(base='rax',index=None,scale=1,offset=0))
        with self.assertRaises(ValueError):decode(bytes.fromhex('48 f7 e3'),0x1000) # unsupported MUL
        m.reg['rax']=value(0,64,UNKNOWN)
        rows=decode(bytes.fromhex('85 c0 74 00 90'),0x1000)
        m.step(rows[0x1000])
        with self.assertRaises(ValueError):m.step(rows[0x1002])


if __name__ == '__main__':unittest.main()
