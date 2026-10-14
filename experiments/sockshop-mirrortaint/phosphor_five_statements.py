#!/usr/bin/env python3
"""Run original Sock Shop accuracy workload with disclosed Phosphor statement hooks."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from zipfile import ZipFile

from host import ROOT, HERE
from sockshop import save, check_spec
from flowdist_full_order import CachedDeployment
from three_method_five import execute_workload
from phosphor_shipping import IMAGE, verify_tool


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def release(tool):
    if (tool/'Phosphor-0.0.3.jar').exists():
        verify_tool(tool)
        return 'Phosphor-0.0.3.jar','0.0.3'
    manifest=json.loads((tool/'manifest.json').read_text())
    jar=tool/'Phosphor-0.0.4.jar'
    if manifest['commit']!='6c15c9b2bb609b790cacfc9297d9f18724dcb1d6' or digest(jar)!=manifest['compiled_jar_sha256']:
        raise ValueError('Not the pinned official 0.0.4 source build')
    for name,expected in manifest['source_java_sha256'].items():
        if digest(tool/'source'/name)!=expected:raise ValueError('Upstream source changed: '+name)
    return jar.name,'0.0.4'


def build(out, tool):
    jar,version=release(tool)
    out.mkdir(parents=True, exist_ok=False)
    source = HERE / 'PhosphorStatementAgent.java'
    command = ['javac', '--release', '8', '-cp', str(tool / jar),
               '-d', str(out / 'classes'), str(source)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    (out / 'compile.log').write_text(result.stdout + result.stderr)
    with ZipFile(out / 'statement-agent.jar', 'w') as archive:
        archive.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nPremain-Class: PhosphorStatementAgent\n\n')
        for file in (out / 'classes').rglob('*.class'):
            archive.write(file, str(file.relative_to(out / 'classes')))
    save(out / 'manifest.json', {'source': str(source), 'source_sha256': digest(source),
         'agent_sha256': digest(out / 'statement-agent.jar'), 'phosphor_sha256': digest(tool / jar), 'phosphor_version':version,
         'propagation_engine_modified': False, 'business_bytecode_modified_on_disk': False,
         'profile': 'Orders selected physical getter reads to total write; Carts reference graph DAO result to return/delete/save; Shipping parameter reference graph to return',
         'limitations': ['Carts source graph tags reference values, not primitive field contents; scored queries are existential statement relations.',
                         'No implicit-flow propagation or cross-JVM tag transport.', 'No cost measurement in this run.']})


def partial_workload(out, result):
    """Attempt every frozen case; keep failed business cases out of accuracy."""
    import five_methods as five
    from host import prepare, submit
    urls=['http://127.0.0.1:'+str(port) for port in (18580,18581,18582,18583)]
    front,cart,orders,shipping=urls
    registry=json.loads((HERE/'cases.json').read_text())
    def remember(call,case,method,phase='accuracy'):
        try:row=call()
        except Exception as error:row={'case':case,'method':method,'phase':phase,'business_passed':False,'error':str(error)}
        result['cases'].append(row)
        save(out/'progress.json',{'cases_completed':len(result['cases']),'last_case':row})
    for case in registry['cases']:
        remember(lambda c=case:five.order_case(c,c['id'],out,front,cart,orders,'accuracy'),case['id'],'newOrder')
    base=registry['cases'][0]
    prepared=[prepare(base,'parallel-'+str(i),out/('parallel-'+str(i)),front,cart,shared=True)
              for i in range(registry['concurrent']['count'])]
    barrier=threading.Barrier(len(prepared))
    with ThreadPoolExecutor(max_workers=len(prepared)) as pool:
        futures=[pool.submit(submit,item,orders,out/('parallel-'+str(i)),barrier) for i,item in enumerate(prepared)]
        for i,(item,future) in enumerate(zip(prepared,futures)):
            try:row=future.result()
            except Exception as error:row={'case':'parallel-'+str(i),'business_passed':False,'error':str(error)}
            row.update(method='newOrder',phase='accuracy',trace_id=item[-1]['trace_id_requested']);result['cases'].append(row)
    for method in ('get','delete','mergeCarts','postShipping'):
        variants=('single','multi','empty') if method!='postShipping' else ('single','same-value')
        for variant in variants:
            name=method+'-'+variant
            remember(lambda m=method,n=name,v=variant:five.additional_case(m,n,out,cart,shipping,v),name,method)
    for method in five.METHODS:
        name='measurement-'+method+'-0'
        call=(lambda m=method,n=name:five.order_case(base,n,out,front,cart,orders,'measurement')) if method=='newOrder' else (
            lambda m=method,n=name:five.additional_case(m,n,out,cart,shipping,phase='measurement'))
        remember(call,name,method,'measurement')


def run(args):
    out, tool, build_dir, jre = [getattr(args, name).resolve() for name in ('out', 'tool', 'build', 'jre')]
    jar,version=release(tool)
    manifest = json.loads((build_dir / 'manifest.json').read_text())
    if digest(build_dir / 'statement-agent.jar') != manifest['agent_sha256'] or digest(HERE / 'PhosphorStatementAgent.java') != manifest['source_sha256']:
        raise ValueError('Statement adapter build changed')
    out.mkdir(parents=True, exist_ok=False)
    spec = json.loads((ROOT / 'scenarios/sockshop/compose.json').read_text())
    check_spec(spec)
    spec['networks'] = {'default': {'ipam': {'config': [{'subnet': args.subnet}]}}}
    for role, port, internal in (('front-end',18580,8079),('carts',18581,80),('orders',18582,80),('shipping',18583,80)):
        spec['services'][role]['ports'] = [f'127.0.0.1:{port}:{internal}']
    spec['services']['rabbitmq']['environment'] = {'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS': '+S 2:2 +A 8'}
    originals = {'orders': ROOT / 'artifacts/sockshop-orders-original-20261012/app.jar',
                 **{role: ROOT / 'artifacts/sockshop-five-methods-original-20261013' / (role + '.jar') for role in ('carts','shipping')}}
    inputs = {str(build_dir / 'statement-agent.jar'): digest(build_dir / 'statement-agent.jar'),
              str(tool / jar): digest(tool / jar), str(jre / 'lib/rt.jar'): digest(jre / 'lib/rt.jar')}
    for role, source in originals.items():
        shutil.copyfile(source, out / (role + '.jar'))
        cache = out / 'cache' / role
        cache.mkdir(parents=True)
        cache.chmod(0o777)
        cfg = spec['services'][role]
        cfg['image'] = IMAGE  # Matching native libraries for the pinned instrumented JRE.
        cfg['user'] = '1000:1000'
        cfg['mem_limit'] = '3g'
        cfg['volumes'] = [str(out / (role + '.jar')) + ':/tf2/app.jar:ro',
                          str(jre) + ':/phos-jre:ro', str(tool) + ':/phos-lib:ro',
                          str(build_dir / 'statement-agent.jar') + ':/tf2/statement-agent.jar:ro',
                          str(cache) + ':/tf2/cache:rw']
        cfg['entrypoint'] = ['/phos-jre/bin/java', '-Xms64m', '-Xmx1g', '-XX:+UseG1GC',
                            '-Djava.security.egd=file:/dev/urandom', '-Dspring.zipkin.enabled=false',
                            '-Xbootclasspath/a:/phos-lib/'+jar, '-javaagent:/tf2/statement-agent.jar',
                            '-javaagent:/phos-lib/'+jar+'=cacheDir=/tf2/cache', '-jar', '/tf2/app.jar', '--port=80']
        cfg['environment'] = {}
        inputs[str(out / (role + '.jar'))] = digest(source)
    for cfg in spec['services'].values():
        cfg['restart'] = 'no'
    file = out / 'compose.preflight.json'
    save(file, spec)
    save(out / 'protocol.json', {'accuracy_registry': json.loads((HERE / 'cases.json').read_text()),
         'additional_cases': {'get':['single','multi','empty'], 'delete':['single','multi','empty'],
                              'mergeCarts':['single','multi','empty'], 'postShipping':['single','same-value']},
         'accuracy_business_calls': 26, 'warmup': 0, 'measurement': 1,
         'source_hooks': manifest, 'input_sha256': inputs, 'accuracy_eligible': False, 'performance_eligible': False})
    project = 'tf2-phos-statements-' + secrets.token_hex(5)
    deployment = CachedDeployment(argparse.Namespace(project=project, ready_timeout=args.ready_timeout), out, file)
    result = {'mode': 'phosphor', 'project': project, 'status': 'unavailable', 'stage': 'startup',
              'cases': [], 'frontend_errors': [], 'phosphor_version':version, 'accuracy_eligible': False, 'performance_eligible': False}
    try:
        deployment.start()
        import five_methods
        five_methods.DB_CONTAINER = deployment.compose('ps', '-q', 'carts-db').stdout.strip()
        result['stage'] = 'business'
        if args.continue_on_failure:
            partial_workload(out,result)
        else:
            execute_workload(argparse.Namespace(warmup=0,repetitions=1), out, result)
        result['method_business_passed']={method:all(c['business_passed'] for c in result['cases'] if c['method']==method)
                                          for method in ('newOrder','get','delete','mergeCarts','postShipping')}
        result.update(status='business-passed' if all(c['business_passed'] for c in result['cases']) else 'partial-business-passed', stage='analysis')
    except Exception as error:
        result['error'] = str(error)
    finally:
        deployment.diagnostics()
        for role in ('orders','carts','shipping'):
            log = deployment.compose('logs', '--no-color', role, check=False).stdout
            (out / (role + '.log')).write_text(log)
        text = (out / 'compose.log').read_text(errors='replace')
        result['frontend_errors'] = [line for line in text.splitlines() if any(word in line for word in (
            'PHOSPHOR_STATEMENT_ERROR', 'java.lang.VerifyError', 'java.lang.NoSuchMethodError', 'java.lang.AbstractMethodError',
            'AnalyzerException', 'Calling uninstrumented Phosphor stubs'))]
        deployment.compose('down', '--volumes', '--remove-orphans', check=False, timeout=90)
        save(out / 'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, indent=2), flush=True)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=('build','run'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--build', type=Path)
    p.add_argument('--tool', type=Path, default=ROOT / 'artifacts/external-tools/phosphor-0.0.3')
    p.add_argument('--jre', type=Path, default=ROOT / 'artifacts/phosphor-shipping-20261014/jre')
    p.add_argument('--subnet', default='10.254.244.0/24')
    p.add_argument('--ready-timeout', type=int, default=420)
    p.add_argument('--continue-on-failure',action='store_true',help='Attempt independent method cases after an Orders business failure; failures remain separate')
    a = p.parse_args()
    if a.stage == 'build':
        build(a.out.resolve(), a.tool.resolve())
    else:
        if not a.build: p.error('--build is required')
        run(a)
