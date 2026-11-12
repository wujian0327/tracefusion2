import unittest
from identity_lifecycle_protocol import validate

class LifecycleProtocolTests(unittest.TestCase):
    def rows(self):return [{'kind':'start','identity_lifecycle_version':1},{'kind':'metrics','lifecycle':{'ids_allocated':120000,'ids_registered':3,'ids_retired':119997,'ids_weak_cleared':119997,'ids_terminal_deferred':0,'field_version_entries':6,'field_versions_retired':119997,'field_cleanup_pending':0,'array_version_entries':0,'array_slot_entries':0}}]
    def test_cumulative_above_old_bound(self):validate(self.rows())
    def test_missing_metrics(self):
        with self.assertRaises(ValueError):validate(self.rows()[:1])
    def test_reused_or_inconsistent_ids(self):
        r=self.rows();r[1]['lifecycle']['ids_allocated']=119999
        with self.assertRaises(ValueError):validate(r)
    def test_negative_counter(self):
        r=self.rows();r[1]['lifecycle']['field_cleanup_pending']=-1
        with self.assertRaises(ValueError):validate(r)
    def test_unknown_protocol(self):
        r=self.rows();r[0]['identity_lifecycle_version']=2
        with self.assertRaises(ValueError):validate(r)
    def test_old_capture(self):validate([{'kind':'start'},{'kind':'metrics'}])
    def test_new_counters_without_version(self):
        r=self.rows();r[0].pop('identity_lifecycle_version')
        with self.assertRaises(ValueError):validate(r)
