#!/usr/bin/env python3

import re
import asyncio
import os
import configparser
import fnmatch
import time
import operator
import logging
from collections import OrderedDict
from types import SimpleNamespace

import nicelogger
from serializer import PickledData
from repo import PKGBUILDPac

try:
    from xdg.BaseDirectory import xdg_cache_home
except ImportError:
    xdg_cache_home = os.path.expanduser("~/.config")

logger = logging.getLogger(__name__)
WORKING_DIR = os.path.join(xdg_cache_home, "nvnotifier")


def version_patch_factory(regex_str, patch=None):
    if patch is None:
        patch = regex_str
        regex_str = r".*"

    def func(pac, version):
        regex = re.compile(regex_str)
        match = regex.match(version)
        ret = patch.format(**pac)

        ret = ret.replace("$0", version)
        for i, g in enumerate(match.groups()):
            ret = ret.replace("$%d" % (i+1), g)

        return ret

    return func


def load_config(configpath):
    config = configparser.ConfigParser()
    config.read(configpath)

    rec = SimpleNamespace(
        meta=dict(config["meta"]),
        pkg=OrderedDict(),
        notifier=OrderedDict(),
    )

    for sec in config.sections():
        if ":" in sec:
            ns, value = sec.split(":")
            if hasattr(rec, ns):
                getattr(rec, ns)[value] = dict(config[sec])

    return rec


def main(configpath):
    C = load_config(configpath)

    cache_file = os.path.join(WORKING_DIR, C.meta["name"] + ".db")
    root = C.meta["root"]
    blacklist = C.meta.get("blacklist", "").split("\n")

    with PickledData(cache_file, default={}) as pickled:
        saved = pickled.get("paclist", [])
        toooonew = pickled.get("toooonew", {})
        outdated = pickled.get("outdated", {})

    def on_local_update(pac):
        if pac.name in outdated:
            del outdated[pac.name]

    def on_remote_update(pac):
        op = getattr(operator, pac.nvconfig.get("_op", "lt"))
        if op(pac.remote_version, pac.local_version):
            outdated[pac.name] = int(time.time())

    all_path = set()
    for d in os.listdir(root):
        relpath = os.path.join(d, "PKGBUILD")
        abspath = os.path.join(root, relpath)

        if os.path.isfile(abspath) and \
           not any([fnmatch.fnmatch(relpath, pat) for pat in blacklist]):
            all_path.add(abspath)

    paclist = []
    for info in filter(lambda e: e["path"] in all_path, saved):
        all_path.remove(info["path"])
        pac = PKGBUILDPac(**info)
        paclist.append(pac)

    for path in all_path:
        pac = PKGBUILDPac(path)
        paclist.append(pac)

    for pattern, conf in C.pkg.items():
        regex = re.compile("^" + pattern + "$")
        for pac in paclist:
            if regex.match(pac.name):
                nvconfig = conf.copy()
                if "_lvpatch" in conf:
                    arg = nvconfig.pop("_lvpatch").split("\n")
                    pac.lvpatch = version_patch_factory(*arg)
                if "_rvpatch" in conf:
                    arg = nvconfig.pop("_rvpatch").split("\n")
                    pac.rvpatch = version_patch_factory(*arg)
                pac.set_nvconfig(conf)

    tasks = []
    for pac in paclist:
        pac.on_local_update(on_local_update)
        pac.on_remote_update(on_remote_update)
        pac.update_local()
        task = asyncio.async(pac.async_update_remote())
        tasks.append(task)

    logger.info("Finished checking local versions.")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.wait(tasks))
    logger.info("Finished checking remote versions.")

    now = int(time.time())
    for pac in paclist:
        if pac.name in outdated:
            print("{name} outdated for {time} hrs "
                  "(L: {lv}, R: {rv})".format(
                    name=pac.name,
                    time=(now-outdated[pac.name]) // 3600,
                    lv=pac.local_version, rv=pac.remote_version))

    with PickledData(cache_file, default={}) as D:
        D["paclist"] = [pac.info for pac in paclist]
        D["outdated"] = outdated


if __name__ == "__main__":
    import sys
    nicelogger.enable_pretty_logging("INFO")
    os.makedirs(WORKING_DIR, exist_ok=True)
    main(sys.argv[1])
