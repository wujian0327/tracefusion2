"""Freeze delivery metadata, verify reuse and archive this round without push."""
import argparse
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from run_planned_service import ROOT, HERE, load, save, sha
from run_paper_frozen_reuse import verify


def crc(path):
    with gzip.open(path,'rb')as f:
        while f.read(1048576):pass


def digest(path):
    h=hashlib.sha256()
    with path.open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def run(home,backup):
    verify(home)
    assert load(home/'evidence-checks-final/summary.json')['passed']
    actual=[]
    for root in (home,home/'calibration-C2',home/'post-metadata-C2'):
        verify(root);assert load(root/'matrix-progress.json')['complete']
        for p in(root/'runs').glob('*/*/result.json'):
            if p.parent.is_symlink():continue
            r=load(p);assert r['state']=='captured'and r['cleanup_returncode']==0 and len(r['cases'])==6
            actual.append({'path':str(p),'sha256':sha(p),'query':r['query'],'mode':r['mode']})
    assert len(actual)==12
    # Actual model is recorded in the sealed input. Only library inventory was
    # imported from the frozen fixture; all business class facts are unchanged.
    complete=load(Path(load(home/'calibration-C2/task-seal-before-tools.json')['model']))
    original=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/metadata/ruoyi/model.json')
    assert {k:v for k,v in complete.items()if k!='library_inventory'}=={k:v for k,v in original.items()if k!='library_inventory'}
    for mode in ('original','mirrortaint'):
        receipt=load(home/'post-metadata-C2'/('reuse-'+mode+'.json'));source=Path(receipt['source'])
        assert all(sha(source/p)==d for p,d in receipt['files'].items())
    # Rebuild tables in a fresh directory and compare every generated cell/file.
    subprocess.run([sys.executable,str(HERE/'build_paper_closeout_tables.py'),'--home',str(home),
                    '--out',str(home/'tables-recheck'),'--include-new'],check=True)
    for p in(home/'tables-final-03').iterdir():
        assert p.read_bytes()==(home/'tables-recheck'/p.name).read_bytes(),p.name
    audit={'core':'bcdf059','core_files_unchanged':139,'new_logical_queries':2,'new_deployments':12,'requests':72,
           'fixed_query_selection_unchanged':True,'A0_C1_C2_calibration_retained':True,
           'business_metadata_same_original_class_facts':True,'table_rebuild_byte_equal':True,
           'compatible_original_MT_files_unchanged':True,'new_framework_contracts':0,'new_performance':False,
           'actual_runs':actual,'no_push':True}
    save(home/'delivery-integrity.json',audit)
    backup.mkdir(parents=True,exist_ok=False)
    # Reuse verified image/JDK archives; no new images were built or pulled.
    previous=load(HERE/'pruning-contribution-backup-20261106.json')
    archives=[r for r in previous['reused_verified_archives']if r['path'].endswith(('actual-images.tar.gz','jdk8-runtime.tar.gz'))]
    assert len(archives)==2
    for r in archives:
        p=ROOT/r['path'];assert digest(p)==r['sha256'];crc(p)
    mounted=home/'mounted-inputs';mounted.mkdir();inputs={}
    for root in (home,home/'calibration-C2',home/'post-metadata-C2'):
        for name,d in load(root/'task-seal-before-tools.json')['artifacts'].items():
            assert sha(Path(name))==d
            if name in inputs:continue
            target=mounted/str(len(inputs));shutil.copy2(name,target);inputs[name]={'file':str(target.relative_to(home)),'sha256':d}
    for name,d in load(home/'tables-final-03/source-hashes.json').items():
        path=ROOT/name;assert sha(path)==d
        if str(path)not in inputs:
            target=mounted/str(len(inputs));shutil.copy2(path,target);inputs[str(path)]={'file':str(target.relative_to(home)),'sha256':d}
    save(home/'mounted-inputs-manifest.json',inputs)
    delivery=home/'delivery';delivery.mkdir()
    names=['run_paper_frozen_reuse.py','score_paper_frozen_reuse.py','build_paper_closeout_tables.py',
           'check_paper_closeout_evidence.py','write_paper_closeout_report.py','finalize_paper_closeout.py',
           'PAPER-EXPERIMENT-CLOSEOUT-20261109.md','paper-experiment-tables-20261109.json',
           'paper-engineering-reference-20261109.json',
           'paper-closeout-sources-20261109.json','paper-frozen-reuse-protocol-20261109.json',
           'paper-frozen-reuse-C1-protocol-20261109.json','paper-frozen-reuse-list-C2-protocol-20261109.json',
           'paper-frozen-reuse-detail-C2-protocol-20261109.json',
           'paper-frozen-reuse-results-20261109.json','paper-frozen-reuse-instances-20261109.csv']
    for stem in ('capability','mt-paired','pruning-ablation'):
        for ext in ('csv','tex'):names.append('paper-'+stem+'-20261109.'+ext)
    for name in names:shutil.copy2(HERE/name,delivery/name)
    manifest={str(p.relative_to(home)):sha(p)for p in sorted(home.rglob('*'))if p.is_file()and not p.is_symlink()}
    save(home/'files-manifest.json',manifest)
    archive=backup/'complete-round.tar.gz'
    with tarfile.open(archive,'w:gz',dereference=False)as tar:tar.add(home,arcname=str(home.relative_to(ROOT)))
    crc(archive)
    receipt={'archive':str(archive.relative_to(ROOT)),'bytes':archive.stat().st_size,'sha256':digest(archive),
             'gzip_CRC_passed':True,'regular_files':len(manifest),'manifest_sha256':sha(home/'files-manifest.json'),
             'reused_verified_runtime_archives':archives,'symlinks_not_dereferenced':True,
             'all_round_raw_failures_and_inputs_retained':True,'local_backup_not_off_machine':True}
    save(backup/'receipt.json',receipt);save(HERE/'paper-closeout-backup-20261109.json',receipt)
    print({'complete':True,'new_queries':2,'new_deployments':12,'core_unchanged':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',required=True,type=Path);p.add_argument('--backup',required=True,type=Path)
    a=p.parse_args();run(a.home.resolve(),a.backup.resolve())
