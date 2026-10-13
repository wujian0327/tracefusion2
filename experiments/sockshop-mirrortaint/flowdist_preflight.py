#!/usr/bin/env python3
"""Run pinned, unchanged FlowDist tools in Java 8 with bounded resources.

This checks compatibility, not Sock Shop accuracy. Author example source and tool
JARs stay unchanged. Classpath layout, resource limits and process lifetime differ
from the author's hardcoded shell scripts and are recorded explicitly.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid
from zipfile import ZipFile

COMMIT = '9a683606aa42289e045cdbfa9391b55e79a3ac05'
IMAGE = 'weaveworksdemos/orders@sha256:b622e40e83433baf6374f15e076b53893f79958640fc6667dff597622eff03b9'
TOOL_HASHES = {'FLOWDIST.jar':'809cadf28550959291c3c21c1ce3130a6ca84af3bb649a545def0d61905c82d5',
               'soot-trunk.jar':'36afc1eb585178b3792599712c6608672a0568f869811f1ef40007d2d7982de7'}
CP = '/flowdist/tool/*:/work/classes'
SOOT_CP = '/usr/lib/jvm/java-1.8-openjdk/jre/lib/rt.jar:/work/classes:/flowdist/tool/FLOWDIST.jar:/flowdist/tool/soot-trunk.jar'
PILOT_QUERY = '<org.apache.thrift.transport.TIOStreamTransport: int read(byte[],int,int)>; <CalculatorClient: void main(java.lang.String[])>'
CROSS_QUERY = '<CalculatorHandler: int add(int,int)>; <CalculatorClient: void main(java.lang.String[])>'


def save(file, data):
    file.write_text(json.dumps(data,indent=2)+'\n')


def verify_repository(repo):
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    if head!=COMMIT:
        raise ValueError('Unexpected FlowDist revision')
    subprocess.run(['git','diff','--exit-code','HEAD','--'],cwd=repo,check=True,stdout=subprocess.DEVNULL)
    for name,expected in TOOL_HASHES.items():
        if hashlib.sha256((repo/'tool'/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Unexpected FlowDist dependency: '+name)


def prepare(repo, out):
    verify_repository(repo)
    out.mkdir(parents=True,exist_ok=False)
    work=out/'work';(work/'classes').mkdir(parents=True);(work/'data').mkdir()
    # Modern javac rejects an invalid '/.' ZIP entry in the author's Soot JAR.
    # Extract only the bundled SLF4J compile dependency; never rewrite the tool.
    deps=out/'compile-deps'
    with ZipFile(repo/'tool/soot-trunk.jar') as z:
        for name in z.namelist():
            if name.startswith('org/slf4j/') and name.endswith('.class'):
                f=deps/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(z.read(name))
    thrift=repo/'data/Thrift/libthrift-0.11.0.jar'
    sources=sorted((repo/'data/Thrift/java').glob('*.java'))
    cmd=['javac','--release','8','-cp',str(thrift)+':'+str(deps),'-d',str(work/'classes'),*map(str,sources)]
    p=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=60)
    (out/'compile.log').write_text(p.stdout+p.stderr)
    if p.returncode:
        raise ValueError('Thrift compilation failed')
    # Author scripts process the Thrift implementation as well as the example.
    with ZipFile(thrift) as z:
        for name in z.namelist():
            if name.endswith('.class'):
                f=work/'classes'/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(z.read(name))
    for name in ('Sources.txt','Sinks.txt'):
        shutil.copyfile(repo/'data'/name,work/'data'/name)
    shutil.copyfile(repo/'Message_PassingAPIList.txt',work/'Message_PassingAPIList.txt')
    save(out/'manifest.json',{'upstream_url':'https://bitbucket.org/wsucailab/flowdist.git',
        'upstream_commit':COMMIT,'image':IMAGE,'tool_sha256':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((repo/'tool').glob('*.jar'))},
        'example_source_sha256':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'compile_command':cmd,'source_modified':False,'engine_modified':False,
        'accuracy_eligible':False,'performance_eligible':False})


def docker(repo, out, entry='java'):
    return ['docker','run','--rm','--network','none','--memory','4g','--user',f'{os.getuid()}:{os.getgid()}',
            '--entrypoint',entry,'-v',str(repo)+':/flowdist:ro','-v',str(out/'work')+':/work:rw',
            '-w','/work',IMAGE]


def prepare_shipping(repo,out,jar):
    verify_repository(repo)
    out.mkdir(parents=True,exist_ok=False)
    work=out/'work';(work/'classes').mkdir(parents=True);(work/'lib').mkdir();(work/'data').mkdir()
    hashes={}
    with ZipFile(jar) as z:
        for name in z.namelist():
            if name.startswith('BOOT-INF/classes/') and name.endswith('.class'):
                target=work/'classes'/name[len('BOOT-INF/classes/'):]
            elif name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):
                target=work/'lib'/Path(name).name
            else:
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            content=z.read(name);target.write_bytes(content)
            hashes[name]=hashlib.sha256(content).hexdigest()
    for name in ('Sources.txt','Sinks.txt'):
        shutil.copyfile(repo/'data'/name,work/'data'/name)
    shutil.copyfile(repo/'Message_PassingAPIList.txt',work/'Message_PassingAPIList.txt')
    save(out/'manifest.json',{'kind':'shipping-original-bytecode-compatibility',
        'upstream_commit':COMMIT,'image':IMAGE,'shipping_jar':str(jar),
        'shipping_jar_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),
        'extracted_sha256':hashes,'tool_sha256':TOOL_HASHES,
        'source_modified':False,'engine_modified':False,
        'accuracy_eligible':False,'performance_eligible':False})


def execute(repo,out,name,arguments,entry='java',timeout=240):
    verify_repository(repo)
    log=out/(name+'.log');meta=out/(name+'-stage.json')
    if log.exists() or meta.exists():
        raise ValueError('Refusing to replace stage evidence: '+name)
    container_name='flowdist-preflight-'+uuid.uuid4().hex[:12]
    command=docker(repo,out,entry)
    command[2:2]=['--name',container_name]
    command+=arguments
    start=time.perf_counter_ns()
    timed_out=False
    with log.open('w') as f:
        try:
            p=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,text=True,timeout=timeout)
            exit_code=p.returncode
        except subprocess.TimeoutExpired:
            timed_out=True
            exit_code=None
            subprocess.run(['docker','rm','-f',container_name],stdout=f,stderr=subprocess.STDOUT,timeout=30)
    elapsed=(time.perf_counter_ns()-start)/1e6
    text=log.read_text(errors='replace')
    errors=[line for line in text.splitlines() if re.match(r'^(Exception in thread|Caused by:|java\.[\w.$]+(?:Exception|Error):|Error:|ERROR\b|Couldn.t)',line)]
    result={'command':command,'exit_code':exit_code,'elapsed_ms':elapsed,'errors':errors,
            'timeout_seconds':timeout,'timed_out':timed_out,
            'status':'timeout' if timed_out else ('failed' if exit_code or errors else 'process-completed-output-requires-validation'),
            'accuracy_eligible':False,'performance_eligible':False}
    save(meta,result)
    if timed_out or exit_code or errors:
        raise ValueError('FlowDist stage failed; inspect '+str(log))
    return result


def static_args(class_name, directory, dependencies=''):
    return ['-Xmx3g','-ea','-cp',CP+dependencies,'disttaint.'+class_name,'-w','-cp',SOOT_CP+dependencies,
            '-p','cg','verbose:false,implicit-entry:false','-p','cg.spark','verbose:false,on-fly-cg:true,rta:false',
            '-f','c','-d','/work/'+directory,'-brinstr:off','-duainstr:off',
            '-process-dir','/work/classes','-allowphantom']


def stage(repo,out,name):
    work=out/'work'
    if (out/(name+'.log')).exists() or (out/(name+'-stage.json')).exists():
        raise ValueError('Refusing to replace stage evidence: '+name)
    manifest=json.loads((out/'manifest.json').read_text())
    dependencies=''.join(':/work/lib/'+f.name for f in sorted((work/'lib').glob('*.jar')))
    if name=='source-sink':
        arguments=['-Xmx2g','-ea','-cp',CP+dependencies,'disttaint.OTBetterSourceSink','/work/classes']
    elif name in ('scope','instrument','branches','refine'):
        klass,directory={'scope':('OTBetterMethods','OTMethods'),'instrument':('OTBetterInstr','OTInstrumented'),
                         'branches':('OTBranchInst','OTBranches'),'refine':('OT3Inst','OT3Instrumented')}[name]
        (work/directory).mkdir(exist_ok=True)
        arguments=static_args(klass,directory,dependencies)
        if name=='instrument' and manifest.get('socket_enabled'):
            arguments+=['-socket']
        if name in ('branches','refine'):
            arguments+=['-slicectxinsens','-wrapTryCatch','-intraCD','-interCD','-exInterCD','-dumpFunctionList','-serializeVTG']
        if name=='refine':
            mapping=work/'OTBranches/entitystmt.out.branch'
            if not mapping.is_file() or not mapping.stat().st_size:
                raise ValueError('Validated branch mapping required before refinement')
            shutil.copyfile(mapping,work/'entitystmt.out.branch')
    elif name in ('method-analysis','cross-method-analysis'):
        query=PILOT_QUERY if name=='method-analysis' else CROSS_QUERY
        if name=='method-analysis' and PILOT_QUERY not in (work/'sourceSinkMethodPairDiffClass.txt').read_text().splitlines():
            raise ValueError('Pilot query absent from actual source/sink configuration')
        if name=='cross-method-analysis':
            for f in ('methodList.out','methodsInPair.out'):
                if (work/f).exists():shutil.copyfile(work/f,out/(f+'.default-query'))
        (work/'traces/test1').mkdir(parents=True,exist_ok=True)
        for f in (work/'runtime').glob('*/test1/*.em'):
            shutil.copyfile(f,work/'traces/test1'/f.name)
        arguments=['-Xmx1g','-ea','-cp',CP,'disttaint.OTAnalysisAll',query,'/work/traces','/work/OTInstrumented','','-prec']
    else:
        raise ValueError('Unknown stage')
    result=execute(repo,out,name,arguments)
    expected={'source-sink':['source_1.txt','sink_1.txt','sourceSinkMethodPairDiffClass.txt'],
              'scope':['coveredMethods.txt'],'instrument':['OTInstrumented/CalculatorClient.class','OTInstrumented/CalculatorServer.class'],
              'method-analysis':['methodList.out','methodsInPair.out'],
              'cross-method-analysis':['methodList.out','methodsInPair.out'],
              'branches':['OTBranches/entitystmt.out.branch'],'refine':['OT3Instrumented/staticVtg.dat']}[name]
    missing=[n for n in expected if not (work/n).is_file() or (work/n).stat().st_size==0]
    result.update(expected_outputs=expected,missing_outputs=missing,status='failed' if missing else 'output-present')
    if name=='source-sink':
        for label,file in (('source_method_count','coveredSourceMethods.txt'),('sink_method_count','coveredSinkMethods.txt')):
            result[label]=len((work/file).read_text().splitlines()) if (work/file).exists() else 0
    if name=='instrument' and manifest.get('socket_enabled'):
        content=(work/'OTInstrumented/org/apache/thrift/transport/TSocket.class').read_bytes()
        result['socket_wrappers_present']=all(n in content for n in (b'disttaint/dtSocketInputStream',b'disttaint/dtSocketOutputStream'))
        if not result['socket_wrappers_present']:result['status']='failed'
    if name in ('method-analysis','cross-method-analysis'):
        raw=(out/(name+'.log')).read_text()
        result['query']=query
        result['query_kind']='configured-source-sink' if name=='method-analysis' else 'manual-server-to-client-method-compatibility'
        length=re.search(r'\[The method path length\]: (\d+)',raw)
        result['method_path_length']=int(length.group(1)) if length else None
        if not length or result['method_path_length']<2:result['status']='failed'
    save(out/(name+'-stage.json'),result)
    if result['status']=='failed':raise ValueError('Missing or invalid actual stage outputs: '+str(missing))
    return result


def runtime(repo,out):
    script=out/'work/run-example.sh'
    script.write_text('''#!/bin/sh
set -eu
mkdir -p /work/runtime/server/test1 /work/runtime/client/test1
cp_value="/work/OTInstrumented:/flowdist/tool/*"
cd /work/runtime/server
java -Xmx256m -ea -cp "$cp_value" CalculatorServer > server.log 2>&1 &
server_pid=$!
client_pid=""
cleanup() {
 if [ -n "$client_pid" ]; then kill -TERM "$client_pid" 2>/dev/null || true; wait "$client_pid" 2>/dev/null || true; fi
 kill -TERM "$server_pid" 2>/dev/null || true
 wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
sleep 2
cd /work/runtime/client
java -Xmx256m -ea -cp "$cp_value" CalculatorClient > client.log 2>&1 &
client_pid=$!
step=0
while [ "$step" -lt 40 ]; do
 if grep -q 'client.divi(' client.log; then exit 0; fi
 if ! kill -0 "$server_pid" 2>/dev/null || ! kill -0 "$client_pid" 2>/dev/null; then exit 2; fi
 sleep 0.5
 step=$((step+1))
done
exit 3
''')
    result=execute(repo,out,'runtime',['/work/run-example.sh'],entry='sh',timeout=45)
    raw=(out/'work/runtime/client/client.log').read_text()
    matches=re.findall(r'client\.(add|minus|multi|divi)\((\d+),(\d+)\)=(-?\d+)',raw)
    checked=[]
    for op,a,b,value in matches:
        a,b,value=int(a),int(b),int(value)
        expected={'add':lambda:a+b,'minus':lambda:a-b,'multi':lambda:a*b,'divi':lambda:a//b}[op]()
        checked.append({'op':op,'a':a,'b':b,'value':value,'passed':value==expected})
    traces=list((out/'work/runtime').glob('*/test1/*.em'))
    passed={r['op'] for r in checked}=={'add','minus','multi','divi'} and all(r['passed'] for r in checked) and len(traces)==2
    result.update(status='example-business-and-traces-passed' if passed else 'failed',operations=checked,
                  traces={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in traces})
    save(out/'runtime-stage.json',result)
    if not passed:raise ValueError('Example business or trace coverage failed')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','prepare-shipping','source-sink','scope','instrument','runtime','method-analysis','cross-method-analysis','branches','refine'])
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--shipping-jar',type=Path)
    p.add_argument('--socket',action='store_true',help='Record and enable the optional socket instrumentation in a new Thrift preparation')
    args=p.parse_args();repo=args.repo.resolve();out=args.out.resolve()
    if args.socket and args.action!='prepare':p.error('--socket is only accepted with prepare')
    if args.action=='prepare':
        prepare(repo,out)
        manifest=json.loads((out/'manifest.json').read_text());manifest['socket_enabled']=args.socket
        save(out/'manifest.json',manifest)
        print('Prepared unchanged Thrift example')
    elif args.action=='prepare-shipping':
        if not args.shipping_jar:p.error('--shipping-jar required')
        prepare_shipping(repo,out,args.shipping_jar.resolve());print('Prepared original Shipping classes and dependencies')
    else:print(json.dumps(runtime(repo,out) if args.action=='runtime' else stage(repo,out,args.action),indent=2))
