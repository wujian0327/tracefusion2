import json
from pathlib import Path
import tempfile
import unittest
from audit_cost_request_records import cohort


class RequestRecordAuditTests(unittest.TestCase):
    def capture(self, root, role, rows, partial=b''):
        p=root/(role+'.jsonl');p.write_bytes(b''.join(json.dumps(r).encode()+b'\n' for r in rows)+partial)
        return p

    def test_same_trace_distinct_spans_and_repeated_frame_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp)
            a=self.capture(r,'a',[{'kind':'start'}, {'kind':'binding-return','frame':'f1','message':'trace/warm'}, {'kind':'read','frame':'f1'}, {'kind':'binding-return','frame':'f2','message':'trace/steady'}, {'kind':'enter','frame':'f3','parent':'f2'}, {'kind':'read','frame':'f3'}])
            b=self.capture(r,'b',[{'kind':'http-json','message':'trace/rpc','parent_message':'trace/steady'}, {'kind':'binding-return','frame':'f1','message':'trace/rpc'}, {'kind':'read','frame':'f1'}])
            d=cohort({'a':a,'b':b},{'trace/steady'})
            self.assertEqual(d['request_records']['a']['events'],3)
            self.assertEqual(d['request_records']['b']['events'],3)
            self.assertEqual(d['outside_cohort_or_global']['a']['events'],3)
            self.assertEqual(d['total_events'],9)

    def test_conflicting_client_identities_are_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);p=self.capture(r,'a',[{'kind':'http-json','message':'t/two','parent_message':'t/one'}])
            with self.assertRaisesRegex(AssertionError,'Two client requests'):
                cohort({'a':p},{'t/one','t/two'})

    def test_partial_final_record_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp);p=self.capture(r,'a',[{'kind':'start'}],b'{"kind":')
            with self.assertRaisesRegex(AssertionError,'partial record'):
                cohort({'a':p},{'t/one'})


if __name__=='__main__':unittest.main()
