#!/usr/bin/env python3
"""Original method instrumentation on frozen service branch bytecode."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile
import flowdist_preflight as tool
from normalize_flowdist_class_literals import run as normalize


def run(repo,static,out):
    tool.verify_repository(repo);out.mkdir(parents=True,exist_ok=False)
    work=out/'work';work.mkdir()
    for name in ('classes','lib','data'):
        shutil.copytree(static/'work'/('NormalizedBranches' if name=='classes' else name),work/name)
    for name in ('methodList.out','coveredMethods.txt','Message_PassingAPIList.txt'):
        shutil.copyfile(static/'work'/name,work/name)
    deps=out/'compile-deps'
    with ZipFile(repo/'tool/soot-trunk.jar') as archive:
        for name in archive.namelist():
            if name.endswith('.class') and not name.startswith('/'):
                path=deps/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(name))
    launcher=work/'launcher';launcher.mkdir()
    source=Path(__file__).with_name('FlowDistServiceMethodLauncher.java')
    cp=':'.join(map(str,[deps,repo/'tool/FLOWDIST.jar',repo/'tool/DUA1.jar']))
    compile=subprocess.run(['javac','--release','8','-cp',cp,'-d',str(launcher),str(source)],
        capture_output=True,text=True,timeout=30)
    (out/'compile.log').write_text(compile.stdout+compile.stderr)
    if compile.returncode:raise ValueError('Service method launcher compilation failed')
    dependencies=''.join(':/work/lib/'+p.name for p in sorted((work/'lib').glob('*.jar')))
    args=tool.static_args('OTBetterInstr','MethodInstrumented',dependencies)
    args[3]+=':/work/launcher';args[4]='FlowDistServiceMethodLauncher'
    args+=['-asm-backend','-java-version','8','-no-bodies-for-excluded']
    config=json.loads((static/'manifest.json').read_text())
    for prefix in [*config['excluded_library_body_prefixes'],'disttaint.*','profile.*']:
        args+=['-exclude',prefix]
    tool.execute(repo,out,'service-methods',args,timeout=120)
    normalize(work/'MethodInstrumented',work/'NormalizedBranches')
    # Branch probes still use the first pass IDs. The second pass mapper has
    # added monitor calls, so it must never replace the semantic branch map.
    for name in ('stmtids.out','entitystmt.out.branch'):
        path=work/'NormalizedBranches'/name
        if path.exists():path.rename(path.with_name('method-pass-'+name))
        shutil.copyfile(static/'work/NormalizedBranches'/name,path)
    config.update(author_method_instrumentation=True,method_instrumenter='original OTBetterInstr',
        terminate_on_main_return=True,original_shutdown_monitor_preserved=True,
        method_launcher_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        source_static_artifact=str(static),accuracy_eligible=False,performance_eligible=False)
    tool.save(out/'manifest.json',config)
    shutil.copyfile(static/'service-branches-stage.json',out/'service-branches-stage.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('repo','static','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();run(a.repo.resolve(),a.static.resolve(),a.out.resolve())
