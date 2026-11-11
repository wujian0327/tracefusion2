"""Read-only delivery audit in a fresh output directory; never re-times."""
import argparse, subprocess
from pathlib import Path
from run_planned_service import load, save, sha
from seal_galette_static_baselines import H
from summarize_galette_static_baselines import run as summarize
from compare_tf_baseline_roots import run as compare


def run(home, out):
    out.mkdir(parents=True, exist_ok=False)
    protocol = load(home/'protocol-before-calibration.json')
    for group in ('core_sources', 'public_contracts', 'files'):
        for p, digest in protocol[group].items():
            assert sha(Path(p)) == digest, p
    for p, fact in load(home/'tool-build-receipt.json')['files'].items():
        assert sha(Path(p)) == fact['sha256'], p
    for p, digest in load(home/'runtime-correction-before-fixed-calibration.json')['restored_files'].items():
        assert sha(Path(p)) == digest, p
    assert not subprocess.check_output(['git', '-C', str(home/'galette-original'), 'status', '--porcelain'], text=True)
    assert 'GALETTE_RUNTIME_API_PROBE_OK' in (home/'runtime-probe-02/run.log').read_text()
    assert 'CALLER_SENSITIVE_OK' in (home/'caller-sensitive-01/original.log').read_text()
    assert 'VerifyError' in (home/'caller-sensitive-01/galette.log').read_text()
    gate = load(home/'formal-gate.json')
    assert not gate['passed'] and gate['formal_deployments'] == 0
    assert load(home/'galette-boot-high-02/result.json')['cleanup_returncode'] == 0
    summarize(home, out/'summary'); compare(home, out/'summary', out/'paired-roots')
    result = load(out/'summary/summary.json')
    for mode in ('mirrortaint', 'full', 'static', 'selective'):
        group = [r for r in result['calibration'] if r['configuration'] == mode]
        assert sum(r['correct'] for r in group) == 39
        assert not any(r['wrong'] or r['unknown'] or r['rejected_or_invalid'] for r in group)
    assert sum(r['unscored'] for r in result['calibration'] if r['configuration'] == 'galette') == 39
    assert result['User_empty_page_control']['original_result']['business_passed'] == 0
    assert load(home/'static-body-controls-504/checks.json')['positive_and_required_unknown_preserved']
    for name in ('static-write-controls-504', 'static-write-fallback-controls-504'):
        checks = load(home/name/'results.json')
        assert all(len(r['checks']) == 8 and len(r['guards']) == 4 for r in checks.values())
    save(out/'audit.json', {'passed': True, 'meaning': 'Evidence bookkeeping, target correctness and stop-condition audit; NOT Galette business certification or formal cost success.',
                           'no_new_deployment_or_timing': True, 'core_manifest_paths': len(protocol['core_sources']),
                           'unchanged_contract_runtime_JSONs': sum(p.endswith('.json') for p in protocol['core_sources']),
                           'formal_gate_passed': False, 'Galette_calibration_passed': False})


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--home', type=Path, default=H); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); run(a.home.resolve(), a.out.resolve())
