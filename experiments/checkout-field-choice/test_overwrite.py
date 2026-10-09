"""Final field definitions and branch pruning, with independent expected origins."""
import copy
import unittest

from test_field_choice import f, analyze


def program():
    # Synthetic forward-only instructions; labels avoid coupling assertions to
    # a particular compiler address. Runtime fixtures separately test real ELF.
    code = [
        'CMPQ SP, 0x10(R14)', 'JBE 0x999', 'PUSHQ BP', 'MOVQ SP, BP', 'SUBQ $0x10, SP',
        'MOVQ AX, 0x20(SP)', 'MOVQ BX, 0x28(SP)', 'MOVB CL, 0x30(SP)', 'MOVB DI, 0x31(SP)',
        'LEAQ 0x100(IP), AX', 'CALL runtime.newobject(SB)',
        'MOVQ 0x20(SP), CX', 'MOVQ 0x38(CX), CX', 'MOVQ CX, 0x38(AX)',
        'MOVZX 0x30(SP), DX', 'TESTL DL, DL', 'JE @second',
        'MOVQ 0x28(SP), CX', 'MOVQ 0x38(CX), CX', 'MOVQ CX, 0x38(AX)',
        'second:', 'MOVZX 0x31(SP), DX', 'TESTL DL, DL', 'JE @final_a',
        'MOVQ 0x28(SP), CX', 'MOVQ 0x38(CX), CX', 'MOVQ CX, 0x38(AX)', 'JMP @return',
        'final_a:', 'MOVQ 0x20(SP), CX', 'MOVQ 0x38(CX), CX', 'MOVQ CX, 0x38(AX)',
        'return:', 'ADDQ $0x10, SP', 'POPQ BP', 'RET',
    ]
    labels = {}; instructions = []
    for instruction in code:
        if instruction.endswith(':'): labels[instruction[:-1]] = 0x100 + len(instructions)*4
        else: instructions.append(instruction)
    rows = []
    for i, instruction in enumerate(instructions):
        for label, address in labels.items(): instruction = instruction.replace('@'+label, hex(address))
        rows.append(dict(address=0x100+i*4, asm=instruction,
                         code='0fb6542430' if instruction.startswith('MOVZX') else '90'))
    return rows


def fixture(first_b, final_b, different=False):
    flow = analyze(program(), 56)
    sites = [dict(id=0, kind='entry', address=flow['entry'])]
    for branch in flow['branches']:
        sites.append(dict(id=len(sites), kind='branch', address=branch['address'], op=branch['op']))
    sites.append(dict(id=len(sites), kind='exit', address=flow['paths'][0]['return_address']))
    selected = [s for s in sites if s['kind']!='branch' or s['address'] in flow['selected_branches']]
    plan = dict(binary_sha256='synthetic', field_offset=56, flow=flow, sites=selected,
                all_sites=sites, event_order=[s['id'] for s in selected], strategy='selected')
    values = [14, 38 if different else 14]
    events = []
    for i, site in enumerate(sites):
        event = dict(timestamp=i+1, pid_tid=(9<<32)|10, g=512, site=site['id'],
                     kind=site['kind'], a=0, b=0, c=0, d=0)
        if i==0: event.update(a=1000, b=2000, c=values[0], d=values[1])
        elif i==3: event.update(a=3000, b=values[int(final_b)])
        else: event['a'] = 0 if (first_b if i==1 else final_b) else 0x40
        events.append(event)
    doc = dict(binary_sha256='synthetic',capture_errors=[],returncode=0,events=events,
               stats=dict(submitted=4,probe_hits=4,pid_rejections=0,lost=0,read_errors=0,submit_errors=0,namespace_errors=0))
    truth = dict(case='synthetic', input_objects=[1000,2000], input_values=values,
                 output_object=3000, output_value=values[int(final_b)], source_candidates=[int(final_b)],
                 source_field_address=2056 if final_b else 1056)
    return plan, doc, truth


class OverwriteTests(unittest.TestCase):
    def test_last_store_kills_first_choice_and_only_second_branch_remains(self):
        flow = analyze(program(),56)
        self.assertEqual(len(flow['paths']),4)
        self.assertEqual({len(p['writes']) for p in flow['paths']},{2,3})
        self.assertEqual(flow['selected_branches'],[flow['branches'][1]['address']])
        for path in flow['paths']:
            self.assertEqual(path['sink'],path['writes'][-1])
            self.assertEqual(path['sink']['input_index'],0 if path['branches'][-1]['taken'] else 1)

    def test_one_uncovered_arm_makes_first_branch_necessary_again(self):
        code=program()
        # Final A arm does not overwrite: the earlier branch now reaches output.
        code[-4]['asm']='NOPL'
        flow=analyze(code,56)
        self.assertEqual(flow['selected_branches'],[b['address'] for b in flow['branches']])
        self.assertEqual({p['sink']['input_index'] for p in flow['paths'] if p['branches'][-1]['taken']},{0,1})

    def test_unknown_or_partial_earlier_write_is_not_hidden_by_later_overwrite(self):
        for asm in ('MOVB CL, 0x38(AX)', 'MOVQ CX, 0x38(BX)', 'CALL unknown.mutate(SB)'):
            code=program();code[13]['asm']=asm
            with self.subTest(asm=asm),self.assertRaises(ValueError):analyze(code,56)

    def test_all_branch_and_selected_policies_agree_with_independent_truth(self):
        for different in (False,True):
            for first_b in (False,True):
                for final_b in (False,True):
                    plan,doc,truth=fixture(first_b,final_b,different)
                    for strategy,count in (('all_branches',4),('selected',3),('boundaries',2)):
                        p=f.strategy_plan(plan,strategy);d=copy.deepcopy(doc)
                        ids={s['id'] for s in p['sites']}
                        d['events']=[e for e in d['events'] if e['site'] in ids]
                        d['stats'].update(submitted=count,probe_hits=count)
                        with self.subTest(different=different,first_b=first_b,final_b=final_b,strategy=strategy):
                            self.assertEqual(len(d['events']),count)
                            self.assertTrue(f.evaluate(p,f.infer(p,d),truth)['passed'])

    def test_sampling_only_the_killed_branch_cannot_resolve_final_origin(self):
        plan,doc,_=fixture(True,False)
        plan['sites']=[s for s in plan['all_sites'] if s['id']!=2]
        doc['events']=[e for e in doc['events'] if e['site']!=2]
        doc['stats'].update(submitted=3,probe_hits=3)
        result=f.infer(plan,doc)
        self.assertEqual(result['status'],'ambiguous')
        self.assertEqual(result['source_candidates'],[0,1])


if __name__=='__main__':unittest.main()
