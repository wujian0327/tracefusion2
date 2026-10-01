"""Execute compiled loops independently and test instance-sensitive provenance."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import loop_provenance as app
from test_interproc_provenance import emulated_events, uc

SCENARIO = app.common.ROOT/'scenarios/loop-provenance'
COUNTS = (0, 1, 2, 4)


@unittest.skipUnless(uc and shutil.which('gcc'), 'Requires GCC/binutils and optional Unicorn')
class LoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.out = Path(cls.temp.name)/'build'; cls.out.mkdir()
        cls.binary, cls.plans, cls.config = app.build(SCENARIO, cls.out)
        cls.events, cls.bases = emulated_events(cls.binary, cls.plans, cls.config, selections=COUNTS)
        cls.oracle = [json.loads(l) for l in subprocess.check_output([str(cls.binary)], text=True).splitlines()]
        cls.stats = dict(backend='unicorn-test-only', received_events=len(cls.events), attempted_events=len(cls.events),
                         lost_events=0, submit_errors=0, state_errors=0, process_returncode=0)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def replay(self, events=None):
        return app.infer(self.events if events is None else events, self.plans, self.config, self.bases)

    def test_native_oracle_zero_one_multiple_iterations(self):
        result = self.replay(); score = app.evaluate(result, self.oracle, self.stats, self.plans)
        self.assertEqual(result['issues'], [])
        self.assertTrue(score['passed'], score)
        self.assertEqual(len(result['results']), 24)
        self.assertEqual(score['read_instance_relations']['fp'], 0)
        self.assertEqual(score['read_instance_relations']['fn'], 0)
        self.assertEqual(len(result['results'][4]['source_reads']), 0)
        self.assertEqual(result['results'][4]['sources'], [])
        self.assertEqual(result['results'][8]['sources'], [])

    def test_overwrite_retains_last_instance_not_all_equal_values(self):
        row = self.replay()['results'][7]  # overwrite, count=4
        self.assertEqual(len(row['source_reads']), 4)
        self.assertEqual([r['id'] for r in row['contributing_reads']], ['input.public_value@read4'])
        graph_reads = {n['local_node'] for n in row['dependency_graph']['nodes'] if n.get('kind') == 'source-read'}
        self.assertEqual(graph_reads, {'input.public_value@read4'})
        self.assertEqual(row['source_reads'][2]['field'], row['source_reads'][3]['field'])
        self.assertNotEqual(row['source_reads'][2]['instruction'], row['source_reads'][3]['instruction'])

    def test_accumulation_and_transform_versions(self):
        rows = self.replay()['results']; accum = rows[11]; transform = rows[3]
        self.assertEqual(len(accum['contributing_reads']), 4)
        self.assertEqual(accum['sources'], ['input.public_value', 'input.secret'])
        self.assertEqual(len(transform['source_reads']), 1)
        self.assertEqual(len(transform['contributing_reads']), 1)
        self.assertGreater(transform['summary']['backward_edges'], 0)
        versions = [n for n in transform['dependency_graph']['nodes'] if n.get('asm', '').startswith('xor ')]
        self.assertEqual(len(versions), 4)
        self.assertEqual(len({n['id'] for n in versions}), 4)

    def test_missing_iteration_even_after_resequencing_is_rejected(self):
        template = [e for e in self.events if e['call_id'] == 8]
        # Cut one entire visit between repeated PCs, concealing the gap in sequence numbers.
        pairs = [(i,j) for i in range(len(template)) for j in range(i+1,len(template))
                 if template[i]['offset'] == template[j]['offset']]
        self.assertTrue(pairs)
        for i,j in pairs:
            rows = copy.deepcopy(template[:i]+template[j:])
            for k,r in enumerate(rows): r['sequence'] = k
            with self.subTest(start=i,end=j):
                result = self.replay(rows)
                self.assertFalse(result['results']); self.assertTrue(result['issues'])

    def test_corruption_loss_budget_and_wrong_read_instance(self):
        template = [e for e in self.events if e['call_id'] == 12]
        for fault in ('register', 'flags', 'input', 'missing-return', 'duplicate', 'depth', 'read-error', 'ip'):
            rows = copy.deepcopy(template)
            if fault == 'register': rows[-2]['regs'][0] ^= 1
            elif fault == 'flags': rows[-2]['flags'] ^= 64
            elif fault == 'input': rows[-2]['inputs'][0] ^= 1
            elif fault == 'missing-return': rows.pop()
            elif fault == 'duplicate': rows.insert(3, copy.deepcopy(rows[3]))
            elif fault == 'depth': rows[3]['depth'] = 2
            elif fault == 'read-error': rows[3]['stack_error'] = -14
            else: rows[3]['ip'] += 1
            with self.subTest(fault=fault):
                self.assertFalse(self.replay(rows)['results'])
        with patch.object(app, 'MAX_EXECUTED_STEPS', 5):
            self.assertFalse(self.replay(template)['results'])
        result = self.replay()
        self.assertFalse(app.evaluate(result, self.oracle, dict(self.stats,lost_events=1), self.plans)['passed'])
        result['results'][7]['contributing_reads'][0]['id'] = 'input.public_value@read3'
        score = app.evaluate(result, self.oracle, self.stats, self.plans)
        self.assertFalse(score['passed'])
        self.assertGreater(score['read_instance_relations']['fp'], 0)
        self.assertGreater(score['read_instance_relations']['fn'], 0)
        self.assertFalse(app.evaluate(self.replay([e for e in self.events if e['call_id']!=8]),
                                      self.oracle,self.stats,self.plans)['passed'])

    def test_unconfigured_iteration_count_and_renamed_functions(self):
        scenario = Path(self.temp.name)/'variant'; shutil.copytree(SCENARIO, scenario)
        for name in ('main.c', 'model.h', 'operations.c', 'config.json'):
            file = scenario/name; text = file.read_text()
            for fn in self.config['functions']: text = text.replace(fn, 'renamed_'+fn)
            text = text.replace('{0, 1, 2, 4}', '{0, 1, 3, 7}').replace('0x55u', '0x66u')
            file.write_text(text)
        out = Path(self.temp.name)/'variant-build'; out.mkdir()
        binary, plans, config = app.build(scenario, out)
        events, bases = emulated_events(binary, plans, config, selections=(0,1,3,7))
        oracle = [json.loads(l) for l in subprocess.check_output([str(binary)], text=True).splitlines()]
        result = app.infer(events, plans, config, bases)
        stats = dict(self.stats, received_events=len(events), attempted_events=len(events))
        self.assertTrue(app.evaluate(result, oracle, stats, plans)['passed'])


if __name__ == '__main__': unittest.main()
