"""Policy failures must not silently fall back to a supposedly safe full mode."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_gin_choice_provenance import choice_evidence,project
from test_gin_byte_provenance import evidence
from gin_byte_boundaries import bind
from gin_byte_adapter import select_observation
from observation_policy import choose_observation,analyze_inputs


def aliased_output(control):
    """Synthetic supported IR/trace: copy destination address to R8, then store
    via R8. Concrete replay handles this, but the older entry certificate only
    permits stores spelled through AX. It is a conservative fallback example,
    not proof that every-read observation is mathematically necessary.
    """
    d,p=choice_evidence(control);old_entry=p['entry'];sid=max(s['id'] for s in p['sites'])+1
    instruction=dict(address=old_entry-3,next=old_entry,site=sid,op='mov',width=64,
        args=[dict(kind='reg',reg='rax',width=64),dict(kind='reg',reg='r8',width=64)],
        asm='MOVQ AX, R8 (synthetic prefix)',code='4989c0')
    p['instructions'].insert(0,instruction);p['entry']=instruction['address']
    p['sites'].append(dict(id=sid,address=instruction['address'],op='instruction',phase='step',pair=-1,snapshots={}))
    p['event_order'].append(sid)
    for n in p['instructions']:
        if n['op']=='mov' and n['args'][-1]['kind']=='mem':
            n['args'][-1]['base']='r8';n['asm']='MOVB SI, (R8)(DX*1) (synthetic alias)';n['code']=''
    pre=next(e for e in d['events'] if e['op']=='work' and e['phase']=='pre')
    first=deepcopy(pre);first.update(site=sid,op='instruction',phase='step',values={})
    for e in d['events']:
        if e['op']=='instruction' or e['op']=='work' and e['phase']=='post':e['registers']['r8']=pre['registers']['rax']
    d['events'].insert(d['events'].index(pre)+1,first)
    for i,e in enumerate(d['events']):e['sequence']=i;e['timestamp']=i
    d['stats']['submitted']=len(d['events']);return d,p


class PolicyTests(unittest.TestCase):
    def test_boundary_and_entry_are_derived_from_reachable_reads(self):
        for variant in ('assign','partial','overwrite'):
            d,p=evidence(variant);p['scope']='synthetic fixture'
            decision=choose_observation(p);self.assertEqual(decision['mode'],'boundary',decision)
            plan=select_observation(p,'auto');doc,_=project(d,p,'boundary')
            self.assertEqual(bind(doc,plan)['status'],'resolved')
        d,p=choice_evidence();decision=choose_observation(p)
        self.assertEqual(decision['mode'],'entry',decision)
        self.assertEqual(len(decision['analysis']['runtime_read_addresses']),1)
        doc,_=project(d,p,'entry');self.assertEqual(bind(doc,select_observation(p,'auto'))['status'],'resolved')

    def test_supported_alias_falls_back_to_observed_reads(self):
        for control in (0,1):
            doc,p=aliased_output(control);full=bind(doc,p);self.assertEqual(full['status'],'resolved',full)
            choice=choose_observation(p);self.assertEqual(choice['mode'],'selective',choice)
            self.assertTrue(any(c['mode']=='entry' and not c['accepted'] for c in choice['candidates']))
            reduced,_=project(doc,p,'selective');actual=bind(reduced,select_observation(p,'auto'))
            self.assertEqual(actual['status'],'resolved',actual)
            self.assertEqual(actual['results'][0]['provenance']['byte_sources'],full['results'][0]['provenance']['byte_sources'])

    def test_unmodeled_or_racy_inputs_are_unsupported_not_full_fallback(self):
        _,original=choice_evidence()
        for case in ('ownership','shared','call','control_store','unknown_load','missing_probe','wrong_snapshot','outside_cfg','branch_flags'):
            p=deepcopy(original);ir=p['instructions']
            if case=='ownership':p.pop('runtime_input_ownership')
            elif case=='shared':p['runtime_input_ownership']='shared'
            elif case=='call':ir[0]['op']='call'
            elif case=='control_store':next(n for n in ir if n['op']=='mov')['args'][-1]['base']='rdi'
            elif case=='unknown_load':next(n for n in ir if n['op']=='movzx')['args'][0]['base']='r9'
            elif case=='missing_probe':p['runtime_input_sites']=[]
            elif case=='wrong_snapshot':next(s for s in p['sites'] if s['id'] in p['runtime_input_sites'])['snapshots']={}
            elif case=='outside_cfg':next(n for n in ir if n['op']=='jmp')['target']=-1
            else:ir[0].update(op='je',args=[],target=ir[1]['address'])
            decision=choose_observation(p)
            self.assertEqual(decision['status'],'unsupported',(case,decision));self.assertIsNone(decision['mode'])
            with self.assertRaises(ValueError,msg=case):select_observation(p,'auto')

    def test_undefined_register_on_one_cfg_path_is_not_covered(self):
        _,p=choice_evidence()
        # SI is first assigned only inside the loop. Replacing the initial XOR
        # with a read of SI must not be legitimized by later loop definitions.
        p['instructions'][0].update(op='mov',args=[dict(kind='reg',reg='rsi',width=64),dict(kind='reg',reg='rdx',width=64)])
        self.assertEqual(choose_observation(p)['status'],'unsupported')

    def test_runtime_guards_still_reject_alias_after_policy_selection(self):
        doc,p=choice_evidence();doc,_=project(doc,p,'entry');plan=select_observation(p,'auto')
        for e in doc['events']:
            if e['op'] in ('work','instruction'):e['registers']['rdi']=e['registers']['rax']
        self.assertEqual(bind(doc,plan)['status'],'unknown')

if __name__=='__main__':unittest.main()
