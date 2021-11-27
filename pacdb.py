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
_DEPENDRE = re.compile(r'([^<>=]+)(?:(<=|>=|<|>|=)(.*))?')


class ExtTarFile(tarfile.TarFile):
    """Until Python's tarfile gets zstd support, this class extends it with
       zstd support
    """

    @classmethod
    def zstdopen(cls, name, mode="r", fileobj=None, cctx=None, dctx=None, **kwargs):
        """Open zstd compressed tar archive name for reading or writing.
           Appending is not allowed.
        """
        if mode not in ("r", "w", "x"):
            raise ValueError("mode must be 'r', 'w' or 'x'")

        try:
            from zstandard import ZstdError, open as zstdopen
        except ImportError:
            raise tarfile.CompressionError("zstandard module is not available") from None

        fileobj = zstdopen(fileobj or name, mode+"b", cctx=cctx, dctx=dctx)

        try:
            t = cls.taropen(name, mode, fileobj, **kwargs)
        except (ZstdError, EOFError) as e:
            fileobj.close()
            if mode == 'r':
                raise tarfile.ReadError("not a zstd file") from e
            raise
        except:
            fileobj.close()
            raise
        t._extfileobj = False
        return t

    OPEN_METH = {"zstd": "zstdopen", **tarfile.TarFile.OPEN_METH}


class Version(object):
    ver: Optional[str]
    evr: Optional[Tuple[str, str, Optional[str]]]

    def __init__(self, ver: Union[str, "Version", None]):
        super(Version, self).__init__()
        if isinstance(ver, Version):
            self.ver, self.evr = ver.ver, ver.evr
        elif ver is None:
            self.ver, self.evr = None, None
        else:
            self.ver = ver
            m = re.split(r'(\D)', ver, 1)
            if len(m) == 3 and m[1] in EPOCH_SEPS:
                e = m[0]
                ver = m[2]
            else:
                e = "0"

            r: Optional[str] = None
            rs = ver.rsplit("-", 1)
            if len(rs) == 2:
                ver, r = rs

            self.evr = (e, ver, r)

    def __str__(self):
        return str(self.ver)

    def __repr__(self):
        return f'Version({repr(self.canonicalize())})'

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
    def _parse(cls, v: str) -> Iterator[Tuple[str, _ExtentType]]:
        current = ""
        current_type = cls._OTHER
        for c in v:
            if not current:
                current += c
                current_type = cls._get_type(current)
            else:
                ctype = cls._get_type(c)
                if ctype is current_type:
                    current += c
                else:
                    yield (current, current_type)
                    current, current_type = c, ctype

        if current:
            yield (current, current_type)

    @classmethod
    def _rpmvercmp(cls, v1: str, v2: str) -> int:
        def cmp(a: Any, b: Any) -> int:
            return (a > b) - (a < b)

        for (p1, t1), (p2, t2) in zip_longest(cls._parse(v1), cls._parse(v2), fillvalue=(None, None)):
            if p1 is None:
                if t2 is cls._ALPHA:
                    return 1
                return -1
            elif p2 is None:
                if t1 is cls._ALPHA:
                    return -1
                return 1

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

    def vercmp(self, other: Union["Version", str, None]) -> int:
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

        if self.evr == other.evr:
            return 0
        elif self.evr is None:
            return -1
        elif other.evr is None:
            return 1

        ret = self._rpmvercmp(self.evr[0], other.evr[0])
        if ret == 0:
            ret = self._rpmvercmp(self.evr[1], other.evr[1])
            if ret == 0 and self.evr[2] is not None and other.evr[2] is not None:
                ret = self._rpmvercmp(self.evr[2], other.evr[2])

        return ret

    __cmp__ = vercmp

    def __lt__(self, other):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) < 0

    def __le__(self, other):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) <= 0

    def __eq__(self, other):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) == 0

    def __gt__(self, other):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) > 0

    def __ge__(self, other):
        if not isinstance(other, (str, Version, type(None))):
            return NotImplemented
        return self.vercmp(other) >= 0

    # this should actually be impossible due to type annotations
    if sys.version_info[0] < 3:
        def __ne__(self, other):
            if not isinstance(other, (str, Version, type(None))):
                return NotImplemented
            return not self == other

    def __bool__(self):
        return self.evr is not None

    __nonzero__ = __bool__

    def __hash__(self):
        return hash(self.canonicalize())

    def canonicalize(self, epochsep: str=':') -> Optional[str]:
        if self.evr is None:
            return None

        v = ""
        if self.evr[0] != "0":
            v = self.evr[0].lstrip('0') + epochsep

        for p, t in self._parse(self.evr[1]):
            if t is self._OTHER:
                v += "."
            elif t is self._DIGIT:
                v += (p.lstrip('0') or '0')
            else:
                v += p

        if self.evr[2] is not None:
            v += "-" + (self.evr[2].lstrip('0') or '0')

        return v

def vercmp(v1: str, v2: str) -> int:
    return Version(v1).vercmp(v2)


class DependEntry(namedtuple('DependEntry', ['name', 'mod', 'version_str', 'desc'])):
    _version: Optional[Version]

    @property
    def version(self) -> Optional[Version]:
        if not hasattr(self, '_version'):
            if self.version_str is not None:
                self._version = Version(self.version_str)
            else:
                self._version = None
        return self._version

Depends = Dict[str, Set[DependEntry]]

def _split_depends(deps: List[str]) -> Depends:
    r: Depends = {}
    for d in deps:
        e = d.rsplit(': ', 1)
        desc = e[1] if len(e) > 1 else None
        entry = DependEntry(*_DEPENDRE.fullmatch(e[0]).groups(), desc) # type: ignore
        r.setdefault(entry.name, set()).add(entry)
    return r


class Database(object):
    def __init__(self, name: str, filename=None, fileobj=None):
        super(Database, self).__init__()
        self.name = name
        self.url: Optional[str] = None
        self.byname: Dict[str, _PackageEntry] = {}
        packages: Dict[str, List[Tuple[str, bytes]]] = {}
        # Unfortunately, tarfile doesn't provide exensiblity for transparent
        # decompression in the |* mode, so use :* here (and require seekable
        # fileobjs)
        with ExtTarFile.open(name=filename, fileobj=fileobj, mode="r:*") as tar:
            for info in tar:
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
            self.byname[desc['%NAME%'][0]] = desc

    @classmethod
    def from_url(cls, name: str, url: str, dbtype: str="db") -> "Database":
        from urllib.request import urlopen
        from io import BytesIO
        if url[-1] != '/':
            url += '/'
        base_url = url
        url += ".".join((name, dbtype))
        with urlopen(url) as f, \
             BytesIO(f.read()) as b:
            db = cls(name, fileobj=b)
        db.url = base_url
        return db

    def get_pkg(self, pkgname: str) -> Optional["Package"]:
        entry = self.byname.get(pkgname)
        if entry is not None:
            return Package(self, entry)
        return None

    def __iter__(self) -> Iterator["Package"]:
        return (Package(self, entry) for entry in self.byname.values())

    def __contains__(self, pkg_or_name: Union[str, "Package"]) -> bool:
        if isinstance(pkg_or_name, Package):
            return pkg_or_name.name in self.byname
        else:
            return pkg_or_name in self.byname

    def __repr__(self) -> str:
        return super(Database, self).__repr__()[:-1] + f": {self.name}>"

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

    def __str__(self) -> str:
        return "-".join((self.name, str(self.version)))

    def __repr__(self) -> str:
        return super(Package, self).__repr__()[:-1] + f": {str(self)} from {str(self.db)}>"

    def __eq__(self, other) -> bool:
        if isinstance(other, Package):
            return self.name == other.name and self.version == other.version
        return NotImplemented

    def __lt__(self, other) -> bool:
        if isinstance(other, Package):
            return (self.name, self.version) < (other.name, other.version)
        return NotImplemented

    def __le__(self, other) -> bool:
        if isinstance(other, Package):
            return (self.name, self.version) <= (other.name, other.version)
        return NotImplemented

    def __gt__(self, other) -> bool:
        if isinstance(other, Package):
            return (self.name, self.version) > (other.name, other.version)
        return NotImplemented

    def __ge__(self, other) -> bool:
        if isinstance(other, Package):
            return (self.name, self.version) >= (other.name, other.version)
        return NotImplemented

    # this should actually be impossible due to type annotations
    if sys.version_info[0] < 3:
        def __ne__(self, other):
            if isinstance(other, Package):
                return not self == other
            return NotImplemented

    def __hash__(self):
        return hash((self.name, self.version))

    def _get_list_entry(self, name: str) -> List[str]:
        return self._entry.get(name, list())

    def _get_single_entry(self, name: str) -> Optional[str]:
        return self._entry.get(name, (None,))[0]

    @property
    def arch(self) -> Optional[str]:
        return self._get_single_entry('%ARCH%')

    @property
    def base(self) -> Optional[str]:
        return self._get_single_entry('%BASE%')

    @property
    def base64_sig(self) -> Optional[str]:
        return self._get_single_entry('%PGPSIG%')

    @property
    def builddate(self) -> Optional[datetime.datetime]:
        d = self._get_single_entry('%BUILDDATE%')
        if d is not None:
            return datetime.datetime.utcfromtimestamp(int(d))
        return None

    @property
    def checkdepends(self) -> Depends:
        return _split_depends(self._get_list_entry('%CHECKDEPENDS%'))

    @property
    def conflicts(self) -> Depends:
        return _split_depends(self._get_list_entry('%CONFLICTS%'))

    @property
    def depends(self) -> Depends:
        return _split_depends(self._get_list_entry('%DEPENDS%'))

    @property
    def desc(self) -> Optional[str]:
        return self._get_single_entry('%DESC%')

    @property
    def download_size(self) -> Optional[int]:
        d = self._get_single_entry('%CSIZE%')
        if d is not None:
            return int(d)
        return None

    @property
    def filename(self) -> str:
        return self._entry['%FILENAME%'][0]

    @property
    def files(self) -> List[str]:
        return self._get_list_entry('%FILES%')

    @property
    def groups(self) -> List[str]:
        return self._get_list_entry('%GROUPS%')

    @property
    def isize(self) -> Optional[int]:
        d = self._get_single_entry('%ISIZE%')
        if d is not None:
            return int(d)
        return None

    @property
    def licenses(self) -> List[str]:
        return self._get_list_entry('%LICENSE%')

    @property
    def makedepends(self) -> Depends:
        return _split_depends(self._get_list_entry('%MAKEDEPENDS%'))

    @property
    def md5sum(self) -> Optional[str]:
        return self._get_single_entry('%MD5SUM%')

    @property
    def name(self) -> str:
        return self._entry['%NAME%'][0]

    @property
    def optdepends(self) -> Depends:
        return _split_depends(self._get_list_entry('%OPTDEPENDS%'))

    @property
    def packager(self) -> Optional[str]:
        return self._get_single_entry('%PACKAGER%')

    @property
    def provides(self) -> Depends:
        return _split_depends(self._get_list_entry('%PROVIDES%'))

    @property
    def replaces(self) -> Depends:
        return _split_depends(self._get_list_entry('%REPLACES%'))

    @property
    def sha256sum(self) -> Optional[str]:
        return self._get_single_entry('%SHA256SUM%')

    size = download_size

    @property
    def url(self) -> Optional[str]:
        return self._get_single_entry('%URL%')

    @property
    def version(self) -> Version:
        return Version(self._entry['%VERSION%'][0])

    def compute_rdepends(self, dependattr: str='depends') -> List[str]:
        ret: List[str] = []
        provs = self.provides.keys()
        for pkg in self.db: # TODO: somehow check other dbs?
            deps = getattr(pkg, dependattr) # type: Depends
            if self.name in deps or not provs.isdisjoint(deps.keys()): # pylint: disable=no-member
                # TODO: check version?
                ret.append(pkg.name)
        return ret

    def compute_optionalfor(self) -> List[str]:
        return self.compute_rdepends('optdepends')

    def compute_requiredby(self) -> List[str]:
        return self.compute_rdepends('depends')


def mingw_db_by_name(name: str, dbtype: str="db") -> Database:
    return Database.from_url(name, 'https://mirror.msys2.org/mingw/{}'.format(name), dbtype)

def msys_db_by_arch(arch: str='x86_64', dbtype: str="db") -> Database:
    return Database.from_url('msys', 'https://mirror.msys2.org/msys/{}'.format(arch), dbtype)
