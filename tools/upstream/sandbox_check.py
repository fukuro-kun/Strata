#!/usr/bin/env python3
"""Probe the inside of the benchmark sandbox: namespaces, loopback-only
networking, writable paths. Run inside the podman container to prove the
isolation properties the A/B protocol relies on (no net, read-only inputs,
no host secrets)."""

import os
import socket


def pr(*a):
    print(*a, flush=True)


pr("uid/gid:", os.getuid(), os.getgid())
for ns in ("net", "pid", "mnt", "uts", "ipc", "user"):
    try:
        pr("ns", ns, os.readlink("/proc/self/ns/" + ns))
    except OSError as e:
        pr("ns", ns, "ERR", e)
try:
    with open("/proc/self/uid_map") as f:
        pr("uid_map:", f.read().strip().replace("\n", " | "))
except OSError as e:
    pr("uid_map ERR", e)

s = socket.socket()
s.bind(("127.0.0.1", 0))
s.listen(1)
port = s.getsockname()[1]
pr("lo-listen-port:", port)
c = socket.socket()
c.settimeout(5)
c.connect(("127.0.0.1", port))
a, _ = s.accept()
c.sendall(b"PING")
pr("lo-data:", a.recv(4))
c.close()
a.close()
s.close()

try:
    o = socket.socket()
    o.settimeout(3)
    o.connect(("10.255.255.1", 9))
    pr("EXT-BAD: external connect succeeded")
except OSError as e:
    pr("ext-blocked:", type(e).__name__, getattr(e, "errno", None))
    o.close()

for p in ["/", "/home", "/root", "/etc", "/run", "/src", "/model", "/out",
          "/tmp", "/usr/local"]:
    try:
        pr("ls", p, "->", sorted(os.listdir(p))[:15])
    except OSError as e:
        pr("ls", p, "ERR", e)

for p in ["/home", "/root/.ssh", "/etc/ssh", "/var/run/docker.sock",
          "/run/user/1000", "/etc/shadow", "/etc/passwd"]:
    pr("exists", p, os.path.exists(p))


def wtest(p):
    try:
        with open(p, "w") as f:
            f.write("x")
        os.remove(p)
        pr("write", p, "OK")
    except OSError as e:
        pr("write", p, "BLOCKED", type(e).__name__, getattr(e, "errno", None))


for p in ("/out/w.txt", "/tmp/w.txt", "/usr/w.txt", "/etc/w.txt", "/w.txt"):
    wtest(p)
pr("check-done")
