#!/usr/bin/env python3
"""Correct a packaging-only Orders launch failure, preserving first evidence.

The frozen first driver remains byte-identical. Derive its Orders routine with
only a new destination and native-only jobs; restore the missing original-JAR
mount. Save the exact derived source before running, not a second TF attempt.
"""
import argparse,inspect,ast
from pathlib import Path
import run_heldout29_first as h


def run(root):
    h.check(root)
    first=root/'orders-first/native'
    assert (first/'failure.json').exists(),'Wait for the immutable first failure receipt'
    assert not (first/'capture/run.json').exists(),'This correction is only for failure before any query request'
    configure=h.native_configure
    def corrected(spec,dest,base,bundle,q):
        configure(spec,dest,base,bundle,q)
        volumes=spec['services']['orders']['volumes'];assert not any(':/tf2/app.jar:'in v for v in volumes)
        volumes.append(str(base/'orders/original.jar')+':/tf2/app.jar:ro')
    h.native_configure=corrected
    source=inspect.getsource(h.run_orders)
    assert source.count("root/'orders-first'")==1
    source=source.replace("root/'orders-first'","root/'native-orders-packaging-correction'")
    tree=ast.parse(source)
    class NativeOnly(ast.NodeTransformer):
        def visit_Assign(self,node):
            if any(isinstance(t,ast.Name)and t.id=='jobs'for t in node.targets):node.value=ast.parse("[('mirrortaint',qs[0])]").body[0].value
            return node
    tree=ast.fix_missing_locations(NativeOnly().visit(tree));derived=ast.unparse(tree)+'\n'
    receipt=root/'native-orders-packaging-amendment.json'
    assert not receipt.exists()
    saved=root/'native-orders-packaging-routine.py';saved.write_text(derived)
    h.save(receipt,{'first_failure':str(first/'failure.json'),'core_unchanged':True,'truth_and_inputs_unchanged':True,'previous_queries_executed':False,'only_change':'Restore same original business JAR bind mount removed by native branch; native-only separate destination.','derived_routine_sha256':h.sha(saved),'correction_driver_sha256':h.sha(Path(__file__))})
    exec(compile(tree,str(saved),'exec'),h.__dict__)
    h.run_orders(root)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);run(p.parse_args().root.resolve())
