"""Whole-command wait4 measurement; parent owns persistence of piped child output."""
import os
import json
import signal
import subprocess
import time


def save(path, data):
    """Commit a complete JSON record, rather than overwriting a live manifest."""
    temporary=path.with_name(path.name+".pending")
    with temporary.open("w") as f:
        json.dump(data,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)
    descriptor=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def measured(cmd, dest, supervisor):
    dest.mkdir(parents=True)
    metric=dest/"resource.txt"
    argv=[str(supervisor),str(metric),*map(str,cmd)]
    begin=time.perf_counter()
    child=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        stdout,stderr=child.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL)
        stdout,stderr=child.communicate()
        for name,data in (("stdout.txt",stdout),("stderr.txt",stderr)):(dest/name).write_bytes(data)
        raise
    # An earlier local archive had missing output despite an immediate successful read.
    # Retain actual pipe bytes, never reconstruct output from an expected answer.
    # The cause was not established; verification must still reopen every artifact.
    for name,data in (("stdout.txt",stdout),("stderr.txt",stderr)):
        with (dest/name).open("wb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
    wall=time.perf_counter()-begin
    if child.returncode:raise RuntimeError(f"command exited {child.returncode}; inspect {dest}")
    user,system,rss,floor=metric.read_text().split()
    record=dict(command=list(map(str,cmd)),wall_seconds=wall,user_seconds=float(user),system_seconds=float(system),
        cpu_seconds=float(user)+float(system),peak_rss_kib=int(rss),supervisor_rss_kib=int(floor),
        rss_above_supervisor_floor=int(floor)>0 and int(rss)>2*int(floor),
        output_persistence="parent-pipes-v1")
    save(dest/"measurement.json",record)
    return record
