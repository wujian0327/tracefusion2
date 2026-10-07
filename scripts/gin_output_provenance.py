#!/usr/bin/env python3
"""Run full/partial/no overwrite with full, boundary, and automatic policies."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import traceback
import zipfile
from gin_choice_provenance import run,KILL_VARIANTS
from hybrid_provenance import ROOT,save
from hybrid_model import require


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('build','run'));parser.add_argument('--output',type=Path)
    args=parser.parse_args();build_only=args.command=='build'
    out=(args.output or ROOT/'artifacts'/('gin-output-provenance-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False);passed=False;reports={}
    try:
        for variant in KILL_VARIANTS:
            print('Checking '+variant,flush=True);trial=out/variant;trial.mkdir()
            require(run(trial,build_only,variant,archive_output=False)==0,'Failed '+variant+'; inspect its runner-error.txt')
            if not build_only:reports[variant]=json.loads((trial/'comparison.json').read_text())
        passed=True;save(out/'evaluation.json',dict(all_passed=True,build_only=build_only,variants=reports))
    except Exception:
        error=traceback.format_exc();(out/'runner-error.txt').write_text(error);print(error,flush=True)
    finally:
        save(out/'run-status.json',dict(completed=passed,build_only=build_only))
        if not build_only:
            archive=out.with_suffix('.zip')
            # Keep one copy of identical binaries, recording exact SHA aliases.
            # Analysis tools can resolve the logical path via this manifest.
            import hashlib
            aliases={};known={}
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for p in sorted(out.rglob('*')):
                    if not p.is_file():continue
                    rel=p.relative_to(out)
                    if p.name=='gin-byte-target' and 'build' not in rel.parts:continue
                    name=str(p.relative_to(out.parent))
                    if p.name in ('gin-byte-target','otel-client'):
                        digest=hashlib.sha256(p.read_bytes()).hexdigest()
                        if digest in known:
                            aliases[name]=dict(path=known[digest],sha256=digest);continue
                        known[digest]=name
                    z.write(p,name)
                z.writestr(out.name+'/binary-aliases.json',json.dumps(aliases,indent=2)+'\n')
            if os.geteuid()==0 and os.environ.get('SUDO_UID','').isdigit():
                os.chown(archive,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
            print('Return this archive: '+str(archive),flush=True)
    return int(not passed)


if __name__=='__main__':raise SystemExit(main())
