#!/usr/bin/env python

import pacdb

build32 = pacdb.Database.from_url('build32', 'https://github.com/jeremyd2019/msys2-build32/releases/download/repo')
msys64 = pacdb.msys_db_by_arch('x86_64')

pkgs64 = {str(pkg): pkg for pkg in msys64}
pkgs32 = {str(pkg): pkg for pkg in build32}

# HACK for rename of msys2-runtime-3.3 to msys2-runtime on i686
pkgs32.update({k[:13] + "-3.3" + k[13:]: v for k, v in pkgs32.items() if v.name in ("msys2-runtime", "msys2-runtime-devel")})

updates = pkgs64.keys() - pkgs32.keys()

def base(pkg):
    return pkg.base or pkg.name

print(" ".join(sorted({base(pkgs64[fullname]) for fullname in updates})))


