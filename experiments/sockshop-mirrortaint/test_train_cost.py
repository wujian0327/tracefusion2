import tempfile
from pathlib import Path
import unittest
from run_train_cost import ROLES,JVM,spec_for,business_matches
from run_sockshop_cost import Sampler
from run_planned_service import save


class TrainCostProtocolTests(unittest.TestCase):
    def test_resource_total_uses_all_five_jvms_and_keeps_database_separate(self):
        names=['ts-'+r+'-service' for r in ROLES]+['db-'+str(i) for i in range(4)]
        sampler=Sampler(dict.fromkeys(names,'unused'),1,Path('/unused'),observed_roles=names[:5])
        for i in range(3):
            sampler.rows.append({name:{'monotonic_ns':(i+1)*10**9,'cpu_ns':i*10**8,'rss_bytes':1000,'container_memory_bytes':2000} for name in names})
        r=sampler.summary(0,4*10**9)
        self.assertAlmostEqual(r['observed_jvms']['cpu_one_core_percent_mean'],50)
        self.assertEqual(r['observed_jvms']['rss_bytes_peak'],5000)
        self.assertEqual(r['deployment']['rss_bytes_peak'],9000)

    def test_spec_business_and_jvm_configuration_only_differs_by_observer(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);inputs=root/'inputs.json';save(inputs,{r:{'image':'example/'+r+'@sha256:fixed'} for r in ROLES})
            normalized=[]
            for mode in ('original','full','selective'):
                dest=root/mode;dest.mkdir();spec=spec_for(mode,dest,root/'build',inputs)
                for r in ROLES:
                    cfg=spec['services']['ts-'+r+'-service'];self.assertTrue(cfg['environment']['JAVA_OPTS'].startswith(JVM))
                    self.assertEqual(cfg['mem_limit'],'768m');self.assertEqual(cfg['cpus'],1)
                    cfg['environment']['JAVA_OPTS']=cfg['environment']['JAVA_OPTS'].split(' -javaagent:')[0]
                    cfg['volumes']=[v for v in cfg['volumes'] if v.endswith(':/tf2/app.jar:ro')]
                normalized.append(spec)
            self.assertEqual(normalized[0],normalized[1]);self.assertEqual(normalized[0],normalized[2])

    def test_expected_business_fallback_is_not_transport_error(self):
        c={'expected_status':0,'expected_prices':{'economyClass':'95.0','confortClass':'120.0'}}
        self.assertTrue(business_matches(c,200,{'status':0,'data':{'prices':c['expected_prices']}}))
        self.assertFalse(business_matches(c,500,{'status':0,'data':{'prices':c['expected_prices']}}))
        self.assertFalse(business_matches(c,200,{'status':0,'data':{'prices':{}}}))
        self.assertFalse(business_matches(c,200,[]))


if __name__=='__main__':unittest.main()
