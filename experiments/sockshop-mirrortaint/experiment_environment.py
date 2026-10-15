"""Portable compiler options and migration-manifest image selection."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def java8_target():
    result = subprocess.run(['javac', '-version'], capture_output=True, text=True, check=True)
    version = (result.stdout + result.stderr).strip()
    return version, (['-source', '8', '-target', '8'] if version.startswith('javac 1.8.')
                     else ['--release', '8'])


def pin_images(spec, application, manifest=None):
    manifest = manifest or ROOT / 'artifacts/desktop-inputs/images-lock.json'
    lock = json.loads(manifest.read_text())
    services = {}
    for reference, record in lock.items():
        if '@sha256:' not in reference:
            raise ValueError('Image reference is not digest locked: ' + reference)
        for service in record['services']:
            if service in services:
                raise ValueError('Duplicate image service binding: ' + service)
            services[service] = reference
    for name, config in spec['services'].items():
        config['image'] = services[application + '/' + name]
        # Host search domains can send old Go's single-label lookups to public
        # DNS before Docker's service name. Keep discovery within this network.
        config['dns_search'] = ['.']
    return spec
