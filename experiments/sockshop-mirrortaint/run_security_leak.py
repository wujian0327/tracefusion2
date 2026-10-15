#!/usr/bin/env python3
"""Freeze, run, and score a controlled two-JVM leak + inert Log4j regression.

Requires cached official Log4j artifacts and existing pinned ASM/Jackson caches.
No containers, remote JNDI endpoints, downloaded code, or production services.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from zipfile import ZipFile, ZIP_DEFLATED

from security_field_flow import infer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEPS = ROOT / 'artifacts/security-leak-deps'
LOG4J_SHA256 = {
    'log4j-api-2.14.1.jar':'8caf58db006c609949a0068110395a33067a2bad707c3da35e959c0473f9a916',
    'log4j-core-2.14.1.jar':'ade7402a70667a727635d5c4c29495f4ff96f061f12539763f6f123973b465b0',
    'log4j-api-2.17.1.jar':'b0d8a4c8ab4fb8b1888d0095822703b0e6d4793c419550203da9e69196161de4',
    'log4j-core-2.17.1.jar':'c967f223487980b9364e94a7c7f9a8a01fd3ee7c19bdbf0b0f9f8cb8511f3d41',
}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out):
    if out != DEPS:
        raise ValueError('Use --out artifacts/security-leak-deps; the build pins this cache')
    out.mkdir(parents=True,exist_ok=True);rows=[]
    for name,expected in LOG4J_SHA256.items():
        artifact,version=name.rsplit('-',1);version=version.removesuffix('.jar')
        url=f'https://repo.maven.apache.org/maven2/org/apache/logging/log4j/{artifact}/{version}/{name}'
        path=out/name
        if not path.exists():
            with urllib.request.urlopen(url,timeout=30) as response:data=response.read(4000000)
            if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Downloaded artifact digest mismatch')
            path.write_bytes(data)
        if sha(path)!=expected:raise ValueError('Cached artifact digest mismatch')
        rows.append({'file':name,'url':url,'sha256':expected})
    if not (out/'manifest.json').exists():save(out/'manifest.json',rows)


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    asm = [ROOT/'artifacts/java-collection-deps'/name for name in ('asm-9.7.1.jar','asm-tree-9.7.1.jar')]
    expected = ['8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281',
                '9929881f59eb6b840e86d54570c77b59ce721d104e6dfd7a40978991c2d3b41f']
    if [sha(p) for p in asm] != expected:
        raise ValueError('ASM dependency changed')
    jackson = [ROOT/'artifacts/flowdist-orders-static-lambda-v3-20261013/work/lib'/name
               for name in ('jackson-core-2.8.6.jar','jackson-databind-2.8.6.jar','jackson-annotations-2.8.6.jar')]
    manifest = json.loads((DEPS/'manifest.json').read_text())
    if {row['file']:row['sha256'] for row in manifest}!=LOG4J_SHA256:
        raise ValueError('Log4j manifest differs from pinned releases')
    for row in manifest:
        if sha(DEPS/row['file']) != row['sha256']:
            raise ValueError('Official Log4j artifact changed')
    log4j = [DEPS/f'log4j-{kind}-2.17.1.jar' for kind in ('api','core')]
    classes = out/'classes';classes.mkdir()
    sources = [HERE/'SecurityLeakLab.java', HERE/'SecurityObservationAgent.java']
    cmd = ['javac','--release','8','-cp',':'.join(map(str,asm+jackson+log4j)),
           '-d',str(classes),*map(str,sources)]
    result = subprocess.run(cmd,text=True,capture_output=True)
    (out/'compile.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError(result.stdout+result.stderr)
    agent = out/'security-observer.jar'
    with ZipFile(agent,'w',ZIP_DEFLATED) as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: SecurityObservationAgent\n\n')
        for p in classes.glob('SecurityObservationAgent*.class'):
            z.write(p,p.name)
        for dependency in asm:
            with ZipFile(dependency) as source:
                for name in source.namelist():
                    if name.startswith('org/objectweb/asm/') and name.endswith('.class'):
                        z.writestr(name,source.read(name))
    save(out/'manifest.json',{'sources':{str(p):sha(p) for p in sources},
                             'dependencies':{str(p):sha(p) for p in asm+jackson},
                             'log4j':manifest,'agent_sha256':sha(agent),
                             'classes_sha256':{p.name:sha(p) for p in classes.glob('*.class')},
                             'jackson_classpath':list(map(str,jackson)),
                             'java':subprocess.run(['java','-version'],capture_output=True,text=True).stderr,
                             'command':cmd})


def freeze(out):
    out.mkdir(parents=True,exist_ok=False)
    cases=[]
    def add(name,mode,secret,public,origin,**extra):
        cases.append(dict(id=name,mode=mode,secret=secret,publicValue=public,
                          expected_property=origin,expected_disclosure=origin=='secret',**extra))
    add('direct-leak','leak','SECRET_A','PUBLIC_A','secret')
    add('public-only','public','SECRET_B','PUBLIC_B','publicValue')
    add('equal-values-public','public','SAME','SAME','publicValue')
    add('equal-values-secret','leak','SAME','SAME','secret')
    add('local-overwrite','overwrite','SECRET_C','PUBLIC_C',None)
    add('field-copy','field-copy','SECRET_D','PUBLIC_D','secret')
    add('field-overwrite','field-overwrite','SECRET_E','PUBLIC_E','publicValue')
    add('read-secret-unused','read-unused','SECRET_F','PUBLIC_F','publicValue')
    add('constant-equals-secret','constant','PUBLIC','PUBLIC',None)
    add('unsupported-copy','unknown-transform','SECRET_UNKNOWN','PUBLIC_UNKNOWN','secret',expected_support=False)
    for i in range(12):
        add('concurrent-'+str(i),'leak' if i%2==0 else 'public','PARALLEL_SAME','PARALLEL_SAME',
            'secret' if i%2==0 else 'publicValue',concurrent=True,delay=(11-i)*3)
    for row in cases:
        row.setdefault('expected_support',True)
        row['expected_log']=(row[row['expected_property']] if row['expected_property'] else 'REDACTED' if row['mode']=='overwrite' else 'PUBLIC')
    payload='${jndi:tf2-local-marker}'
    cve=[dict(id='lookup-direct',mode='leak',secret=payload,publicValue='PUBLIC',expected_property='secret',lookup_capable=True),
         dict(id='lookup-field-copy',mode='field-copy',secret=payload,publicValue='PUBLIC',expected_property='secret',lookup_capable=True),
         dict(id='lookup-overwritten',mode='overwrite',secret=payload,publicValue='PUBLIC',expected_property=None,lookup_capable=False),
         dict(id='ordinary-message',mode='leak',secret='ORDINARY_MESSAGE',publicValue='PUBLIC',expected_property='secret',lookup_capable=False),
         dict(id='public-input-lookup',mode='public',secret='SECRET',publicValue=payload,expected_property='publicValue',lookup_capable=True)]
    save(out/'contract.json',{'controlled':cases,'cve':cve,
        'controlled_policy':'Record.secret is confidential; the configured file log is forbidden for raw confidential data.',
        'cve_policy':'Record.secret/publicValue are HTTP-controlled; observe whether a source-derived actual logger argument triggers native JndiLookup in the same synchronous frame.',
        'profiles':{'controlled':{'version':'2.17.1','no_lookups':False},
                    'cve-vulnerable':{'version':'2.14.1','no_lookups':False},
                    'cve-config-mitigated':{'version':'2.14.1','no_lookups':True},
                    'cve-fixed':{'version':'2.17.1','no_lookups':False}},
        'oracle':'Explicit fixture reference-copy/last-write semantics; literal JNDI expression and inert local provider; separate from inference inputs.',
        'limitations':['New controlled application; no Sock Shop vulnerability claim.',
                       'Known vulnerable library in a small harness, not an original vulnerable production application.',
                       'The local JNDI provider confirms lookup evaluation only, not LDAP access or remote code execution.',
                       'No new-vulnerability discovery claim; no competing-tool or performance measurements.']})


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def run_profile(build_dir, out, cfg, cases):
    out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((build_dir/'manifest.json').read_text())
    for file, expected in {**manifest['sources'],**manifest['dependencies']}.items():
        if sha(Path(file)) != expected:
            raise ValueError('Build input changed')
    if sha(build_dir/'security-observer.jar') != manifest['agent_sha256']:
        raise ValueError('Observer changed')
    for name,expected in manifest['classes_sha256'].items():
        if sha(build_dir/'classes'/name)!=expected:
            raise ValueError('Compiled application changed')
    ports=[free_port(),free_port()]
    while ports[1]==ports[0]:ports[1]=free_port()
    deps=[DEPS/f"log4j-{kind}-{cfg['version']}.jar" for kind in ('api','core')]
    for p in deps:
        expected=next(r['sha256'] for r in manifest['log4j'] if r['file']==p.name)
        if sha(p)!=expected:raise ValueError('Log4j runtime artifact changed')
    classpath=':'.join([str(build_dir/'classes'),*manifest['jackson_classpath'],*map(str,deps)])
    config=out/'log4j2.xml'
    config.write_text('<Configuration status="ERROR"><Appenders><File name="F" fileName="'+str(out/'application.log')+'" immediateFlush="true"><PatternLayout pattern="%X{request}|%m%n"/></File></Appenders><Loggers><Root level="info"><AppenderRef ref="F"/></Root></Loggers></Configuration>')
    processes=[];handles=[];commands=[];business=[]
    try:
        for role,port in zip(('source','target'),ports):
            role_dir=out/role;role_dir.mkdir()
            cmd=['java','-Xms32m','-Xmx256m','-javaagent:'+str(build_dir/'security-observer.jar'),
                 '-Dlab.events='+str(role_dir/'events.jsonl'),'-Dlab.callbacks='+str(out/'callbacks.jsonl'),
                 '-Dlog4j.configurationFile='+str(config),
                 '-Djava.naming.factory.initial=SecurityLeakLab$LocalContextFactory']
            if cfg['no_lookups']:cmd.append('-Dlog4j2.formatMsgNoLookups=true')
            cmd+=['-cp',classpath,'SecurityLeakLab',role,str(port),str(ports[0])]
            commands.append(cmd);handle=(role_dir/'console.log').open('w');handles.append(handle)
            processes.append(subprocess.Popen(cmd,stdout=handle,stderr=subprocess.STDOUT))
        deadline=time.monotonic()+25
        for port,process in zip(ports,processes):
            while True:
                if process.poll() is not None:raise RuntimeError('JVM startup failed: '+str(out))
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=.5) as response:
                        if response.read()==b'ok':break
                except (OSError,TimeoutError):pass
                if time.monotonic()>deadline:raise RuntimeError('JVM readiness timed out')
                time.sleep(.05)
        def call(case):
            params={k:case[k] for k in ('mode','secret','publicValue')};params.update(request=case['id'],delay=case.get('delay',0))
            url=f'http://127.0.0.1:{ports[1]}/run?'+urllib.parse.urlencode(params)
            with urllib.request.urlopen(url,timeout=20) as response:
                data=response.read();ok=response.status==200 and data==b'{"ok":true}'
            return {'id':case['id'],'business_passed':ok,'response':data.decode()}
        sequential=[c for c in cases if not c.get('concurrent')]
        concurrent=[c for c in cases if c.get('concurrent')]
        business.extend(call(c) for c in sequential)
        with ThreadPoolExecutor(max_workers=12) as pool:
            business.extend(pool.map(call,concurrent))
        if not all(c['business_passed'] for c in business):raise ValueError('Business case failed')
        save(out/'business.json',business)
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for handle in handles:handle.close()
        save(out/'deployment.json',{'commands':commands,'pids':[p.pid for p in processes],
                                   'exit_codes':[p.returncode for p in processes],'all_stopped':all(p.poll() is not None for p in processes),
                                   'ports':ports,'config':cfg,'business_completed':len(business)})


def metrics(rows):
    tp=sum(r['expected'] and r['prediction'] is True for r in rows)
    fp=sum(not r['expected'] and r['prediction'] is True for r in rows)
    fn=sum(r['expected'] and r['prediction'] is not True for r in rows)
    tn=sum(not r['expected'] and r['prediction'] is False for r in rows)
    answered=sum(r['prediction'] is not None for r in rows)
    return dict(queries=len(rows),tp=tp,fp=fp,fn_including_unknown_positive=fn,tn=tn,
                unknown=len(rows)-answered,coverage=answered/len(rows),
                precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
                f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)


def evaluate(out):
    contract=json.loads((out/'contract.json').read_text());report={'profiles':{},'limitations':contract['limitations']}
    for profile,cfg in contract['profiles'].items():
        run=out/profile;cases=contract['controlled'] if profile=='controlled' else contract['cve']
        predictions=infer(run/'source/events.jsonl',run/'target/events.jsonl');save(run/'predictions.json',predictions)
        indexed={a['request_id']:a for a in predictions['answers']}
        logs={}
        for line in (run/'application.log').read_text().splitlines():
            key,value=line.split('|',1)
            if key in logs:raise ValueError('Duplicate application log')
            logs[key]=value
        callbacks=[json.loads(line) for line in (run/'callbacks.jsonl').read_text().splitlines()] if (run/'callbacks.jsonl').exists() else []
        if set(indexed)!=set(logs) or set(indexed)!={c['id'] for c in cases}:raise ValueError('Case/log coverage mismatch')
        rows=[]
        for c in cases:
            p=indexed[c['id']];actual_origin=[v[3].rsplit('.',1)[1] for v in p['origins']]
            expected_origins=[c['expected_property']] if c['expected_property'] else []
            source_exact=actual_origin==expected_origins if p['known'] else None
            if profile=='controlled':
                expected=c['expected_disclosure'];prediction=p['disclosure']
                if logs[c['id']]!=c['expected_log']:raise ValueError('Independent output oracle failed '+c['id'])
            else:
                expected=c['lookup_capable'] and profile=='cve-vulnerable';prediction=p['unsafe_lookup']
                hits=[v for v in callbacks if v['request_id']==c['id']]
                if bool(hits)!=expected or len(hits)>1:raise ValueError('Independent native JNDI oracle failed '+profile+'/'+c['id'])
                if expected and (logs[c['id']]!='LOCAL_LOOKUP_MARKER' or not p['jndi_lookups']):raise ValueError('Lookup not confirmed by log output')
                expected_log='REDACTED' if c['mode']=='overwrite' else c[c['expected_property']]
                if not expected and logs[c['id']]!=expected_log:raise ValueError('Fixed/negative output oracle failed')
            rows.append(dict(id=c['id'],expected=expected,prediction=prediction,known=p['known'],
                             actual_origin=actual_origin,expected_origin=expected_origins,source_exact=source_exact,
                             log_value=logs[c['id']],frame=p['frame'],
                             message=p['message'],sink_seq=p.get('sink_seq'),logger_seq=p['logger_seq'],
                             field_evidence=p['evidence'],jndi_lookups=p['jndi_lookups']))
        report['profiles'][profile]={'metrics':metrics(rows),'queries':rows,'business_calls':len(cases),
                                    'native_jndi_callbacks':len(callbacks),'inference_limits':predictions['limitations']}
    save(out/'results.json',report)
    with (out/'results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        rows=[dict(profile=name,**data['metrics']) for name,data in report['profiles'].items()]
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    def pct(value):return 'N/A' if value is None else f'{value:.1%}'
    names={'controlled':'受控跨服务泄露','cve-vulnerable':'Log4j 2.14.1 漏洞配置',
           'cve-config-mitigated':'Log4j 2.14.1 + formatMsgNoLookups', 'cve-fixed':'Log4j 2.17.1 修复版'}
    lines=['# 字段溯源支持安全确认：首轮实验（2026-10-15）','',
           '结论：本次新增的有界安全观测／离线重建扩展，已经能把指定字段来源连接到真实日志参数，并用实际日志或本地 JNDI 查询确认影响。尚不代表通用漏洞检测能力。','',
           '这是新的两 JVM 受控应用，不是 Sock Shop 漏洞。已知漏洞部分使用官方未修改的 Log4j 库与小型应用夹具，复现 CVE-2021-44228 的危险 lookup 求值路径；没有访问 LDAP、加载远程代码或执行 RCE。','',
           '## 结果','',
           '| 配置 | 业务／查询 | TP | FP | FN（含阳性 unknown） | TN | Unknown | Precision | Recall | F1 | 覆盖率 |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for profile,data in report['profiles'].items():
        m=data['metrics'];lines.append('| '+names[profile]+' | '+' | '.join(str(m[k]) for k in ('queries','tp','fp','fn_including_unknown_positive','tn','unknown'))+' | '
                                      +' | '.join(pct(m[k]) for k in ('precision','recall','f1','coverage'))+' |')
    lines += ['', '共 37/37 业务调用通过。缓解版、修复版没有阳性样本和阳性预测，Precision/Recall/F1 无定义，记 N/A，不写成 100%。两类实验使用不同安全判据，不合并分母。','',
              '## 受控案例','',
              '22 个请求包括直接泄露、公开字段、同值异字段、局部变量覆盖、对象字段复制／覆盖、读取但未使用的敏感字段、与敏感值相同的常量、未知 helper 及 12 个并发请求。','',
              '并发组使用同一业务 ID、完全相同的字段值，并在日志前设置屏障，使 12 个实际业务帧重叠。每次源服务响应生成独立 UUID；来源只按消息身份、属性名与对象字段版本关联，不按业务值、请求名称或时间近似匹配。','',
              '未知 helper 实际把敏感字符串复制到日志，但当前无此调用的重建模型，因此保留 unknown。它作为真实泄露的漏检计入 FN：TP=9、FN=1，Recall=90%，没有只统计成功重建的查询。','',
              '## 已知漏洞的确认依据','',
              '每个库配置五个输入：直接 lookup、经对象字段复制的 lookup、覆盖后的 lookup、普通消息、公开但可控字段中的 lookup。漏洞配置有三个触发点，两个负例；配置缓解版及修复版各五个输入均不触发。','',
              '证据链：源服务字段快照 → 实际 HTTP 消息身份／JSON 内容 → 目标字段读取和选定分支 → 实际 Logger.info 参数 → 原生 JndiLookup.lookup 参数 → 本地 Context.lookup 回调 → 日志中的 LOCAL_LOOKUP_MARKER。','',
              '来源重建只读两端观测和原始字节码模型，不读取用例真值。原生 lookup 钩子仅观测参数。`${jndi:key}` 到 lookup 参数的连接采用明确披露的单个字面表达式模型，验证实际 key；不宣称还原 Log4j 内部每条语句。','',
              '原生库未改传播算法或写入来源标签；测试 JVM 的 JNDI provider 被替换为只返回固定字符串的本地测试提供器。因此证明危险求值路径及修复前后行为差异，不证明该环境具备远程代码执行条件。','',
              '## 验证与证据','',
              '`audit.json` 核验构件 SHA-256、原始库 class、原始应用 class、每个配置的 80 条 Flow 指令及操作数（独立 javap）、业务覆盖和真实帧重叠。`negative-controls.json` 保存对消息身份、分支、版本、目标参数和 lookup 参数等证据的破坏测试。','',
              '各配置目录包含 `source/events.jsonl`、`target/events.jsonl`、`application.log`、`callbacks.jsonl`（仅有触发时）、逐查询 `predictions.json` 和 `business.json`。主结果为 `results.json` / `results.csv`。','',
              '## 能力边界','',
              '- 新增前端和离线参考复制重建是实验扩展，不是此前 Sock Shop 结果自动具备的能力。当前只支持有界无环引用复制、实际分支、默认三字段 JSON、单跳 HTTP 及已审计的新对象构造；其他调用可产生 unknown。',
              '- 只分析数据依赖，不支持一般隐式流；要求 DTO 在线程内独占，观测之外无并发字段修改。',
              '- 受控泄露规则事先规定 secret 不得进入该日志；不把任意敏感数据日志都视为实际产品漏洞。',
              '- 尚未发现新漏洞，未复现原始生产应用，未比较其他工具，也未测量可对比的在线／离线总成本。旧性能数据不能移用。','',
              '官方漏洞依据：[Apache Log4j 安全公告](https://logging.apache.org/security.html#CVE-2021-44228)。','']
    (out/'results.md').write_text('\n'.join(lines))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('prepare','build','freeze','run','evaluate'))
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--build',type=Path)
    args=parser.parse_args();out=args.out.resolve()
    if args.stage=='prepare':prepare(out)
    elif args.stage=='build':build(out)
    elif args.stage=='freeze':freeze(out)
    elif args.stage=='run':
        if not args.build:parser.error('--build is required')
        contract=json.loads((out/'contract.json').read_text())
        for profile,cfg in contract['profiles'].items():
            print('Running',profile,flush=True)
            run_profile(args.build.resolve(),out/profile,cfg,contract['controlled'] if profile=='controlled' else contract['cve'])
    else:
        result=evaluate(out);print(json.dumps({k:v['metrics'] for k,v in result['profiles'].items()},indent=2))
