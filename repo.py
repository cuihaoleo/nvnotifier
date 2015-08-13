import re
from functools import total_ordering
from collections import namedtuple
from nvchecker.get_version import get_version
from helper.pkgbuild import pkgbuild_parser
from abc import ABCMeta, abstractmethod
from tornado.platform.asyncio import AsyncIOMainLoop
from pkg_resources import parse_version
import asyncio

# Tell Tornado to use the asyncio eventloop
AsyncIOMainLoop().install()

PackageVersion = namedtuple('PackageVersion',
                            ['epoch', 'ver', 'rel'])


class Pac(metaclass=ABCMeta):
    VersionFactory = parse_version

    @abstractmethod
    def __init__(self, name):
        self.name = name
        self.local_version = None
        self.remote_version = None
        self._info = {}
        self._on_local_update = []
        self._on_remote_update = []
        self._vpatch = None
        self._nvconfig = self._raw_nvconfig = None

    def __getattr__(self, attr):
        if attr in self._info:
            return self._info[attr]
        else:
            raise AttributeError(attr)

    def update_local_version(self, version):
        if isinstance(version, str):
            version = self.VersionFactory(version)

        if self.local_version is None or version != self.local_version:
            self.local_version = version
            self.on_local_update()

    @asyncio.coroutine
    def async_update_remote_version(self):
        future = asyncio.Future()

        def cb(name, newver):
            future.set_result(newver is not None)
            if newver is None:
                return

            if self._vpatch:
                newver = self._vpatch(self, newver)

            if isinstance(newver, str):
                newver = self.VersionFactory(newver)

            if self.remote_version is None or newver != self.remote_version:
                self.remote_version = newver
                self.on_remote_update()

        get_version(self.name, self.nvconfig, cb)
        return future

    def set_nvconfig(self, config):
        self._nvconfig = config

    def set_raw_nvconfig(self, raw_config={}):
        self._raw_nvconfig = raw_config

    @property
    def info(self):
        ret = self._info.copy()
        ret.update({
            "name": self.name,
            "local_version": str(self.local_version),
            "remote_version": str(self.remote_version),
        })
        return ret

    @property
    def nvconfig(self):
        if self._raw_nvconfig:
            return self._raw_nvconfig
        elif self._nvconfig:
            nvconfig = {}
            for k, v in self._nvconfig.items():
                nvconfig[k] = v.format(**self.info)
            return nvconfig
        else:
            raise AttributeError("Please set nvconfig first!")

    def on_local_update(self, func=None):
        if func:
            self._on_local_update.append(func)
        else:
            for f in self._on_local_update:
                f(self)

    def on_remote_update(self, func=None):
        if func:
            self._on_remote_update.append(func)
        else:
            for f in self._on_remote_update:
                f(self)

    def apply_version_patch(self, patch):
        self._vpatch = patch

    @property
    def outdated(self):
        rver = self._vpatch(self, self.remote_version)
        return rver > self.local_version


@total_ordering
class PacmanVersion:
    regex = re.compile(r"^(?:(\d+):)?([^:-]*)(?:-([^-]+))?$")

    def __init__(self, s):
        m = self.regex.match(s)
        if not m:
            raise ValueError("Version string cannot be parsed")

        epoch, ver, rel = m.groups()
        self.epoch = int(epoch) if epoch else 0
        self.ver = parse_version(ver)
        self.rel = parse_version(rel if rel is not None else "0")

    def __str__(self):
        return "{}:{}-{}".format(self.epoch, self.ver, self.rel)

    def __eq__(self, other):
        return (self.epoch, self.ver, self.rel) == \
               (other.epoch, other.ver, other.rel)

    def __lt__(self, other):
        return (self.epoch, self.ver, self.rel) < \
               (other.epoch, other.ver, other.rel)


class PKGBUILDPac(Pac):
    VersionFactory = PacmanVersion

    def __init__(self, path):
        d = pkgbuild_parser(path)

        super(PKGBUILDPac, self).__init__(
            name=d['pkgbase'] if 'pkgbase' in d else d['pkgname'][0])

        self._info["path"] = path
        self._info["sources"] = d.get('source', [])
        self._info["packages"] = d.get('pkgname', [])

    def update_local_version(self, version=None):
        if version is None:
            d = pkgbuild_parser(self.path)

            epoch = d.get("epoch", 0)
            pkgver = d["pkgver"].split("-")[0]
            pkgrel = d.get("pkgrel", "0")

            version = self.VersionFactory("%s:%s-%s" % (epoch, pkgver, pkgrel))

        super(PKGBUILDPac, self).update_local_version(version)


if __name__ == "__main__":
    import sys
    import os

    def on_up(pac):
        if pac.remote_version > pac.local_version:
            print("! " + pac.name)
        else:
            print("= " + pac.name)

    def dummy_patch(pac, ver):
        print("I got ver {} from pac {}.".format(pac.name, ver))
        return ver

    pacs = []
    for directory in os.listdir(sys.argv[1]):
        pkgbuild = os.path.join(sys.argv[1], directory, "PKGBUILD")
        if os.path.isfile(pkgbuild):
            pac = PKGBUILDPac(pkgbuild)
            pac.apply_version_patch(dummy_patch)
            pac.set_raw_nvconfig({"aur": None})
            pac.update_local_version()
            pac.on_remote_update(on_up)
            pacs.append(pac)

    tasks = []
    for pac in pacs:
        task = asyncio.async(pac.async_update_remote_version())
        tasks.append(task)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.wait(tasks))
