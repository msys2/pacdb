#!/usr/bin/env python

import datetime
import re
import tarfile
from typing import Dict, List, Set

_PackageEntry = Dict[str, List[str]]

# Utility functions
def _split_depends(deps: List[str]) -> Dict[str, Set[str]]:
    r: Dict[str, Set[str]] = {}
    for d in deps:
        parts = re.split("([<>=]+)", d, 1)
        first = parts[0].strip()
        second = "".join(parts[1:]).strip()
        r.setdefault(first, set()).add(second)
    return r

def _split_optdepends(deps: List[str]) -> Dict[str, Set[str]]:
    r: Dict[str, Set[str]] = {}
    for d in deps:
        if ":" in d:
            a, b = d.split(":", 1)
            a, b = a.strip(), b.strip()
        else:
            a, b = d.strip(), ""
        e = r.setdefault(a, set())
        if b:
            e.add(b)
    return r


class Database(object):
    def __init__(self, name: str, filename=None, fileobj=None):
        super(Database, self).__init__()
        self.name = name
        self.sources: Dict[str, _PackageEntry] = {}
        packages: Dict[str, list] = {}
        with tarfile.open(name=filename, fileobj=fileobj, mode="r:*") as tar:
            for info in tar.getmembers():
                package_name = info.name.split("/", 1)[0]
                infofile = tar.extractfile(info)
                if infofile is None:
                    continue
                with infofile:
                    packages.setdefault(package_name, []).append(
                        (info.name, infofile.read()))
        for package_name, infos in sorted(packages.items()):
            t = ""
            for name, data in sorted(infos):
                if name.endswith("/desc"):
                    t += data.decode("utf-8")
                elif name.endswith("/depends"):
                    t += data.decode("utf-8")
                elif name.endswith("/files"):
                    t += data.decode("utf-8")
            desc = self._parse_desc(t)
            self.sources[package_name] = desc

        # make a handy-dandy mapping
        self.byname: Dict[str, _PackageEntry] = {}
        for p in self.sources.values():
            self.byname[p['%NAME%'][0]] = p

    def get_pkg(self, pkgname: str):
        entry = self.byname.get(pkgname)
        return entry and Package(self, entry)

    @staticmethod
    def _parse_desc(t: str) -> _PackageEntry:
        d: _PackageEntry = {}
        cat = None
        values: List[str] = []
        for l in t.splitlines():
            l = l.strip()
            if cat is None:
                cat = l
            elif not l:
                d[cat] = values
                cat = None
                values = []
            else:
                values.append(l)
        if cat is not None:
            d[cat] = values
        return d


class Package(object):
    def __init__(self, db: Database, entry: _PackageEntry):
        super(Package, self).__init__()
        self.db = db
        self._entry = entry

    def _get_list_entry(self, name):
        return self._entry.get(name, list())

    def _get_single_entry(self, name):
        return self._entry.get(name, (None,))[0]

    @property
    def arch(self):
        return self._get_single_entry('%ARCH%')

    @property
    def base(self):
        return self._get_single_entry('%BASE%')

    @property
    def base64_sig(self):
        return self._get_single_entry('%PGPSIG%')
    
    @property
    def builddate(self):
        d = self._get_single_entry('%BUILDDATE%')
        return d and datetime.datetime.utcfromtimestamp(int(d))

    @property
    def checkdepends(self):
        return _split_depends(self._get_list_entry('%CHECKDEPENDS%'))

    @property
    def conflicts(self):
        return _split_depends(self._get_list_entry('%CONFLICTS%'))
    
    @property
    def depends(self):
        return _split_depends(self._get_list_entry('%DEPENDS%'))
    
    @property
    def desc(self):
        return self._get_single_entry('%DESC%')

    @property
    def download_size(self):
        d = self._get_single_entry('%CSIZE%')
        return d and int(d)

    @property
    def filename(self):
        return self._entry['%FILENAME%'][0]
    
    @property
    def files(self):
        return self._get_list_entry('%FILES%')

    @property
    def groups(self):
        return self._get_list_entry('%GROUPS%')

    @property
    def isize(self):
        d = self._get_single_entry('%ISIZE%')
        return d and int(d)

    @property
    def licenses(self):
        return self._get_list_entry('%LICENSE%')
    
    @property
    def makedepends(self):
        return _split_depends(self._get_list_entry('%MAKEDEPENDS%'))

    @property
    def md5sum(self):
        return self._get_single_entry('%MD5SUM%')

    @property
    def name(self):
        return self._entry['%NAME%'][0]

    @property
    def optdepends(self):
        return _split_optdepends(self._get_list_entry('%OPTDEPENDS%'))

    @property
    def packager(self):
        return self._get_single_entry('%PACKAGER%')

    @property
    def provides(self):
        return _split_depends(self._get_list_entry('%PROVIDES%'))

    @property
    def replaces(self):
        return _split_depends(self._get_list_entry('%REPLACES%'))

    @property
    def sha256sum(self):
        return self._get_single_entry('%SHA256SUM%')

    size = download_size

    @property
    def url(self):
        return self._get_single_entry('%URL%')

    @property
    def version(self):
        return self._entry['%VERSION%'][0]

    def compute_optionalfor(self) -> List[str]:
        optionalfor = []
        for pkgent in self.db.sources.values(): # TODO: somehow check other dbs?
            pkg = Package(self.db, pkgent)
            if self.name in pkg.optdepends:
                optionalfor.append(pkg.name)
        return optionalfor

    def compute_requiredby(self) -> List[str]:
        requiredby = []
        for pkgent in self.db.sources.values(): # TODO: somehow check other dbs?
            pkg = Package(self.db, pkgent)
            if self.name in pkg.depends: # TODO: check version?
                requiredby.append(pkg.name)
        return requiredby


def mingw_db_by_name(name: str) -> Database:
    from urllib.request import urlopen
    from io import BytesIO
    with urlopen('https://mirror.msys2.org/mingw/{0}/{0}.db'.format(name)) as u:
        with BytesIO(u.read()) as f:
            return Database(name, fileobj=f)
