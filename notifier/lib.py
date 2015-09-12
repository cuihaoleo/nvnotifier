from datetime import timedelta
import re


def convert_timeout_to_second(s):
    r = re.compile("^\s*(?:(\d+)d)?\s*(?:(\d+)h)?\s*"
                   "(?:(\d+)m)?\s*(?:(\d+)s)?\s*$")
    m = r.match(s)

    if m:
        l = [int(e) if e is not None else 0 for e in m.groups()]
        td = timedelta(days=l[0], hours=l[1], minutes=l[2], seconds=l[3])
        return td.total_seconds()
    else:
        raise ValueError("Cannot understand timeout: %s" % s)
