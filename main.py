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
from importlib import import_module

import nicelogger
from serializer import PickledData
from nvnotifier.repo import PKGBUILDPac

try:
    from xdg.BaseDirectory import xdg_cache_home
except ImportError:
    xdg_cache_home = os.path.expanduser("~/.config")

logger = logging.getLogger(__name__)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("tornado").setLevel(logging.WARNING)
WORKING_DIR = os.path.join(xdg_cache_home, "nvnotifier")


def version_patch_factory(regex_str, patch=None):
    if patch is None:
        patch = regex_str
        regex_str = r".*"

    def func(pacinfo, version):
        ret = patch.format(**pacinfo)
        regex = re.compile(regex_str)
        match = regex.match(version)

        if not match:
            logger.error("Failed to patch version for %s" % pacinfo["name"])
            return None

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

    nicelogger.enable_pretty_logging(C.meta.get("log", "INFO").upper())
    cache_file = os.path.join(WORKING_DIR, C.meta["name"] + ".db")
    root = C.meta["root"]
    blacklist = [re.compile("^"+s+"$") \
                 for s in C.meta.get("blacklist", "").split("\n")]

    with PickledData(cache_file, default={}) as pickled:
        saved = pickled.get("paclist", [])
        outdated = pickled.get("outdated", {})
        notifier_data = pickled.get("notifier_data", {})

    def on_local_update(pac):
        lv = pac.local_version
        rv = pac.remote_version
        op = getattr(operator, pac.nvconfig.get("_op", "lt"))
        if rv is None or lv is None or not op(rv, lv):
            outdated.pop(pac.name, None)

    def on_remote_update(pac):
        lv = pac.local_version
        rv = pac.remote_version
        if lv is not None and rv is not None:
            op = getattr(operator, pac.nvconfig.get("_op", "lt"))
            if op(rv, lv):
                outdated[pac.name] = int(time.time())

    all_path = set()
    for d in os.listdir(root):
        relpath = os.path.join(d, "PKGBUILD")
        abspath = os.path.join(root, relpath)

        if os.path.isfile(abspath):
            if any([p.match(d) for p in blacklist]):
                logger.debug("%s is in blacklist" % d)
            else:
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

    with PickledData(cache_file, default={}) as D:
        D["outdated"] = outdated
        D["paclist"] = [pac.info for pac in paclist]

    notifiers = {} 
    for name, conf in C.notifier.items():
        mod = import_module("notifier.%s" % name)
        if name in notifier_data:
            n = mod.Notifier(saved=notifier_data[name], **conf)
        else:
            n = mod.Notifier(**conf)
        notifiers[name] = n

    for pac in filter(lambda p: p.name in outdated, paclist):
        for notifier in notifiers.values():
            notifier.send(pac, outdated[pac.name])

    for name, notifier in notifiers.items():
        notifier_data[name] = notifier.finish()

    with PickledData(cache_file, default={}) as D:
        D["notifier_data"] = notifier_data


if __name__ == "__main__":
    import sys
    os.makedirs(WORKING_DIR, exist_ok=True)
    main(sys.argv[1])
