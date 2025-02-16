#!/usr/bin/env python

import argparse
import os
import pacdb
import subprocess
import sys

parser = argparse.ArgumentParser(description='Mirror packages from a pacman sync db, via rsync')
parser.add_argument('-e', '--repo', required=True, help='pacman repo name to mirror')
parser.add_argument('-n', '--no-sync-db', action='store_true')
parser.add_argument('-v', '--verbose', action='count', help='output additional information')
parser.add_argument('url', help='source rsync url')
parser.add_argument('dir', help='destination dir')

options = parser.parse_args()

def popen_rsync():
    return subprocess.Popen(["rsync", "-rptHL" + ("v" if options.verbose else ""), "--from0", "--files-from", "-", options.url, options.dir], stdin=subprocess.PIPE, close_fds=True, text=True)


# unfortunately, I don't think there's any way to know the .tar.X extension,
# so just get the straight .db and .files without the extra extensions
if options.no_sync_db:
    files = set(options.repo + ext + sig for sig in ("", ".sig") for ext in (".db", ".files"))
else:
    files = set()
    p = popen_rsync()
    for t in (".db", ".files"):
        files.add(options.repo + t)
        print(options.repo + t, end="\0", file=p.stdin)
        files.add(options.repo + t + ".sig")
        print(options.repo + t + ".sig", end="\0", file=p.stdin)
    p.stdin.close()
    p.wait()

db = pacdb.Database(options.repo, filename=os.path.join(options.dir, options.repo+".db"))

p = popen_rsync()
for pkg in db:
    files.add(pkg.filename)
    print(pkg.filename, end="\0", file=p.stdin)
    files.add(pkg.filename + ".sig")
    print(pkg.filename + ".sig", end="\0", file=p.stdin)
p.stdin.close()
p.wait()

toremove = [f for f in os.listdir(options.dir) if f not in files]
if options.verbose and toremove:
    print("Removing:", "\n\t".join(toremove), sep="\n\t", file=sys.stderr)

for f in toremove:
    os.unlink(os.path.join(options.dir, f))

