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

import nvchecker.lib.nicelogger as nicelogger
from serializer import PickledData
import nvnotifier.repo as repo
from nvnotifier.repo import PKGBUILDPac

try:
    from xdg.BaseDirectory import xdg_cache_home
except ImportError:
    xdg_cache_home = os.path.expanduser("~/.config")

logger = logging.getLogger(__name__)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("tornado").setLevel(logging.WARNING)
logging.getLogger("nvchecker").setLevel(logging.ERROR)
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

    try:
        config.read(configpath)
    except configparser.Error:
        raise argparse.ArgumentTypeError("config invalid")

    rec = SimpleNamespace(
        meta=dict(config["meta"] if "meta" in config.sections() else {}),
        pkg=OrderedDict(), notifier=OrderedDict(),
    )

    for sec in config.sections():
        if ":" in sec:
            ns, value = sec.split(":")
            if hasattr(rec, ns):
                getattr(rec, ns)[value] = dict(config[sec])

    return rec


def all_pkgbuilds(root, blacklist=[]):
    all_path = set()
    pattern_list = [re.compile("^%s$" % p) for p in blacklist]

    for d in os.listdir(root):
        relpath = os.path.join(d, "PKGBUILD")
        abspath = os.path.join(root, relpath)

        if os.path.isfile(abspath):
            if any([p.match(d) for p in pattern_list]):
                logger.debug("%s is in blacklist" % d)
            else:
                all_path.add(abspath)

    return all_path


def init_notifiers(conf, saved):
    notifiers = {} 
    for name, conf in conf.items():
        try:
            mod = import_module("notifier.%s" % name)
            if name in saved:
                n = mod.Notifier(saved=saved[name], **conf)
            else:
                n = mod.Notifier(**conf)
        except Exception as exp:
            logger.error("Failed to initialize Notifier %s" % name)
        else:
            notifiers[name] = n

    return notifiers


def predicate(a, b):
    try:
        if a == b:
            return '='
        elif a > b:
            return '>'
        elif a < b:
            return '<'
    except TypeError:
        return '?'


def main(C):
    cache_file = os.path.join(WORKING_DIR, C.meta["name"] + ".db")
    root = C.meta["root"]

    # load saved session data
    D = SimpleNamespace()
    with PickledData(cache_file, default={}) as pickled:
        D.paclist = pickled.get("paclist", [])
        D.out_of_date = pickled.get("out_of_date", {})
        D.not_ready = pickled.get("not_ready", {})
        D.notifier_data = pickled.get("notifier_data", {})

    paclist = []
    pkgbuilds = all_pkgbuilds(root, C.meta.get("blacklist", "").split('\n'))
    repo.refresh_timestamp()
    for info in filter(lambda e: e["path"] in pkgbuilds, D.paclist):
        pkgbuilds.remove(info["path"])
        pac = PKGBUILDPac(**info)
        paclist.append(pac)

    for path in pkgbuilds:
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
                if "_op" in conf:
                    pac.check_od = getattr(operator, conf["_op"])
                pac.set_nvconfig(conf)

    tasks = []
    for pac in paclist:
        pac.update_local()
        task = asyncio.async(pac.async_update_remote())
        tasks.append(task)

    logger.info("Finished checking local versions.")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.wait(tasks))
    logger.info("Finished checking remote versions.")

    not_ready = {}
    out_of_date = {}
    for pac in paclist:
        lv = pac.local_version
        rv = pac.remote_version
        logger.debug("{name} | {lv} ({raw_local_version}) "
                     "{pred} {rv} ({raw_remote_version})".format(
                     lv=lv, rv=rv, pred=predicate(lv, rv), **pac.info))

        if not pac.version_ready:
            not_ready[pac.name] = D.not_ready.get(pac.name, repo.TIMESTAMP)
            if pac.name in D.out_of_date:
                out_of_date[pac.name] = D.out_of_date[pac.name] 
        elif pac.out_of_date:
            out_of_date[pac.name] = D.out_of_date.get(pac.name, repo.TIMESTAMP)

    with PickledData(cache_file, default={}) as pickled:
        pickled["out_of_date"] = out_of_date
        pickled["not_ready"] = not_ready
        pickled["paclist"] = [pac.info for pac in paclist]

    notifiers = init_notifiers(C.notifier, D.notifier_data)
    for pac in filter(lambda p: p.name in out_of_date, paclist):
        for name, notifier in notifiers.items():
            try:
                notifier.send(pac, out_of_date[pac.name])
            except Exception as exp:
                logger.error("Failed to send notification of %s "
                             "via Notifier %s" % (pac, name))

    notifier_data = D.notifier_data
    for name, notifier in notifiers.items():
        notifier_data[name] = notifier.finish()

    with PickledData(cache_file, default={}) as pickled:
        pickled["notifier_data"] = notifier_data


if __name__ == "__main__":
    import sys
    import argparse

    os.makedirs(WORKING_DIR, exist_ok=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=load_config,
                        help="INI format config file")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="increase output verbosity")

    args = parser.parse_args()
    nicelogger.enable_pretty_logging(
        ["WARNING", "INFO", "DEBUG"][min(args.verbose, 2)])
    main(args.config)
