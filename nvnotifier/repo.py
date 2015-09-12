import re
import os
from functools import total_ordering
from nvchecker.get_version import get_version
from abc import ABCMeta, abstractmethod
from tornado.platform.asyncio import AsyncIOMainLoop
from tornado.stack_context import ExceptionStackContext
from pkg_resources import parse_version
from .helper.pkgbuild import pkgbuild_parser
from .git import git_last_change
import datetime
import asyncio
import operator
import logging


# Tell Tornado to use the asyncio eventloop
AsyncIOMainLoop().install()

TIMESTAMP = datetime.datetime.now()
logger = logging.getLogger(__name__)


def refresh_timestamp():
    global TIMESTAMP
    TIMESTAMP = datetime.datetime.now()


class Pac(metaclass=ABCMeta):
    VersionFactory = parse_version

    @abstractmethod
    def __init__(self, name, **kwargs):
        # variables that are safe to be serialized
        self.raw_local_version = kwargs.pop("raw_local_version", None)
        self.raw_remote_version = kwargs.pop("raw_remote_version", None)

        self._info = kwargs
        self._info.update({
            "name": name,
            "local_timestamp": TIMESTAMP,
            "remote_timestamp": TIMESTAMP,
        })

        # don't serialize these (though nvconfig should be safe)
        self._on_local_update = []
        self._on_remote_update = []
        self._nvconfig = None
        self.lvpatch = self.rvpatch = lambda p, s: s
        self.check_od = operator.lt

    def __getattr__(self, attr):
        if attr in self._info:
            return self._info[attr]
        else:
            raise AttributeError(attr)

    def __str__(self):
        return "%s <L: %s> <R: %s>" % \
                (self.name, self.local_version, self.remote_version)

    @abstractmethod
    def update_local(self):
        old_info = self.info
        if self.info != old_info:
            self.on_local_update()

    @asyncio.coroutine
    def async_update_remote(self):
        future = asyncio.Future()

        def handle_exception(type, value, traceback):
            future.set_result(False)
            logger.error("nvchecker failed to get version of %s", self)
            raise value.with_traceback(traceback)

        def cb(name, newver):
            future.set_result(newver is not None)

            if newver is None:
                logger.error("nvchecker failed to get version of %s", self)
            elif newver != self.raw_remote_version:
                self.raw_remote_version = newver
                self.on_remote_update()

        # ugly work-around to deal with nvchecker vcs handler
        old_cwd = os.getcwd()
        if "path" in self._info:
            os.chdir(os.path.join(os.path.dirname(self.path), ".."))

        try:
            with ExceptionStackContext(handle_exception):
                get_version(self.name, self.nvconfig, cb)
        finally:
            os.chdir(old_cwd)

        return future

    @property
    def local_version(self):
        if self.raw_local_version is None:
            return None
        else:
            if not self.lvpatch:
                self.lvpatch = lambda p, s: s
            patched = self.lvpatch(self._info, self.raw_local_version)
        return self.VersionFactory(patched) if patched is not None else None

    @property
    def remote_version(self):
        if self.raw_remote_version is None:
            return None
        else:
            if not self.rvpatch:
                self.rvpatch = lambda p, s: s
            patched = self.rvpatch(self._info, self.raw_remote_version)
        return self.VersionFactory(patched) if patched is not None else None

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

    @property
    def version_ready(self):
        return bool(self.local_version and self.remote_version)

    @property
    def out_of_date(self):
        if self.check_od is None:
            self.check_od = operator.lt
        return bool(self.check_od(self.local_version, self.remote_version))

    def set_nvconfig(self, config):
        self._nvconfig = config

    def on_local_update(self, func=None):
        if func:
            self._on_local_update.append(func)
        else:
            logger.info("%s triggers on_local_update", self)
            self._info["local_timestamp"] = TIMESTAMP
            for f in self._on_local_update:
                f(self)

    def on_remote_update(self, func=None):
        if func:
            self._on_remote_update.append(func)
        else:
            self._info["remote_timestamp"] = TIMESTAMP
            logger.info("%s triggers on_remote_update", self)
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
        return "{}:{}-{}".format(self.epoch or '*', self.ver, self.rel or '*')

    def __eq__(self, o):
        if o is None:
            raise TypeError("")

        v1 = [self.epoch, self.ver, self.rel]
        v2 = [o.epoch, o.ver, o.rel]
        for i in range(3):
            if v1[i] is None or v2[i] is None or v1[i] == v2[i]:
                continue
            else:
                return False
        return True

    def __lt__(self, o):
        if o is None:
            raise TypeError("")

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
        super().__init__(**kwargs)

    def update_local(self):
        mtime = git_last_change(self.path)
        if mtime is None:
            stat = os.stat(self.path)
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime)

        if mtime != self._info.get("mtime"):
            old_info = self.info
            d = pkgbuild_parser(self.path)

            self._info["mtime"] = mtime
            self._info["packages"] = tuple(d["pkgname"])
            self._info["sources"] = tuple(d.get('source', []))

            epoch = d.get("epoch", 0)
            pkgver = d["pkgver"].split("-")[0]
            pkgrel = d.get("pkgrel", "0")
            self.raw_local_version = "%s:%s-%s" % (epoch, pkgver, pkgrel)

            self.info != old_info and self.on_local_update()
