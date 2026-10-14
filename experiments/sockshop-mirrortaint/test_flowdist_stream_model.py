import unittest
from flowdist_stream_model import derive


CALLER='<demo.Pipeline: double compute(java.util.List)>'
CALLBACK='<demo.Pipeline: double arbitraryMapper(demo.Value)>'


def pipeline():
    bodies=['s = interfaceinvoke list.<java.util.List: java.util.stream.Stream stream()>()',
        'fn = dynamicinvoke "applyAsDouble" <java.util.function.ToDoubleFunction ()>() <java.lang.invoke.LambdaMetafactory: java.lang.invoke.CallSite metafactory()>(handle: '+CALLBACK+')',
        'ds = interfaceinvoke s.<java.util.stream.Stream: java.util.stream.DoubleStream mapToDouble(java.util.function.ToDoubleFunction)>(fn)',
        'result = interfaceinvoke ds.<java.util.stream.DoubleStream: double sum()>()']
    return [CALLER+' - '+body for body in bodies]+[CALLBACK+' - return arbitraryValue']


class StreamSummaryTests(unittest.TestCase):
    def test_generic_mapper_result_contributes_without_field_or_query_names(self):
        result=derive(pipeline());self.assertEqual(len(result),1)
        self.assertEqual((result[0]['source_variable'],result[0]['target_variable']),('arbitraryValue','result'))
        self.assertEqual(result[0]['edge_type'],'VTE_RET')

    def test_parallel_pipeline_is_not_silently_modelled(self):
        rows=pipeline();rows.insert(1,CALLER+' - parallel = interfaceinvoke s.<java.util.stream.Stream: java.util.stream.Stream parallel()>()')
        self.assertEqual(derive(rows),[])

    def test_unrelated_terminal_receiver_does_not_get_an_edge(self):
        rows=pipeline();rows[3]=rows[3].replace('interfaceinvoke ds.','interfaceinvoke other.')
        self.assertEqual(derive(rows),[])

    def test_no_callback_return_means_no_summary(self):
        self.assertEqual(derive(pipeline()[:-1]),[])

    def test_reassigned_callback_is_unsupported(self):
        rows=pipeline();rows.insert(2,CALLER+' - fn = replacement')
        self.assertEqual(derive(rows),[])

    def test_filtered_intermediate_stream_is_outside_direct_pipeline_model(self):
        rows=pipeline();rows.insert(3,CALLER+' - ds2 = interfaceinvoke ds.<java.util.stream.DoubleStream: java.util.stream.DoubleStream filter(java.util.function.DoublePredicate)>(predicate)')
        rows[4]=rows[4].replace('interfaceinvoke ds.','interfaceinvoke ds2.')
        self.assertEqual(derive(rows),[])


if __name__=='__main__':unittest.main()
