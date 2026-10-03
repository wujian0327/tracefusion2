"""Migration evidence is required separately from correct JSON/provenance."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_read_provenance import stats,uc
import test_gin_concurrent_provenance as concurrent_tests
history=concurrent_tests.history
import gin_migration_provenance as app
import gin_migration_boundaries as boundary
import gin_concurrent_boundaries as pinned

BUILD=os.environ.get('GIN_MIGRATION_BUILD')


def migrating_history(binary,plans,config,original=None):
    rows,runtime,oracle=copy.deepcopy(original) if original is not None else history(binary,plans,config)
    for e in rows:
        # All four Gs reuse the same threads. Read entry/return stay paired on
        # one TID; migration also occurs inside an in-flight computation.
        if e['kind'] in (3,):worker=400
        elif e['kind'] in (1,2):worker=400+e['io_id']-1
        elif e['kind']==0:worker=402+e['sequence']%2
        else:worker=404
        e['pid_tid']=(321<<32)|worker
    return rows,runtime,oracle


@unittest.skipUnless(BUILD and uc,'requires GIN_MIGRATION_BUILD and Unicorn')
class MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(BUILD);cls.binary=cls.root/'hybrid-demo'
        cls.plans=json.loads((cls.root/'probe-plan.json').read_text());cls.config=json.loads((cls.root/'config.json').read_text())
        cls.original=history(cls.binary,cls.plans,cls.config)
        cls.events,cls.runtime,cls.oracle=migrating_history(cls.binary,cls.plans,cls.config,cls.original)

    def infer(self,events=None):
        return boundary.bind(self.events if events is None else events,self.plans,self.config,self.runtime)

    def test_migration_and_shared_threads_preserve_exact_sources(self):
        inferred=self.infer();self.assertEqual(inferred['issues'],[])
        report=boundary.evaluate(inferred,self.oracle,stats(self.events),self.plans)
        self.assertTrue(report['passed'],report)
        self.assertEqual(report['migration']['migrated_requests'],28)
        self.assertEqual(report['external_source_relations'],dict(tp=28,fp=0,fn=0,precision=1.0,recall=1.0))
        self.assertEqual(self.infer(list(reversed(self.events))),inferred)
        self.assertTrue(all('pid_tid' not in r and r['execution_id']==r['request_id'] for r in inferred['results']))
        self.assertTrue(all(len(r['observed_pid_tids'])==2 for r in inferred['compute_results']))
        self.assertTrue(pinned.bind(self.events,self.plans,self.config,self.runtime)['issues'])

    def test_no_migration_cannot_claim_coverage(self):
        rows,runtime,oracle=copy.deepcopy(self.original)
        inferred=boundary.bind(rows,self.plans,self.config,runtime)
        report=boundary.evaluate(inferred,oracle,stats(rows),self.plans)
        self.assertTrue(report['provenance_checks_passed'])
        self.assertFalse(report['migration_coverage_passed']);self.assertFalse(report['passed'])

    def test_wrong_g_process_generation_sequence_and_missing_boundary_rejected(self):
        for key in ('g','process','request_id','request_sequence'):
            rows=copy.deepcopy(self.events);e=next(e for e in rows if e['kind']==7)
            if key=='g':e['regs'][14]+=0x100000
            elif key=='process':e['pid_tid']+=1<<32
            else:e[key]+=1
            self.assertTrue(self.infer(rows)['issues'],key)
        rows=copy.deepcopy(self.events);rows.pop(next(i for i,e in enumerate(rows) if e['kind']==4))
        for i,e in enumerate(rows):e['observation_sequence']=i
        self.assertTrue(self.infer(rows)['issues'])

    def test_migration_inside_single_syscall_rejected(self):
        rows=copy.deepcopy(self.events);next(e for e in rows if e['kind']==2)['pid_tid']+=1
        self.assertTrue(self.infer(rows)['issues'])

    def test_equal_value_wrong_file_offset_fails(self):
        rows=copy.deepcopy(self.events);rid=next(e['request_id'] for e in rows if e['kind']==1 and e['file_offset']==0)
        for e in rows:
            if e['request_id']==rid and e['kind'] in (1,2):e['file_offset']+=16
        inferred=self.infer(rows);self.assertFalse(inferred['issues'])
        self.assertFalse(boundary.evaluate(inferred,self.oracle,stats(rows),self.plans)['passed'])

    def test_capture_errors_fail(self):
        inferred=self.infer()
        for key in ('lost_events','submit_errors','state_errors'):
            capture=stats(self.events);capture[key]=1
            self.assertFalse(boundary.evaluate(inferred,self.oracle,capture,self.plans)['passed'])



@unittest.skipUnless(BUILD,'requires GIN_MIGRATION_BUILD')
class MigrationHTTPTests(unittest.TestCase):
    def test_actual_unpinned_http_and_independent_thread_evidence(self):
        import signal
        binary=Path(BUILD)/'hybrid-demo'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with (root/'program.stdout.jsonl').open('w') as stdout,(root/'program.stderr.log').open('w') as stderr:
                process=subprocess.Popen([str(binary),'--wait'],cwd=root,stdout=stdout,stderr=stderr)
                try:
                    app.common.wait_stopped(process);process.send_signal(signal.SIGCONT)
                    app.client(root);self.assertEqual(process.wait(timeout=12),0)
                finally:
                    if process.poll() is None:process.kill();process.wait()
            oracle=app.oracle(root);self.assertEqual(len(oracle),28)
            for row in oracle:
                mode=row['mode'];v=0 if mode=='zero' else 0xffffffff if mode=='max' else 424242
                v={'left':(v^0x55)+3,'merge':(v^0x55)+3+v,'overwrite':42}.get(mode,v)
                self.assertEqual(json.loads(row['body']),{'balance':v})
                self.assertEqual(row['status'],200)
            observed=json.loads((root/'program.stderr.log').read_text())
            self.assertTrue(all(r['phase_tids'][0]!=r['phase_tids'][1] and r['phase_tids'][2]!=r['phase_tids'][3] for r in observed),observed)


class MigrationCollectorTests(unittest.TestCase):
    def test_generated_collector_follows_g_across_threads_and_cleans_up(self):
        config=json.loads((app.SCENARIO/'config.json').read_text())
        generated=app.bpf_source([],config)
        generated='\n'.join(line for line in generated.splitlines() if not line.startswith('#include'))
        generated=generated.replace('.delete(','.erase(')
        fixtures=Path(__file__).parent/'fixtures'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'collector.cc';binary=root/'collector'
            source.write_text((fixtures/'gin_concurrent_shim.hpp').read_text()+generated+(fixtures/'gin_migration_shim_main.cc').read_text())
            result=subprocess.run(['g++','-std=c++17','-O1',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(binary)],check=True)


if __name__=='__main__':unittest.main()
