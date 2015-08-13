#!/usr/bin/env python3

import re
import asyncio
import os
import configparser
import repo

try:
    from xdg.BaseDirectory import xdg_cache_home
except ImportError:
    xdg_cache_home = os.path.expanduser("~/.config")

WORKING_DIR = os.path.join(xdg_cache_home, "nvnotifier") 


def version_patch_factory(regex_str, patch):
    def func(pac, version):
        regex = re.compile(regex_str)
        match = regex.match(version)
        ret = patch.format(**pac.info)

        ret = ret.replace("$0", version)
        for i, g in enumerate(match.groups()):
            ret = ret.replace("$%d" % (i+1), g)

        if ":" not in patch:
            ret = "%d:" % getattr(pac.local_version, "epoch", 0) + ret
        if "-" not in patch:
            ret += "-%s" % getattr(pac.local_version, "rel", "0")

        return ret

    return func


def main(configpath):
    config = configparser.ConfigParser()
    config.read(configpath)

    meta = config["__meta__"]
    cache_file = os.path.join(WORKING_DIR, meta["name"])
    root = meta["root"]
    

    paclist = []
    for d in os.listdir(root):
        dpath = os.path.join(root, d)
        ppath = os.path.join(dpath, "PKGBUILD")
        if os.path.isfile(ppath):
            pac = repo.PKGBUILDPac(ppath)
            paclist.append(pac)

    for secname in config.sections():
        section = config[secname]

        if ":" not in secname:
            continue

        skey, svalue = secname.split(":", 1) 
        regex = re.compile("^" + svalue + "$")
        raw_nvconfig = {
            k: section[k] for k in section if not k.startswith("_")}

        for pac in paclist:
            if regex.match(getattr(pac, skey)):
                pac.set_raw_nvconfig(raw_nvconfig)
                if "_vpatch" in section:
                    arg = section["_vpatch"].split("\n")
                    pac.apply_version_patch(version_patch_factory(*arg))

    if "__default__" in config:
        default_nvconfig = dict(config["__default__"])
        for pac in paclist:
            pac.set_nvconfig(default_nvconfig)

    def on_up(pac):
        if pac.remote_version > pac.local_version:
            c = "!"
        elif pac.remote_version < pac.local_version:
            c = "?"
        else:
            c = "="
        print("%c %s (%s -> %s)" % \
              (c, pac.name, pac.local_version, pac.remote_version))

    tasks = []
    for pac in paclist:
        pac.update_local_version()
        pac.on_remote_update(on_up)
        task = asyncio.async(pac.async_update_remote_version())
        tasks.append(task)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.wait(tasks))


if __name__ == "__main__":
    import sys
    os.makedirs(WORKING_DIR, exist_ok=True)
    main(sys.argv[1])
