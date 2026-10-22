#!/usr/bin/env python3
"""Audit the isolated-core costs against raw samples and native library bytes."""
import argparse
import json
from pathlib import Path
from run_planned_service import load, save, sha
from run_isolated_cost import check, JVM
from audit_jackson_isolation import mapper_hash
from audit_application_call_revision import class_hashes
from isolate_agent_jackson import symbolic_types, OLD
from zipfile import ZipFile


def audit(root):
    check(root)
    classes = class_hashes(root/'bound-base/distributed-observer.jar')
    receipts = []
    for kind in ('cart', 'train', 'price'):
        b = root/(kind+'-build')
        assert class_hashes(b/'distributed-observer.jar') == classes
        with ZipFile(b/'distributed-observer.jar') as z:
            assert not any(n.startswith('com/fasterxml/jackson/') for n in z.namelist())
            for n in z.namelist():
                if n.endswith('.class'):
                    assert not any(OLD in t for t in symbolic_types(z.read(n)))
        cfg = load(root/('cost-'+kind)/'config.json')
        assert cfg['jvm'] == JVM
        for name, mode in cfg['order']:
            d = root/('cost-'+kind)/name
            cap = d/('trainticket' if kind == 'price' else 'capture')
            spec = load(cap/'compose.json')
            roles = list(load(b/'build.json')['inputs']) if kind == 'price' else ['carts' if kind == 'cart' else 'train']
            for role in roles:
                service = 'carts' if role == 'carts' else 'ts-'+role+'-service'
                options = spec['services'][service]['environment']['JAVA_OPTS']
                assert options == JVM + ('' if mode == 'original' else ' -javaagent:/tf2/observer.jar -Dservice.plan=/tf2/plan.json -Dservice.events=/tf2/capture/events.jsonl -Dservice.mode='+mode)
                if mode == 'original':
                    continue
                rows = [json.loads(s) for s in (cap/role/'events.jsonl').read_text().splitlines()]
                proofs = [r for r in rows if r['kind'] == 'jackson-isolation']
                assert proofs, (kind, name, role)
                native = mapper_hash(b/role/'original.jar')
                assert all(r['business_class_sha256'] == native[1] and r['agent_class_sha256'] == classes['tracefusion/internal/jackson/databind/ObjectMapper.class'] for r in proofs)
                plan = load(b/role/'plan.json')
                assert plan['source_evidence'] is True
                assert rows[0]['plan_sha256'] == sha(b/role/'plan.json')
                receipts.append({'kind':kind,'trial':name,'role':role,'native':native,'proofs':proofs,'events_sha256':sha(cap/role/'events.jsonl')})
    assert len(receipts) == 70
    save(root/'native-cost-audit.json', {'all_passed':True,'observed_jvms_verified':len(receipts),'agent_classes':len(classes),'receipts':receipts,'all_JVM_options_equal':True,'raw_HTTP_audit_cost_included':True})
    from audit_lifecycle_cost import audit as cost_audit
    cost_audit(root, ('calibration-audit.json','native-cost-audit.json'))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--root',required=True,type=Path)
    audit(p.parse_args().root.resolve())
