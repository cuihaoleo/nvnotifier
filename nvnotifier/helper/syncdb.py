import tarfile
import os


class SyncDB:
    def __init__(self, filename):
        self.pkgs = {}

        with tarfile.open(filename) as tar:
            for mem in tar.getmembers():
                if not mem.isfile() or \
                   not os.path.basename(mem.name) == "desc":
                    continue

                d = {}
                with tar.extractfile(mem) as fin:
                    ready, key = True, ""
                    for l in fin:
                        l = l.decode("utf8")
                        if l.strip() == "":
                            ready = True
                        elif ready and l.startswith("%"):
                            key = l.strip("\n %")
                            d[key] = []
                            ready = False
                        elif not ready:
                            d[key].append(l[:-1])

                if len(d.get("NAME", [])) == 1:
                    self.pkgs[d["NAME"][0]] = dict((k, "\n".join(d[k]))
                                                   for k in d)
