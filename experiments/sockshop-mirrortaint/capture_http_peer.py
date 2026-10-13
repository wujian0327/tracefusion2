#!/usr/bin/env python3
"""Passive capture in a callee network namespace, restricted to one Orders peer."""
import argparse
import json
from pathlib import Path
import signal
import socket
import struct
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--orders-ip', required=True)
parser.add_argument('--peer-ip', required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
orders = socket.inet_aton(args.orders_ip)
peer = socket.inet_aton(args.peer_ip)
running = True


def stop(*_):
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
sock.bind(('eth0', 0))
sock.settimeout(0.25)
packets = 0
with (args.out / 'http.pcap').open('wb') as output:
    output.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
    output.flush()
    (args.out / 'ready.json').write_text(json.dumps({'orders_ip': args.orders_ip, 'peer_ip': args.peer_ip}))
    while running:
        try:
            packet = sock.recv(65535)
        except socket.timeout:
            continue
        if len(packet) < 54 or packet[12:14] != b'\x08\x00':
            continue
        header = (packet[14] & 15) * 4
        if packet[23] != 6 or (packet[26:30], packet[30:34]) not in ((orders, peer), (peer, orders)):
            continue
        offset = 14 + header
        if len(packet) < offset + 4 or 80 not in struct.unpack('!HH', packet[offset:offset + 4]):
            continue
        now = time.time_ns()
        output.write(struct.pack('<IIII', now // 1000000000, now % 1000000000 // 1000, len(packet), len(packet)))
        output.write(packet)
        packets += 1
    output.flush()
stats = struct.unpack('II', sock.getsockopt(263, 6, 8))  # SOL_PACKET / PACKET_STATISTICS
sock.close()
(args.out / 'capture-result.json').write_text(json.dumps({'saved_packets': packets,
    'socket_packets': stats[0], 'socket_drops': stats[1], 'scope': 'callee eth0; exact Orders/peer IPv4 pair, TCP port 80'}, indent=2) + '\n')
