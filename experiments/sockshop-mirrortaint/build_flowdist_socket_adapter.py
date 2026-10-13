#!/usr/bin/env python3
"""Build a disclosed clock-wiring fix; do not modify the FlowDist engine JAR.

OTBetterInstr records events with OTMonitor, but its original socket wrappers
use dtMonitor's separate clock and first-receive map. Replace only that monitor
reference in the two author socket classes. The optional robust variant also
repairs the InputStream contract while retaining the author wire header. The
graph logic and original monitor remain unchanged in both variants.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

from flowdist_preflight import verify_repository


def build(repo, out, robust=False):
    verify_repository(repo)
    out.mkdir(parents=True, exist_ok=False)
    sources=[]; changes={}
    for name in ('dtSocketInputStream','dtSocketOutputStream'):
        original=repo/'code/src/disttaint'/(name+'.java')
        before=original.read_text()
        after,count=re.subn(r'\bdtMonitor\b','OTMonitor',before)
        if count<2:
            raise ValueError('Expected author monitor references absent')
        if robust:after=(Path(__file__).parent/'flowdist'/(name+'.java')).read_text()
        target=out/(name+'.java');target.write_text(after);sources.append(target)
        (out/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(original),tofile=str(target))))
        changes[name]={'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
                       'adapted_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'replacements':count}
    classes=out/'classes';classes.mkdir()
    command=['javac','--release','8','-cp',str(repo/'tool/FLOWDIST.jar'),'-d',str(classes),*map(str,sources)]
    p=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (out/'compile.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise ValueError('Socket adapter compilation failed')
    jar=out/'flowdist-socket-adapter.jar'
    with ZipFile(jar,'w',ZIP_DEFLATED) as z:
        for file in sorted(classes.rglob('*.class')):z.write(file,str(file.relative_to(classes)))
    manifest={'kind':'flowdist-socket-clock-wiring-adapter','changes':changes,
              'compile_command':command,'jar_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),
              'engine_jar_modified':False,'framing_modified':robust,'wire_format_modified':False,
              'variant':'clock-and-stream-contract' if robust else 'clock-wiring-only',
              'robust_variant_limits':{'token_mode_required':True,'maximum_frame_bytes':64*1024*1024,
                                       'maximum_sender_bytes':4096} if robust else None,
              'graph_algorithm_modified':False,
              'accuracy_eligible':False,'performance_eligible':False}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(jar)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--robust-framing',action='store_true',help='Also fix partial header reads, frame boundaries, single bytes and per-stream accounting')
    a=p.parse_args();build(a.repo.resolve(),a.out.resolve(),a.robust_framing)
