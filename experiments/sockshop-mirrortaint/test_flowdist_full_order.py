"""Guard experiment ownership and immediate failure on exited services."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import flowdist_full_order as full


class DeploymentChecks(unittest.TestCase):
    def _existing_resource_is_never_cleaned_up(self, replies):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / 'build'
            build.mkdir()
            apps = {}
            for role in ('orders', 'shipping'):
                data = b'fixture-' + role.encode()
                (build / (role + '-flowdist.jar')).write_bytes(data)
                apps[role] = {'adapted_sha256': hashlib.sha256(data).hexdigest()}
            (build / 'manifest.json').write_text(json.dumps({'kind': 'sockshop-spring-flowdist-boundary-runtime',
                'upstream_commit': full.tool.COMMIT, 'apps': apps}))
            args = SimpleNamespace(repo=root, apps=build, out=root / 'out', project='existing-user-project',
                subnet='10.254.243.0/24', ready_timeout=180)
            with patch.object(full.tool, 'verify_repository'), patch.object(full, 'CachedDeployment') as deployment:
                instance = deployment.return_value
                instance.command.side_effect = [SimpleNamespace(stdout=reply) for reply in replies]
                with self.assertRaisesRegex(ValueError, 'Fresh Docker project'):
                    full.run(args)
                instance.start.assert_not_called()
                instance.compose.assert_not_called()
                instance.diagnostics.assert_not_called()

    def test_existing_project_is_never_cleaned_up(self):
        self._existing_resource_is_never_cleaned_up(['existing-container-id\n'])

    def test_existing_volume_without_containers_is_never_cleaned_up(self):
        self._existing_resource_is_never_cleaned_up(['', '', 'existing-data-volume\n'])

    def test_exited_service_fails_before_health_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'compose.json'
            file.write_text(json.dumps({'services': {'orders': {'image': 'fixture:1'}}}))
            deployment = full.CachedDeployment(SimpleNamespace(project='fixture', ready_timeout=180), root, file)
            image = json.dumps([{'Id': 'fixture-id', 'RepoDigests': ['fixture@sha256:123']}])
            with patch.object(deployment, 'command', return_value=SimpleNamespace(stdout=image)), \
                 patch.object(deployment, 'compose') as compose:
                def reply(*args, **kwargs):
                    return SimpleNamespace(stdout='{"State":"exited"}\n' if args[0] == 'ps' else '')
                compose.side_effect = reply
                with self.assertRaisesRegex(RuntimeError, 'exited during startup'):
                    deployment.start()
                self.assertFalse(any(call.args[0] == 'exec' for call in compose.call_args_list))


if __name__ == '__main__':
    unittest.main()
