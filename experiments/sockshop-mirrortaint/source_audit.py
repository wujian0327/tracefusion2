#!/usr/bin/env python3
"""Verify frozen Git revisions and source files, independently of engine output."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
FILES = {
    'orders': ['pom.xml', 'src/main/java/works/weave/socks/orders/controllers/OrdersController.java',
               'src/main/java/works/weave/socks/orders/entities/CustomerOrder.java',
               'src/main/java/works/weave/socks/orders/entities/Shipment.java',
               'src/main/java/works/weave/socks/orders/services/AsyncGetService.java'],
    'carts': ['pom.xml', 'src/main/java/works/weave/socks/cart/controllers/ItemsController.java',
              'src/main/java/works/weave/socks/cart/item/ItemResource.java',
              'src/main/java/works/weave/socks/cart/entities/Item.java'],
    'shipping': ['pom.xml', 'src/main/java/works/weave/socks/shipping/controllers/ShippingController.java'],
    'user': ['api/service.go', 'api/transport.go'],
    'payment': ['service.go', 'endpoints.go'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources-dir', required=True, type=Path,
                        help='Parent containing sockshop-orders/carts/shipping/user/payment clones')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    lock = json.loads((HERE / 'sources.json').read_text())
    results = {}
    for name, wanted in lock['applications'].items():
        source = args.sources_dir / ('sockshop-' + name)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        if head != wanted['commit']:
            raise ValueError('Wrong original revision: ' + name)
        subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--'], cwd=source, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        digests = {path: hashlib.sha256((source / path).read_bytes()).hexdigest()
                   for path in FILES[name]}
        results[name] = {'commit': head, 'tracked_source_unmodified': True, 'sha256': digests}
    output = {'applications': results, 'engine_output_read': False,
              'source_image_correspondence_verified': False,
              'execution_oracle_available': False, 'second_human_reviewed': False}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + '\n')
    print('PASS: five pinned original repositories and source fingerprints; runtime oracle still pending')


if __name__ == '__main__':
    main()
