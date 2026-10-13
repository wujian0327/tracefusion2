"""Optional independent callee HTTP observer for fresh service runs."""
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import time

HERE = Path(__file__).resolve().parent
IMAGE = 'python@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111'


def command(args, merge=False):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT if merge else subprocess.PIPE, timeout=30).stdout


class WireCapture:
    def __init__(self, project, out):
        self.project, self.out = project, out
        self.observers, self.errors = [], []
        self.metadata = {'capture_image': IMAGE, 'deployment_project': project, 'containers': {},
                         'capture_source_sha256': hashlib.sha256((HERE / 'capture_http_peer.py').read_bytes()).hexdigest()}

    def start(self):
        command(['docker', 'image', 'inspect', IMAGE])
        for name in ('orders', 'carts', 'user', 'payment', 'shipping'):
            info = json.loads(command(['docker', 'inspect', self.project + '-' + name + '-1']))[0]
            network = info['NetworkSettings']['Networks'][self.project + '_default']
            self.metadata['containers'][name] = {'id': info['Id'], 'ip': network['IPAddress'], 'image': info['Image']}
        containers = self.metadata['containers']
        for name in ('carts', 'user', 'payment', 'shipping'):
            folder = self.out / 'wire' / name
            folder.mkdir(parents=True)
            folder.chmod(0o777)
            observer = 'tf2-capture-' + secrets.token_hex(5)
            command(['docker', 'run', '-d', '--name', observer, '--network', 'container:' + containers[name]['id'],
                     '--cap-drop', 'ALL', '--cap-add', 'NET_RAW', '--read-only',
                     '-v', str(HERE / 'capture_http_peer.py') + ':/capture.py:ro', '-v', str(folder) + ':/output:rw',
                     IMAGE, 'python', '/capture.py', '--orders-ip', containers['orders']['ip'],
                     '--peer-ip', containers[name]['ip'], '--out', '/output'])
            self.observers.append((observer, folder))
        deadline = time.monotonic() + 15
        while not all((folder / 'ready.json').exists() for _, folder in self.observers):
            if time.monotonic() > deadline:
                raise RuntimeError('Independent wire observer startup timed out')
            time.sleep(.1)

    def finish(self):
        for observer, folder in self.observers:
            try:
                command(['docker', 'stop', '--time', '5', observer])
                (folder / 'observer.log').write_text(command(['docker', 'logs', observer], merge=True))
                pcap = folder / 'http.pcap'
                if pcap.exists():
                    decoded = command(['tshark', '-2', '-r', str(pcap), '-Y', 'http', '-T', 'json', '--no-duplicate-keys'])
                    (folder / 'http.json').write_text(decoded)
            except Exception as exc:
                self.errors.append(str(exc))
            finally:
                try:
                    command(['docker', 'rm', observer])
                except Exception as exc:
                    self.errors.append(str(exc))
        self.metadata['observers'] = [name for name, _ in self.observers]
        (self.out / 'capture-metadata.json').write_text(json.dumps(self.metadata, indent=2) + '\n')
