#!/usr/bin/env python3
"""Sock Shop deployment smoke check. Standard library only; not a lineage oracle."""
import argparse
import copy
import datetime as dt
import http.cookiejar
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / 'scenarios/sockshop/compose.json'
EXPECTED_SERVICES = {'front-end', 'user', 'user-db', 'carts', 'carts-db',
                     'orders', 'orders-db', 'payment', 'shipping', 'rabbitmq', 'queue-master'}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def check_spec(spec):
    assert set(spec['services']) == EXPECTED_SERVICES, 'Expected exactly 11 components'
    for name, service in spec['services'].items():
        assert ':' in service['image'] and not service['image'].endswith(':latest'), name
        assert service.get('platform') == 'linux/amd64', name
        for port in service.get('ports', []):
            assert port.startswith('127.0.0.1:'), 'Only loopback fixture ports are allowed'
        assert not any('docker.sock' in v for v in service.get('volumes', [])), name


def validate_payload(status, body):
    if not 200 <= status < 300:
        raise RuntimeError('HTTP status %s: %s' % (status, str(body)[:300]))
    if isinstance(body, dict):
        code = body.get('status_code', 200)
        if body.get('error') or (isinstance(code, int) and code >= 400):
            raise RuntimeError('Application error inside HTTP response: %s' % str(body)[:300])
    return body


class Client:
    def __init__(self, out):
        self.out = out
        self.events = []
        self.headers = {}
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, method, url, body=None, label='request', redact=False):
        encoded = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=encoded, method=method,
                                     headers=dict({'Content-Type': 'application/json'}, **self.headers))
        try:
            with self.opener.open(req, timeout=20) as response:
                status, raw = response.status, response.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read().decode('utf-8', errors='replace')
        try:
            result = json.loads(raw)
        except ValueError:
            result = raw
        event = {'label': label, 'method': method, 'url': url, 'status': status,
                 'response': result, 'time': dt.datetime.now(dt.timezone.utc).isoformat()}
        event['request'] = '<fixture registration credentials omitted>' if redact else body
        self.events.append(event)
        save(self.out / 'http-client-observations.json', self.events)
        return validate_payload(status, result)


def classify(value, original):
    if value is None or value == '':
        return 'absent_or_empty'
    if value == original:
        return 'full_value_returned'
    if isinstance(value, str) and len(original) >= 4 and value.endswith(original[-4:]) \
            and (len(value) == 4 or set(value[:-4]) <= {'*', 'X', 'x', '#'}):
        return 'last_four_only_or_masked'
    return 'different_value_needs_review'


def verify_order(order, fixture):
    """Verify the right fixture/order, independently classify sensitive fields."""
    if not isinstance(order, dict) or not order.get('id'):
        raise RuntimeError('Response is not a saved order object')
    if order.get('customerId') != fixture['customer_id']:
        raise RuntimeError('Order customerId does not match the newly created fixture')
    items = order.get('items')
    if not isinstance(items, list) or len(items) != 1:
        raise RuntimeError('Expected exactly one fixture item')
    expected = fixture['item']
    if any(items[0].get(k) != expected[k] for k in ('itemId', 'quantity', 'unitPrice')):
        raise RuntimeError('Order item is not the preseeded fixture')
    total = order.get('total')
    if not isinstance(total, (float, int)) or not math.isclose(
            total, expected['quantity'] * expected['unitPrice'] + 4.99, abs_tol=0.01):
        raise RuntimeError('Order total differs from original shipping + item formula')
    card = order.get('card') or {}
    address = order.get('address') or {}
    customer = order.get('customer') or {}
    if not all(isinstance(x, dict) for x in (card, address, customer)):
        raise RuntimeError('Unexpected nested object shape')
    return {'order_id': order['id'], 'fixture_identity_verified': True,
            'fields': { 'card.longNum': classify(card.get('longNum'), fixture['card']['longNum']),
                        'card.ccv': classify(card.get('ccv'), fixture['card']['ccv']),
                        'address.street': classify(address.get('street'), fixture['address']['street']),
                        'customer.firstName': classify(customer.get('firstName'), fixture['firstName'])}}


def require_id(value, label):
    ident = value.get('id') if isinstance(value, dict) else None
    if not isinstance(ident, str) or not re.fullmatch('[0-9a-fA-F]{24}', ident):
        raise RuntimeError('%s did not return a Mongo object id: %r' % (label, value))
    return ident


def smoke(out, front, cart, client=None):
    client = client or Client(out)
    token = secrets.token_hex(6)
    fixture = {'username': 'tf2_' + token, 'firstName': 'TF2_' + token,
               'lastName': 'Synthetic',
               'card': {'longNum': '4111111111111111', 'expires': '12/30', 'ccv': '123'},
               'address': {'number': '17', 'street': 'TF2_' + token + '_Street',
                           'city': 'TestCity', 'postcode': '000000', 'country': 'TestCountry'},
               'item': {'itemId': 'tf2_item_' + token, 'quantity': 1, 'unitPrice': 5.0}}
    credentials = {'username': fixture['username'], 'password': secrets.token_hex(16),
                   'email': fixture['username'] + '@example.invalid',
                   'firstName': fixture['firstName'], 'lastName': fixture['lastName']}
    # Registration obtains a real frontend session; no forged logged_in cookie.
    fixture['customer_id'] = require_id(client.request(
        'POST', front + '/register', credentials, 'register', redact=True), 'register')
    save(out / 'fixture.json', fixture)
    fixture['address_id'] = require_id(client.request(
        'POST', front + '/addresses', fixture['address'], 'create-address'), 'address')
    fixture['card_id'] = require_id(client.request(
        'POST', front + '/cards', fixture['card'], 'create-card'), 'card')
    save(out / 'fixture.json', fixture)
    client.request('POST', cart + '/carts/' + fixture['customer_id'] + '/items',
                   fixture['item'], 'preseed-cart')
    # This existing endpoint exposes only the last four digits in upstream code.
    preview = client.request('GET', front + '/card', label='card-preview')
    save(out / 'card-preview.json', preview)
    if not isinstance(preview, dict) or preview.get('number') != fixture['card']['longNum'][-4:]:
        raise RuntimeError('Original /card preview is not the expected last-four response')
    order = client.request('POST', front + '/orders', {}, 'create-order')
    save(out / 'order-response.json', order)
    result = verify_order(order, fixture)
    result['card_preview_last_four_verified'] = True
    result['observation_scope'] = 'test-client HTTP responses; no internal field lineage captured'
    return result


HEALTH_JS = """var http=require('http');
var hosts=['user','carts','orders','payment','shipping']; var left=hosts.length, bad=false;
function done(host,ok){console.log(host+': '+(ok?'ready':'not-ready'));bad=bad||!ok;
 if(--left===0)process.exit(bad?1:0);}
hosts.forEach(function(host){var finished=false;
 function end(ok){if(!finished){finished=true;done(host,ok);}}
 var r=http.get('http://'+host+'/health',function(res){var b='';res.on('data',function(x){b+=x;});
 res.on('end',function(){try{var j=JSON.parse(b); var h=j.health;
 end(res.statusCode===200&&Array.isArray(h)&&h.length>0&&h.every(function(x){return x.status==='OK';}));
 }catch(e){end(false);}});});r.setTimeout(4000,function(){r.abort();end(false);});
 r.on('error',function(){end(false);});});"""


class Deployment:
    def __init__(self, args, out, compose_file=COMPOSE):
        self.args, self.out = args, out
        self.file = compose_file

    def command(self, cmd, timeout=60, check=True):
        with (self.out / 'commands.log').open('a', encoding='utf-8') as log:
            log.write(json.dumps(cmd) + '\n'); log.flush()
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=timeout)
            log.write(p.stdout + '\n')
        if check and p.returncode:
            raise RuntimeError('Command failed (%s): %s\n%s' % (p.returncode, ' '.join(cmd), p.stdout[-1500:]))
        return p

    def compose(self, *args, **kwargs):
        return self.command(['docker', 'compose', '-p', self.args.project, '-f', str(self.file), *args], **kwargs)

    def start(self):
        if not shutil.which('docker'):
            raise RuntimeError('Docker is not installed. Run this package on a host with Docker Engine and Compose v2.')
        self.command(['docker', 'version'])
        self.command(['docker', 'compose', 'version'])
        self.compose('config', '--quiet')
        spec = json.loads(self.file.read_text())
        manifest = {}
        for service, cfg in spec['services'].items():
            image = cfg['image']
            if image in manifest:
                continue
            print('Pulling ' + image, flush=True)
            self.command(['docker', 'pull', '--platform', 'linux/amd64', image], timeout=600)
            inspected = self.command(['docker', 'image', 'inspect', image])
            obj = json.loads(inspected.stdout)[0]
            digests = obj.get('RepoDigests') or []
            if not digests:
                raise RuntimeError('Image has no registry digest: ' + image)
            manifest[image] = {'id': obj['Id'], 'digests': digests,
                               'architecture': obj.get('Architecture'),
                               'labels': obj.get('Config', {}).get('Labels')}
            save(self.out / 'images.json', manifest)
        locked = copy.deepcopy(spec)
        for cfg in locked['services'].values():
            cfg['image'] = manifest[cfg['image']]['digests'][0]
        self.file = self.out / 'compose.lock.json'
        save(self.file, locked)
        self.compose('up', '-d', timeout=180)
        deadline = time.monotonic() + self.args.ready_timeout
        while time.monotonic() < deadline:
            p = self.compose('exec', '-T', 'front-end', 'node', '-e', HEALTH_JS, check=False, timeout=15)
            if p.returncode == 0:
                q = self.compose('exec', '-T', 'rabbitmq', 'rabbitmqctl',
                                 'list_queues', 'name', 'consumers', check=False, timeout=20)
                if q.returncode == 0 and re.search(r'^shipping-task\s+[1-9]\d*\s*$', q.stdout, re.M):
                    save(self.out / 'readiness.json', {'application_health': p.stdout,
                                                      'queue_consumers': q.stdout})
                    return
            print('Waiting for services and shipping consumer...', flush=True)
            time.sleep(3)
        raise RuntimeError('Readiness timeout: no order submitted; inspect commands.log and compose.log')

    def diagnostics(self):
        if not shutil.which('docker'):
            return
        for filename, argv in [('compose.log', ('logs', '--no-color', '--tail', '250')),
                               ('compose-ps.json', ('ps', '--all', '--format', 'json'))]:
            try:
                p = self.compose(*argv, check=False, timeout=30)
                (self.out / filename).write_text(p.stdout, encoding='utf-8')
            except Exception as exc:
                (self.out / filename).write_text(str(exc), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'run', 'down'])
    parser.add_argument('--project', default='tracefusion2-sockshop')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--ready-timeout', type=int, default=240)
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]*', args.project):
        parser.error('project must use lowercase letters, digits, hyphens or underscores')
    check_spec(json.loads(COMPOSE.read_text()))
    if args.action == 'check':
        print('PASS: 11 components, versioned images, loopback ports, no Docker socket mount.')
        print('This is a static package check, not a Docker deployment test.')
        return 0
    if args.action == 'down':
        if not shutil.which('docker'):
            print('Docker is not installed.', file=sys.stderr); return 1
        return subprocess.call(['docker', 'compose', '-p', args.project, '-f', str(COMPOSE), 'down'])
    out = (args.out or ROOT / 'artifacts' / ('sockshop-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S')
                                           + '-' + secrets.token_hex(2))).resolve()
    out.mkdir(parents=True, exist_ok=False)
    deployment = Deployment(args, out)
    result = {'status': 'failed', 'stage': 'deployment', 'project': args.project,
              'lineage_accuracy': None, 'lineage_oracle_available': False}
    try:
        deployment.start()
        result['stage'] = 'order-smoke'
        front = 'http://127.0.0.1:' + os.environ.get('TF2_FRONT_PORT', '18080')
        cart = 'http://127.0.0.1:' + os.environ.get('TF2_CART_PORT', '18081')
        result.update(smoke(out, front, cart))
        result.update(status='passed', stage='complete')
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        deployment.diagnostics()
        save(out / 'result.json', result)
        shutil.copyfile(ROOT / 'scenarios/sockshop/sources.json', out / 'sources.json')
        bundle = out.with_suffix('.zip')
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(out.iterdir()):
                if path.is_file():
                    archive.write(path, path.name)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('RESULT BUNDLE: ' + str(bundle))
        print('Any started containers are kept; stop with: python3 scripts/sockshop.py down --project ' + args.project)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
