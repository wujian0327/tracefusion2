#!/usr/bin/env python3
"""Reproduce pre-exec RSS contamination; this is not a target benchmark."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def child_peak():
    child = subprocess.Popen(['/bin/true'], start_new_session=True)
    _, status, usage = os.wait4(child.pid, 0)
    child.returncode = os.waitstatus_to_exitcode(status)
    if child.returncode:
        raise RuntimeError('Control child failed')
    return usage.ru_maxrss * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child-supervisor', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.child_supervisor:
        print(child_peak())
        return
    before = child_peak()
    allocation = bytearray(120*1024*1024)
    after = child_peak()
    fresh = int(subprocess.check_output([sys.executable, __file__, '--child-supervisor']))
    result = dict(target='/bin/true', small_parent_peak_bytes=before,
        allocated_parent_peak_bytes=after, allocation_bytes=len(allocation),
        fresh_supervisor_child_peak_bytes=fresh,
        parent_memory_affects_child_maxrss=after > before + 100*1024*1024,
        fresh_supervisor_reduces_inherited_floor=fresh < after - 100*1024*1024,
        host_performance_result=False,
        scope='Local measurement mechanism only; a Python supervisor still has its own RSS floor')
    if args.output:
        args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
