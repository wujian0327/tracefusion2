import unittest
from flowdist_query import validate_methods


class QueryMethodPresenceTest(unittest.TestCase):
    def test_missing_source_cannot_be_a_negative(self):
        with self.assertRaisesRegex(ValueError, 'Source method absent'):
            validate_methods({'traces': [{'source_first': None, 'sink_last': 123}]})

    def test_missing_sink_cannot_be_a_negative(self):
        with self.assertRaisesRegex(ValueError, 'Sink method absent'):
            validate_methods({'traces': [{'source_first': 1, 'sink_last': None}]})

    def test_two_process_method_presence(self):
        validate_methods({'traces': [{'source_first': 1, 'sink_last': None},
                                    {'source_first': None, 'sink_last': 123}]})
