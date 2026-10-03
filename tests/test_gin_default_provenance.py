"""Default scheduling preserves correctness gates without fabricated migration."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest

from test_read_provenance import stats,uc
import test_gin_concurrent_provenance as concurrent_tests
import test_gin_migration_provenance as migration_tests
import gin_default_provenance as app
import gin_default_boundaries as boundary

BUILD=os.environ.get('GIN_DEFAULT_BUILD')
SCHEDULER=dict(gomaxprocs=4,num_cpu=8,gomaxprocs_env_set=False,scheduler_override_flags=[])


def staggered(rows):
    requests=boundary.migration.groups(sorted(rows,key=lambda e:e['observation_sequence']))
    result=[]
    for start in range(0,len(requests),4):
        a,b,c,d=requests[start:start+4]
        # Two at a time, with no batch-wide read/compute/JSON phase ordering.
        result.extend(a[:5]+b[:3]+a[5:]+c[:3]+b[3:]+d[:3]+c[3:]+d[3:])
    for i,e in enumerate(result):e['observation_sequence']=i;e['timestamp']=i*100+1
    return result


@unittest.skipUnless(BUILD and uc,'requires GIN_DEFAULT_BUILD and Unicorn')
class DefaultReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(BUILD);cls.binary=cls.root/'hybrid-demo'
        cls.plans=json.loads((cls.root/'probe-plan.json').read_text());cls.config=json.loads((cls.root/'config.json').read_text())
        cls.original=concurrent_tests.history(cls.binary,cls.plans,cls.config)
        cls.events=staggered(copy.deepcopy(cls.original[0]));cls.runtime=cls.original[1]
        cls.oracle=dict(requests=cls.original[2],scheduler_initial=copy.deepcopy(SCHEDULER),scheduler_final=copy.deepcopy(SCHEDULER))

    def infer(self,rows=None):
        return boundary.bind(self.events if rows is None else rows,self.plans,self.config,self.runtime)

    def test_two_overlapping_requests_without_phase_barriers_or_migration_pass(self):
        result=self.infer();self.assertFalse(result['issues'])
        report=boundary.evaluate(result,self.oracle,stats(self.events),self.plans)
        self.assertTrue(report['passed'],report)
        self.assertEqual(report['concurrency']['max_active_scopes'],2)
        self.assertEqual(report['migration']['migrated_requests'],0)
        self.assertFalse(report['migration_required']);self.assertNotIn('batches',report)
        self.assertEqual(report['external_source_relations'],dict(tp=28,fp=0,fn=0,precision=1.0,recall=1.0))
        self.assertEqual(self.infer(list(reversed(self.events))),result)
        old=boundary.migration.concurrent.evaluate(result,self.oracle['requests'],stats(self.events),self.plans)
        self.assertFalse(old['passed']) # Old forced phase coverage remains strict.

    def test_serial_history_correct_but_concurrency_not_covered(self):
        requests=boundary.migration.groups(copy.deepcopy(self.events));rows=[e for r in requests for e in r]
        for i,e in enumerate(rows):e['observation_sequence']=i;e['timestamp']=i*100+1
        result=self.infer(rows);report=boundary.evaluate(result,self.oracle,stats(rows),self.plans)
        self.assertTrue(report['provenance_checks_passed'])
        self.assertFalse(report['natural_concurrency_coverage_passed']);self.assertFalse(report['passed'])

    def test_natural_migration_is_preserved_when_present(self):
        rows,_,_=migration_tests.migrating_history(self.binary,self.plans,self.config,self.original)
        rows=staggered(rows);result=self.infer(rows)
        report=boundary.evaluate(result,self.oracle,stats(rows),self.plans)
        self.assertTrue(report['passed'],report);self.assertEqual(report['migration']['migrated_requests'],28)

    def test_environment_override_or_missing_runtime_metadata_fails(self):
        result=self.infer()
        for key,value in [('gomaxprocs_env_set',True),('scheduler_override_flags',['asyncpreemptoff']),('gomaxprocs',0)]:
            oracle=copy.deepcopy(self.oracle);oracle['scheduler_initial'][key]=value
            report=boundary.evaluate(result,oracle,stats(self.events),self.plans)
            self.assertTrue(report['provenance_checks_passed']);self.assertFalse(report['passed'])
        self.assertFalse(boundary.default_scheduler({}))

    def test_wrong_source_offset_and_capture_failure_still_fail(self):
        rows=copy.deepcopy(self.events);rid=next(e['request_id'] for e in rows if e['kind']==1 and e['file_offset']==0)
        for e in rows:
            if e['request_id']==rid and e['kind'] in (1,2):e['file_offset']+=16
        result=self.infer(rows);self.assertFalse(result['issues'])
        self.assertFalse(boundary.evaluate(result,self.oracle,stats(rows),self.plans)['passed'])
        result=self.infer()
        for key in ('lost_events','state_errors','submit_errors'):
            capture=stats(self.events);capture[key]=1
            self.assertFalse(boundary.evaluate(result,self.oracle,capture,self.plans)['passed'])

    def test_wrong_g_or_sequence_rejected(self):
        for key in ('g','request_sequence'):
            rows=copy.deepcopy(self.events);e=next(e for e in rows if e['kind']==7)
            if key=='g':e['regs'][14]+=0x100000
            else:e[key]+=1
            self.assertTrue(self.infer(rows)['issues'])


@unittest.skipUnless(BUILD,'requires GIN_DEFAULT_BUILD')
class DefaultHTTPTests(unittest.TestCase):
    def test_actual_http_without_server_scheduling_fixture(self):
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
            oracle=app.oracle(root);self.assertEqual(len(oracle['requests']),28)
            self.assertTrue(boundary.default_scheduler(oracle['scheduler_initial']))
            self.assertTrue(boundary.default_scheduler(oracle['scheduler_final']))
            for row in oracle['requests']:
                mode=row['mode'];v=0 if mode=='zero' else 0xffffffff if mode=='max' else 424242
                v={'left':(v^0x55)+3,'merge':(v^0x55)+3+v,'overwrite':42}.get(mode,v)
                self.assertEqual(json.loads(row['body']),{'balance':v});self.assertEqual(row['status'],200)
                self.assertEqual(row['content_type'],'application/json; charset=utf-8')


class DefaultCollectorContractTests(unittest.TestCase):
    def test_uses_unchanged_migration_collector(self):
        config=json.loads((app.SCENARIO/'config.json').read_text())
        self.assertEqual(app.bpf_source([],config),app.migration.bpf_source([],config))
        source=(app.SCENARIO/'main.go').read_text()
        for forbidden in ('LockOSThread','Gosched','time.Sleep','rendezvous','retireCurrentThread','sync.WaitGroup'):
            self.assertNotIn(forbidden,source)
        self.assertEqual(source.count('runtime.GOMAXPROCS('),1)
        self.assertIn('runtime.GOMAXPROCS(0)',source) # Read only.


if __name__=='__main__':unittest.main()
