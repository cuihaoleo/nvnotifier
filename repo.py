from collections import namedtuple
from nvchecker.get_version import get_version
from helper.pkgbuild import pkgbuild_parser
from abc import ABCMeta, abstractmethod
from tornado.platform.asyncio import AsyncIOMainLoop
import asyncio

# Tell Tornado to use the asyncio eventloop
AsyncIOMainLoop().install()

PackageVersion = namedtuple('PackageVersion',
                            ['epoch', 'ver', 'rel'])


class Pac(metaclass=ABCMeta):

    @abstractmethod
    def __init__(self, name, local_version):
        self.name = name
        self.local_version = local_version
        self.remote_version = None
        self._info = {}
        self._on_local_update = []
        self._on_remote_update = []
        self._vpatch = None

    def __getattr__(self, attr):
        if attr in self._info:
            return self._info[attr]
        else:
            raise AttributeError(attr)

    def update_local_version(self, version=None):
        if version is None:
            return
        else:
            if version != self.local_version:
                self.local_version = version
                self.on_local_update()

    @asyncio.coroutine
    def async_update_remote_version(self):
        future = asyncio.Future()

        def cb(name, newver):
            if newver is not None and newver != self.remote_version:
                self.remote_version = newver
                self.on_remote_update()
            future.set_result(newver is not None)

        get_version(self.name, self.nvconfig, cb)
        return future

    def set_nvconfig(self, config):
        pass

    def set_raw_nvconfig(self, raw_config={}):
        self._raw_nvconfig = raw_config

    @property
    def nvconfig(self):
        if self._raw_nvconfig:
            return self._raw_nvconfig
        elif self._nvconfig:
            self._nvconfig.format(
                self._info, name=self.name,
                version=self.local_version)
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
    def patched_local_version(self):
        if self._vpatch is None:
            return self.local_version
        else:
            self._vpatch(self.local_version)

    @property
    def outdated(self):
        rver = self._vpatch(self.remote_version)
        return rver > self.local_version


class PKGBUILDPac(Pac):

    def __init__(self, path):
        d = pkgbuild_parser(path)
        version = PackageVersion(
                    d.get("epoch", 0), d['pkgver'], d.get("pkgrel", 0))

        super(PKGBUILDPac, self).__init__(
            name=d['pkgbase'] if 'pkgbase' in d else d['pkgname'][0],
            local_version=version,
        )

        self._info["path"] = path
        self._info["sources"] = d.get('source', [])
        self._info["packages"] = d.get('pkgname', [])

    def update_local_version(self, version=None):
        if version is None:
            d = pkgbuild_parser(self.path)
            version = PackageVersion(
                          d.get("epoch", 0), d['pkgver'], d.get("pkgrel", 0))
        super(PKGBUILDPac, self).update_local_version(version)

if __name__ == "__main__":
    import sys
    import os

    pacs = []
    for directory in os.listdir(sys.argv[1]):
        pkgbuild = os.path.join(sys.argv[1], directory, "PKGBUILD")
        if os.path.isfile(pkgbuild):
            pac = PKGBUILDPac(pkgbuild)
            pac.set_raw_nvconfig({"aur": None})
            pac.on_remote_update(lambda pac: print(pac.remote_version))
            pacs.append(pac)

    tasks = []
    for pac in pacs:
        task = asyncio.async(pac.async_update_remote_version())
        tasks.append(task)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.wait(tasks))
