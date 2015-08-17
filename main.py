#!/usr/bin/env python3

import re
import asyncio
import os
import configparser
import fnmatch
from serializer import PickledData
from repo import PKGBUILDPac

try:
    from xdg.BaseDirectory import xdg_cache_home
except ImportError:
    xdg_cache_home = os.path.expanduser("~/.config")

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


# replace this function later
def on_up(pac):
    if pac.remote_version > pac.local_version:
        c = "!"
    elif pac.remote_version < pac.local_version:
        c = "?"
    else:
        c = "="
    print("%c %s (%s -> %s)" %
          (c, pac.name, pac.local_version, pac.remote_version))


def main(configpath):
    config = configparser.ConfigParser()
    config.read(configpath)

    meta = config["__meta__"]

    cache_file = os.path.join(WORKING_DIR, meta["name"] + ".db")
    root = meta["root"]
    blacklist = meta.get("blacklist", "").split("\n")

    with PickledData(cache_file, default={}) as D:
        saved = D.get("paclist", [])

    if "__default__" in config:
        default_nvconfig = dict(config["__default__"])
    else:
        default_nvconfig = None

    all_path = set()
    for d in os.listdir(root):
        relpath = os.path.join(d, "PKGBUILD")
        abspath = os.path.join(root, relpath)

        if os.path.isfile(abspath) and \
           not any([fnmatch.fnmatch(relpath, pat) for pat in blacklist]):
            all_path.add(abspath)

    paclist = []
    for info in saved:
        if info["path"] in all_path:
            all_path.remove(info["path"])
            pac = PKGBUILDPac(**info)
            pac.set_nvconfig(default_nvconfig)
            paclist.append(pac)

    for path in all_path:
        pac = PKGBUILDPac(path)
        pac.set_nvconfig(default_nvconfig)
        paclist.append(pac)

    for secname in config.sections():
        section = config[secname]

        regex = re.compile("^" + secname + "$")
        nvconfig = {
            k: section[k] for k in section if not k.startswith("_")}

        for pac in paclist:
            if regex.match(pac.name):
                pac.set_nvconfig(nvconfig)

                if "_lvpatch" in section:
                    arg = section["_lvpatch"].split("\n")
                    pac.lvpatch = version_patch_factory(*arg)
                if "_rvpatch" in section:
                    arg = section["_rvpatch"].split("\n")
                    pac.rvpatch = version_patch_factory(*arg)

    tasks = []
    for pac in paclist:
        pac.update_local()
        pac.on_remote_update(on_up)
        task = asyncio.async(pac.async_update_remote())
        tasks.append(task)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.wait(tasks))

    with PickledData(cache_file, default={}) as D:
        D["paclist"] = [pac.info for pac in paclist]

if __name__ == "__main__":
    import sys
    os.makedirs(WORKING_DIR, exist_ok=True)
    main(sys.argv[1])
