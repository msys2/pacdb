#!/usr/bin/env python

import datetime
import re
import sys
import tarfile
from collections import namedtuple
from itertools import zip_longest
from typing import Dict, List, Set, Any, Tuple, Optional, Union, Iterator

__all__ = ['Database', 'Package', 'Version', 'mingw_db_by_name',
           'msys_db_by_arch', 'vercmp']

# Arch uses ':', MSYS2 uses '~'
EPOCH_SEPS = frozenset(":~")

_PackageEntry = Dict[str, List[str]]
_DependEntry = namedtuple('_DependEntry', ['name', 'mod', 'version', 'desc'])
_DEPENDRE = re.compile(r'([^<>=]+)(?:(<=|>=|<|>|=)(.*))?')

def _split_depends(deps: List[str]) -> Dict[str, Set[_DependEntry]]:
    r: Dict[str, Set[_DependEntry]] = {}
    for d in deps:
        e = d.rsplit(': ', 1)
        desc = e[1] if len(e) > 1 else None
        entry = _DependEntry(*_DEPENDRE.fullmatch(e[0]).groups(), desc)
        r.setdefault(entry.name, set()).add(entry)
    return r

class Version(object):
    def __init__(self, ver: Union[str, "Version", None]):
        super(Version, self).__init__()
        if isinstance(ver, Version):
            self.ver = ver.ver
            self.e, self.v, self.r = ver.e, ver.v, ver.r
        elif ver is not None:
            self.ver = ver
            self.e, self.v, self.r = self._split(ver)
        else:
            self.ver, self.e, self.v, self.r = (None, None, None, None)

    def __str__(self):
        return str(self.ver)

    def __repr__(self):
        return f'Version({repr(self.canonicalize())})'

    @staticmethod
    def _split(v: str) -> Tuple[str, str, Optional[str]]:
        m = re.split(r'(\D)', v, 1)
        if len(m) == 3 and m[1] in EPOCH_SEPS:
            e = m[0]
            v = m[2]
        else:
            e = "0"

        r: Optional[str] = None
        rs = v.rsplit("-", 1)
        if len(rs) == 2:
            v, r = rs

        return (e, v, r)

    class _ExtentType(object):
        pass

    _DIGIT, _ALPHA, _OTHER = _ExtentType(), _ExtentType(), _ExtentType()

    @classmethod
    def _get_type(cls, c: str) -> _ExtentType:
        assert c
        if c.isdigit():
            return cls._DIGIT
        elif c.isalpha():
            return cls._ALPHA
        else:
            return cls._OTHER

    @classmethod
    def _parse(cls, v: str) -> Iterator[str]:
        current = ""
        for c in v:
            if not current:
                current += c
            else:
                if cls._get_type(c) is cls._get_type(current):
                    current += c
                else:
                    yield current
                    current = c

        if current:
            yield current

    @classmethod
    def _rpmvercmp(cls, v1: str, v2: str) -> int:
        if v1 == v2:
            return 0

        def cmp(a: Any, b: Any) -> int:
            return (a > b) - (a < b)

        for p1, p2 in zip_longest(cls._parse(v1), cls._parse(v2), fillvalue=None):
            if p1 is None:
                if cls._get_type(p2) is cls._ALPHA:
                    return 1
                return -1
            elif p2 is None:
                if cls._get_type(p1) is cls._ALPHA:
                    return -1
                return 1

            t1 = cls._get_type(p1)
            t2 = cls._get_type(p2)
            if t1 is not t2:
                if t1 is cls._DIGIT:
                    return 1
                elif t2 is cls._DIGIT:
                    return -1
                elif t1 is cls._OTHER:
                    return 1
                elif t2 is cls._OTHER:
                    return -1
            elif t1 is cls._OTHER:
                ret = cmp(len(p1), len(p2))
                if ret != 0:
                    return ret
            elif t1 is cls._DIGIT:
                ret = cmp(int(p1), int(p2))
                if ret != 0:
                    return ret
            elif t1 is cls._ALPHA:
                ret = cmp(p1, p2)
                if ret != 0:
                    return ret

        return 0

    def vercmp(self, other: Union[str, "Version", None]) -> Union[int, type(NotImplemented)]:
        if isinstance(other, Version):
            if self.ver == other.ver:
                return 0
        elif isinstance(other, str):
            if self.ver == other:
                return 0
            other = Version(other)
        elif other is None:
            return 1 if self.ver is not None else 0
        else:
            return NotImplemented

        if self.ver is None:
            return -1
        elif other.ver is None:
            return 1

        ret = self._rpmvercmp(self.e, other.e)
        if ret == 0:
            ret = self._rpmvercmp(self.v, other.v)
            if ret == 0 and self.r is not None and other.r is not None:
                ret = self._rpmvercmp(self.r, other.r)

        return ret

    __cmp__ = vercmp

    def __lt__(self, other: Union[str, "Version", None]):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) < 0

    def __le__(self, other: Union[str, "Version", None]):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) <= 0

    def __eq__(self, other: Union[str, "Version", None]):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) == 0

    def __gt__(self, other: Union[str, "Version", None]):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) > 0

    def __ge__(self, other: Union[str, "Version", None]):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) >= 0

    # this should actually be impossible due to type annotations
    if sys.version_info[0] < 3:
        def __ne__(self, other: Union[str, "Version", None]):
            if not isinstance(other, (str, Version, type(None))):
                return NotImplemented
            return not self == other

    def __bool__(self):
        return self.ver is not None

    def __hash__(self):
        return hash(self.canonicalize())

    def canonicalize(self, epochsep: str=':') -> Optional[str]:
        if self.ver is None:
            return None

        v = ""
        if self.e != "0":
            v = self.e.lstrip('0') + epochsep

        for p in self._parse(self.v):
            t = self._get_type(p)
            if t is self._OTHER:
                v += "."
            elif t is self._DIGIT:
                v += p.lstrip('0')
            else:
                v += p

        if self.r is not None:
            v += "-" + self.r.lstrip('0')

        return v


def vercmp(v1: str, v2: str) -> int:
    return Version(v1).vercmp(v2)


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

    def __iter__(self):
        return (Package(self, entry) for entry in self.sources.values())

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
        return _split_depends(self._get_list_entry('%OPTDEPENDS%'))

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
            if self.name in pkg.optdepends or any(prov in pkg.optdepends for prov in self.provides):
                optionalfor.append(pkg.name)
        return optionalfor

    def compute_requiredby(self) -> List[str]:
        requiredby = []
        for pkgent in self.db.sources.values(): # TODO: somehow check other dbs?
            pkg = Package(self.db, pkgent)
            if self.name in pkg.depends or any(prov in pkg.depends for prov in self.provides):
                # TODO: check version?
                requiredby.append(pkg.name)
        return requiredby


def mingw_db_by_name(name: str) -> Database:
    from urllib.request import urlopen
    from io import BytesIO
    with urlopen('https://mirror.msys2.org/mingw/{0}/{0}.db'.format(name)) as u:
        with BytesIO(u.read()) as f:
            return Database(name, fileobj=f)

def msys_db_by_arch(arch: str='x86_64') -> Database:
    from urllib.request import urlopen
    from io import BytesIO
    with urlopen('https://mirror.msys2.org/msys/{0}/msys.db'.format(arch)) as u:
        with BytesIO(u.read()) as f:
            return Database("msys", fileobj=f)
