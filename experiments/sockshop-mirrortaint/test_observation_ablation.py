"""Ablation admission and configuration controls, without Docker or fixtures."""
from pathlib import Path
import tempfile
import unittest
from calibrate_mirrortaint_total import common_spec
from run_observation_ablation import POLICIES,normalized_spec,qualified


class AblationControls(unittest.TestCase):
    def test_policy_is_only_deployment_difference(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);build=root/'frozen-build';specs=[]
            for policy in POLICIES:
                trial=root/policy;(trial/'sockshop').mkdir(parents=True)
                spec=common_spec('tracefusion',trial/'sockshop',build,None,observation_policy=policy)
                for role in ('orders','carts'):
                    options=spec['services'][role]['environment']['JAVA_OPTS']
                    self.assertEqual(options.count('-javaagent:'),1)
                    self.assertIn('-Dservice.mode='+policy,options)
                self.assertNotIn('-javaagent:',spec['services']['shipping']['environment']['JAVA_OPTS'])
                specs.append(normalized_spec(spec,trial))
            self.assertEqual(specs[0],specs[1]);self.assertEqual(specs[1],specs[2])

    def test_unknown_control_cannot_qualify_as_accurate_method(self):
        correct={'queries':24,'exact':24,'tp':84,'fp':0,'fn':0,'unknown':0}
        missing={'queries':24,'exact':0,'tp':0,'fp':0,'fn':84,'unknown':24}
        for policy in ('full','selective'):
            self.assertTrue(qualified(policy,correct,24))
            self.assertFalse(qualified(policy,missing,24))
            self.assertFalse(qualified(policy,correct,25))
        self.assertTrue(qualified('boundary',missing,24))
        self.assertFalse(qualified('boundary',correct,24))
        self.assertFalse(qualified('boundary',{**missing,'unknown':23},24))
        self.assertFalse(qualified('boundary',{**missing,'fp':1},24))
        self.assertFalse(qualified('boundary',{**missing,'queries':0,'unknown':0}))

if __name__=='__main__':unittest.main()
