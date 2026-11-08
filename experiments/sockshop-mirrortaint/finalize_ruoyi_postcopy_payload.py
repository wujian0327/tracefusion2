"""Archive the narrow analysis and full immutable input; never deploy or push."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from analyze_target_demand_shadow import sha, save


def run(home, backup):
    exp = Path(__file__).resolve().parent; root = exp.parents[1]
    protocol = json.loads((home/'protocol.json').read_text()); spec = protocol['input']
    frozen_path = root/'artifacts/pruning-contribution-audit-20261106/final-candidate/historical/algorithm-freeze.json'
    frozen = json.loads(frozen_path.read_text())
    assert not [p for p,d in frozen['sources'].items() if sha(Path(p)) != d]
    assert not Path(spec['capture']+'.invalid').exists()
    inputs = home/'inputs'; inputs.mkdir()
    for kind, name in [('capture', 'events.jsonl'), ('plan', 'plan.json')]:
        p = Path(spec[kind]); assert sha(p) == spec[kind+'_sha256']
        shutil.copy2(p, inputs/name); assert sha(inputs/name) == spec[kind+'_sha256']
        protocol['input'][kind] = str(inputs/name)
    save(home/'portable-protocol.json', protocol)
    subprocess.run([sys.executable, str(exp/'analyze_ruoyi_postcopy_payload.py'),
                    '--protocol', str(home/'portable-protocol.json'), '--out', str(home/'copied-input-recheck')], check=True)
    for name in ['summary.json', 'point-associations.json', 'byte-estimates.json', 'candidate-inventory.json', 'snapshot-estimates.csv']:
        assert (home/'analysis-final'/name).read_bytes() == (home/'copied-input-recheck'/name).read_bytes(), name
    for pattern in ['test_ruoyi_postcopy_payload.py', 'test_target_demand_shadow.py']:
        with (home/(pattern+'.log')).open('w') as log:
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(exp), '-p', pattern, '-v'],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
    audit = {'reference':'bcdf059', 'core_unchanged_files': len(frozen['sources']),
             'all_original_input_hashes_unchanged': True, 'copied_input_outputs_byte_equal': True,
             'analysis_controls': 19, 'new_agent_deployments': 0, 'new_timing': False,
             'hypothetical_rows_written_as_capture': False, 'permission_implementation': False}
    save(home/'integrity-audit.json', audit)
    delivery = home/'delivery'; delivery.mkdir()
    for name in ['analyze_ruoyi_postcopy_payload.py', 'test_ruoyi_postcopy_payload.py',
                 'finalize_ruoyi_postcopy_payload.py', 'RUOYI-POSTCOPY-PAYLOAD-20261108.md',
                 'ruoyi-postcopy-payload-results-20261108.json', 'ruoyi-postcopy-payload-estimates-20261108.csv',
                 'ruoyi-postcopy-payload-protocol-20261108.json']:
        shutil.copy2(exp/name, delivery/name)
    manifest = {str(p.relative_to(home)):sha(p) for p in sorted(home.rglob('*')) if p.is_file()}
    save(home/'files-manifest.json', manifest)
    backup.mkdir(parents=True, exist_ok=False); archive = backup/'complete-analysis-and-inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar: tar.add(home, arcname=str(home.relative_to(root)))
    with gzip.open(archive,'rb') as f:
        while f.read(1048576): pass
    digest = hashlib.sha256()
    with archive.open('rb') as f:
        for chunk in iter(lambda:f.read(1048576), b''): digest.update(chunk)
    receipt = {'archive':str(archive.relative_to(root)), 'bytes':archive.stat().st_size,
               'sha256':digest.hexdigest(), 'gzip_CRC_passed':True, 'regular_files':len(manifest),
               'manifest_sha256':sha(home/'files-manifest.json'), 'full_original_capture_and_plan_included':True,
               'old_records_unchanged':True, 'no_new_images_used':True, 'local_not_off_machine':True}
    save(backup/'receipt.json',receipt); save(exp/'ruoyi-postcopy-payload-backup-20261108.json',receipt)
    print(json.dumps(audit))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--backup',required=True,type=Path)
    a=p.parse_args();run(a.home.resolve(),a.backup.resolve())
