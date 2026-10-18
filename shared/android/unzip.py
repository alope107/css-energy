#!/usr/bin/env python3
# Minimal unzip that keeps unix permissions and symlinks (no `unzip` in the container).
# usage: python3 -I unzip.py <zip> <destdir>
import os, sys, zipfile, stat

zpath, dest = sys.argv[1], os.path.abspath(sys.argv[2])
os.makedirs(dest, exist_ok=True)
with zipfile.ZipFile(zpath) as z:
    for info in z.infolist():
        target = os.path.abspath(os.path.join(dest, info.filename))
        if not (target == dest or target.startswith(dest + os.sep)):
            raise SystemExit(f"unsafe path in zip: {info.filename}")
        mode = info.external_attr >> 16
        if info.is_dir():
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if stat.S_ISLNK(mode):
            link = z.read(info).decode()
            if os.path.lexists(target):
                os.unlink(target)
            os.symlink(link, target)
            continue
        with z.open(info) as src, open(target, "wb") as dst:
            while True:
                b = src.read(1 << 20)
                if not b:
                    break
                dst.write(b)
        if mode & 0o777:
            os.chmod(target, mode & 0o777)
