import re
import os
from functools import total_ordering
from nvchecker.get_version import get_version
from helper.pkgbuild import pkgbuild_parser
from abc import ABCMeta, abstractmethod
from tornado.platform.asyncio import AsyncIOMainLoop
from pkg_resources import parse_version
import asyncio

# Tell Tornado to use the asyncio eventloop
AsyncIOMainLoop().install()


class Pac(metaclass=ABCMeta):
    VersionFactory = parse_version

    @abstractmethod
    def __init__(self, name, **kwargs):
        # variables that are safe to be serialized
        self.raw_local_version = kwargs.pop("raw_local_version", None)
        self.raw_remote_version = kwargs.pop("raw_remote_version", None)
        self._info = kwargs
        self._info["name"] = name

        # don't serialize these (though nvconfig should be safe)
        self._on_local_update = []
        self._on_remote_update = []
        self._nvconfig = None
        self.lvpatch = self.rvpatch = lambda p, s: s 

    def __getattr__(self, attr):
        if attr in self._info:
            return self._info[attr]
        else:
            print(self.info)
            raise AttributeError(attr)

    def __str__(self):
        return "%s <LOCAL: %s> <REMOTE: %s>" % \
                (self.name, self.local_version, self.remote_version)

    @abstractmethod
    def update_local(self, runhook=True):
        old_info = self.info
        self.info != old_info and self.on_local_update()

    @asyncio.coroutine
    def async_update_remote(self, runhook=True):
        future = asyncio.Future()

        def cb(name, newver):
            future.set_result(newver is not None)
            if newver is None:
                return

            if newver != self.raw_remote_version:
                self.raw_remote_version = newver
                runhook and self.on_remote_update()

        # ugly work-around to deal with nvchecker vcs handler
        old_cwd = os.getcwd()
        if "path" in self._info:
            os.chdir(os.path.join(os.path.dirname(self.path), ".."))

        try:
            get_version(self.name, self.nvconfig, cb)
        finally:
            os.chdir(old_cwd)

        return future

    @property
    def local_version(self):
        if self.raw_local_version is None:
            return None
        else:
            return self.VersionFactory(
                self.lvpatch(self._info, self.raw_local_version))

    @property
    def remote_version(self):
        if self.raw_remote_version is None:
            return None
        else:
            return self.VersionFactory(
                self.rvpatch(self._info, self.raw_remote_version))

    @property
    def info(self):
        ret = self._info.copy()
        ret.update({
            "name": self.name,
            "raw_local_version": self.raw_local_version,
            "raw_remote_version": self.raw_remote_version,
        })
        return ret

    @property
    def nvconfig(self):
        if self._nvconfig:
            nvconfig = {"oldver": None}
            for k, v in self._nvconfig.items():
                nvconfig[k] = v.format(**self._info) if v is not None else None
            return nvconfig
        else:
            raise AttributeError("Please set nvconfig first!")

    def set_nvconfig(self, config):
        self._nvconfig = config

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


@total_ordering
class PacmanVersion:
    regex = re.compile(r"^(?:(\d+):)?([^:-]*)(?:-([^-]+))?$")

    def __init__(self, s):
        m = self.regex.match(s)
        if not m:
            raise ValueError("Version string cannot be parsed")

        epoch, ver, rel = m.groups()
        self.epoch = int(epoch) if epoch is not None else None
        self.ver = parse_version(ver)
        self.rel = parse_version(rel) if rel else None 

    def __str__(self):
        return "{}:{}-{}".format(self.epoch, self.ver, self.rel)

    def __eq__(self, o):
        v1 = [self.epoch, self.ver, self.rel]
        v2 = [o.epoch, o.ver, o.rel]
        for i in range(3):
            if v1[i] is None or v2[i] is None or v1[i] == v2[i]:
                continue
            else:
                return False
        return True

    def __lt__(self, o):
        v1 = [self.epoch, self.ver, self.rel]
        v2 = [o.epoch, o.ver, o.rel]
        for i in range(3):
            if v1[i] is None or v2[i] is None:
                continue
            elif v1[i] < v2[i]:
                return True
        return False


class PKGBUILDPac(Pac):
    VersionFactory = PacmanVersion

    def __init__(self, path, **kwargs):
        kwargs["path"] = os.path.abspath(path)
        kwargs["name"] = os.path.basename(os.path.dirname(path))
        super(PKGBUILDPac, self).__init__(**kwargs)

    def update_local(self):
        stat = os.stat(self.path)

        if stat != self._info.get("stat"):
            old_info = self.info
            d = pkgbuild_parser(self.path)

            self._info["stat"] = stat
            self._info["packages"] = tuple(d["pkgname"])
            self._info["sources"] = tuple(d.get('source', []))

            epoch = d.get("epoch", 0)
            pkgver = d["pkgver"].split("-")[0]
            pkgrel = d.get("pkgrel", "0")
            self.raw_local_version = "%s:%s-%s" % (epoch, pkgver, pkgrel)

            self.info != old_info and self.on_local_update()
