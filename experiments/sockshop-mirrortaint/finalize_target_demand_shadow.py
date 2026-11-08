"""Verify immutable inputs/core and archive this analysis, including full inputs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from analyze_target_demand_shadow import save, sha


def run(home, backup):
    root = Path(__file__).resolve().parents[2]
    exp = Path(__file__).resolve().parent
    freeze = root / 'artifacts/pruning-contribution-audit-20261106/final-candidate/historical/algorithm-freeze.json'
    frozen = json.loads(freeze.read_text())
    changed = [name for name, digest in frozen['sources'].items() if sha(Path(name)) != digest]
    assert not changed, changed
    protocol = json.loads((home / 'protocol-before-analysis.json').read_text())
    inputs = home / 'inputs'; inputs.mkdir(exist_ok=False)
    portable = json.loads(json.dumps(protocol))
    for task, spec in protocol['tasks'].items():
        folder = inputs / task; folder.mkdir()
        for key in ('capture', 'plan'):
            source = Path(spec[key]); assert sha(source) == spec[key + '_sha256']
            destination = folder / ('events.jsonl' if key == 'capture' else 'plan.json')
            shutil.copy2(source, destination)
            assert sha(destination) == spec[key + '_sha256']
            portable['tasks'][task][key] = str(destination)
    save(home / 'portable-protocol.json', portable)
    with (home / 'controls.log').open('w') as log:
        subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(exp),
                        '-p', 'test_target_demand_shadow.py', '-v'], stdout=log,
                       stderr=subprocess.STDOUT, check=True, cwd=root)
    subprocess.run([sys.executable, str(exp / 'analyze_target_demand_shadow.py'),
                    '--protocol', str(home / 'portable-protocol.json'),
                    '--out', str(home / 'copied-input-recheck')], check=True, cwd=root)
    for name in ('summary.json', 'retained-fields.csv', 'mall.json', 'zlt-user.json', 'ruoyi-dictionary.json'):
        assert (home / 'shadow-final' / name).read_bytes() == (home / 'copied-input-recheck' / name).read_bytes(), name
    delivery = home / 'delivery'; delivery.mkdir()
    names = ['analyze_target_demand_shadow.py', 'test_target_demand_shadow.py',
             'finalize_target_demand_shadow.py', 'TARGET-DEMAND-SHADOW-20261108.md',
             'target-demand-shadow-results-20261108.json',
             'target-demand-shadow-retained-20261108.csv', 'target-demand-shadow-protocol-20261108.json']
    for name in names: shutil.copy2(exp / name, delivery / name)
    audit = {'core_unchanged_files': len(frozen['sources']), 'core_reference': protocol['reference_core'],
             'core_source_manifest_sha256': sha(freeze), 'all_three_complete_inputs_unchanged': True,
             'copied_inputs_analysis_byte_equal': True, 'controls': 10,
             'new_agent_deployments': 0, 'new_performance_measurements': 0,
             'no_new_omission_permission': True, 'no_push': True}
    save(home / 'integrity-audit.json', audit)
    manifest = {str(p.relative_to(home)): sha(p) for p in sorted(home.rglob('*')) if p.is_file()}
    save(home / 'files-manifest.json', manifest)
    backup.mkdir(parents=True, exist_ok=False)
    archive = backup / 'complete-analysis-and-inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(home, arcname=str(home.relative_to(root)))
    with gzip.open(archive, 'rb') as f:
        while f.read(1024 * 1024): pass
    digest = hashlib.sha256()
    with archive.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): digest.update(chunk)
    receipt = {'archive': str(archive.relative_to(root)), 'bytes': archive.stat().st_size,
               'sha256': digest.hexdigest(), 'gzip_CRC_passed': True,
               'regular_files': len(manifest), 'manifest_sha256': sha(home / 'files-manifest.json'),
               'complete_original_captures_and_plans_included': True,
               'no_new_business_images_used': True, 'local_backup_not_off_machine': True,
               'old_captures_and_failures_retained': True}
    save(backup / 'receipt.json', receipt)
    save(exp / 'target-demand-shadow-backup-20261108.json', receipt)
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--home', required=True, type=Path)
    p.add_argument('--backup', required=True, type=Path)
    a = p.parse_args(); run(a.home.resolve(), a.backup.resolve())
