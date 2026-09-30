#!/usr/bin/env python3
"""Bounded BCC/eBPF packet recorder for one explicit Sock Shop bridge.

Requires Linux root and the distribution's python3-bpfcc. No tcpdump fallback.
The persisted PCAP contains synthetic experiment payloads, including credentials.
"""
import argparse
import ctypes
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def filter_source(services):
    ips = sorted({int(ipaddress.IPv4Address(ip)) for ip in services})
    if not ips or len(ips) > 32:
        raise ValueError('Expected 1..32 explicitly selected experiment IPv4 addresses')
    expression = ' || '.join('(src == %du || dst == %du)' % (ip, ip) for ip in ips)
    source = (ROOT / 'instrumentation/ebpf/http_capture.c').read_text()
    return source.replace('TF2_IP_FILTER', expression)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface', required=True)
    p.add_argument('--services', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--seconds', type=int, default=300)
    p.add_argument('--max-mib', type=int, default=64)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    stats = {'status': 'failed', 'mechanism': 'bcc-ebpf-socket-filter',
             'interface': args.interface, 'packets_written': 0, 'bytes_written': 0,
             'socket_drops': None, 'fragmented_packets': None,
             'timestamp_source': 'userspace-receive-wall-clock',
             'scope': 'IPv4 TCP port 80/8079; explicit experiment IP allowlist'}
    sock = bpf = None
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        if args.seconds < 1 or args.max_mib < 1:
            raise ValueError('Capture limits must be positive')
        if os.geteuid() != 0:
            raise RuntimeError('Run this recorder as root on the Linux Docker host')
        from bcc import BPF
        services = json.loads(args.services.read_text())['ip_to_service']
        source = filter_source(services)
        stats['bpf_source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
        stats['ip_to_service'] = services
        bpf = BPF(text=source)
        function = bpf.load_func('capture_http', BPF.SOCKET_FILTER)
        BPF.attach_raw_socket(function, args.interface)
        sock = socket.socket(fileno=function.sock)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        # Promiscuity is reference counted and undone automatically on close.
        membership = struct.pack('IHH8s', socket.if_nametoindex(args.interface), 1, 0, b'')
        sock.setsockopt(263, 1, membership)  # SOL_PACKET / PACKET_ADD_MEMBERSHIP
        try:
            sock.setsockopt(socket.SOL_SOCKET, 35, 1)  # SO_TIMESTAMPNS on Linux amd64
            stats['timestamp_source'] = 'kernel-SO_TIMESTAMPNS'
        except OSError:
            pass
        sock.settimeout(0.25)
        stats['receive_buffer_bytes'] = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        started = time.monotonic()
        with (args.out / 'packets.pcap').open('xb') as f:
            f.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 262144, 1))
            f.flush()
            (args.out / 'ready.json').write_text(json.dumps({'ready': True, 'pid': os.getpid()}))
            while not stopped:
                if time.monotonic() - started >= args.seconds:
                    stats['limit_reached'] = 'duration'
                    break
                try:
                    packet, ancillary, flags, _ = sock.recvmsg(262144, 128)
                except socket.timeout:
                    continue
                if flags & socket.MSG_TRUNC:
                    raise RuntimeError('Packet exceeded snap length')
                stamp = time.time_ns()
                for level, kind, data in ancillary:
                    if level == socket.SOL_SOCKET and kind == 35 and len(data) >= 16:
                        sec, nsec = struct.unpack('qq', data[:16])
                        stamp = sec * 10**9 + nsec
                if stats['bytes_written'] + len(packet) + 16 > args.max_mib * 1024**2:
                    stats['limit_reached'] = 'storage'
                    break
                sec, nano = divmod(stamp, 10**9)
                f.write(struct.pack('<IIII', sec, nano // 1000, len(packet), len(packet)))
                f.write(packet)
                f.flush()
                stats['packets_written'] += 1
                stats['bytes_written'] += 16 + len(packet)
            os.fsync(f.fileno())
        stats['status'] = 'stopped' if stopped else 'limit_reached'
    except Exception as exc:
        stats['error'] = '%s: %s' % (type(exc).__name__, exc)
        print(stats['error'], file=sys.stderr)
    finally:
        if sock:
            try:
                received, dropped = struct.unpack('II', sock.getsockopt(263, 6, 8))
                stats.update(socket_packets=received, socket_drops=dropped)
            except OSError as exc:
                stats['statistics_error'] = str(exc)
            sock.close()
        # BCC __len__ counts lazily opened tables. A loaded module can be falsey
        # before its first table lookup; that does not mean initialization failed.
        if bpf is not None:
            try:
                stats['filter_accepted_packets'] = int(bpf['counters'][ctypes.c_int(0)].value)
                stats['fragmented_packets'] = int(bpf['counters'][ctypes.c_int(1)].value)
            except Exception as exc:
                # Preserve the original load/capture error even if map access fails.
                stats['bpf_statistics_error'] = '%s: %s' % (type(exc).__name__, exc)
        (args.out / 'capture.json').write_text(json.dumps(stats, indent=2) + '\n')
    return 0 if stats['status'] == 'stopped' else 1


if __name__ == '__main__':
    raise SystemExit(main())
