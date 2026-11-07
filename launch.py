#!/usr/bin/env python3
"""Detached launcher: survives the parent shell/session going away."""
import os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))

def spawn(argv, log):
    f = open(os.path.join(BASE, log), "w")
    p = subprocess.Popen(argv, cwd=BASE, stdout=f, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    print(f"started {argv[0]} pid={p.pid}")
    return p

os.chdir(BASE)
spawn(["/bin/sh", "-c", "pkill -f 'pointerd$'; pkill -f server.py; pkill -f handmouse/viewer; sleep 0.6; exit 0"], "spawn.log")
time.sleep(1.0)
spawn(["./pointerd"], "pointerd.log")
time.sleep(1.5)
spawn([sys.executable, "server.py"], "server.log")
time.sleep(2.0)
spawn(["./viewer"], "viewer.log")
time.sleep(1.0)
print("done")
