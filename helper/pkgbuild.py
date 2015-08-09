import re
import shlex
from collections import defaultdict


def remove_comments(string):
    # from: http://stackoverflow.com/a/18381470
    pattern = r"(\".*?\"|\'.*?\')|(#[^\r\n]*$)"
    regex = re.compile(pattern, re.MULTILINE | re.DOTALL)

    def _replacer(match):
        if match.group(2) is not None:
            return ""
        else:
            return match.group(1)

    return regex.sub(_replacer, string)


def simple_shell_parser(s):
    s = remove_comments(s)
    magic = re.compile(
              "^(\w+)=(\((?:[^)]*|\n*)\)|(?:.*|\n)*)\n", re.M)

    d = {}
    for (key, value) in magic.findall(s):
        key = key.strip()
        value = " ".join(v.strip() for v in value.split('\n') if v.strip())

        if value.startswith("(") and value.endswith(")"):
            try:
                split = shlex.split(value[1:-1])
            except ValueError:
                d[key] = value
            else:
                d[key] = []
                for v in split:
                    d[key].append(v.strip())
        else:
            try:
                shlex.split(value)[0]
            except (ValueError, IndexError):
                pass
            finally:
                d[key] = re.sub(r'^[\'"]|[\'"]$', '', value)

    return d


def replace_shell_vars(string, d):
    if isinstance(string, str):
        s = re.sub(r"\$\{(\w+)[^{}]*\}", r'{\1}', string)
        s = re.sub(r"\$(\w+)", r'{\1}', s)
        dd = defaultdict(lambda: "", d)
        try:
            return s.format(**dd)
        except ValueError:
            return string
    else:
        return [replace_shell_vars(w, d) for w in string]


class PKGSafeParser:
    def __init__(self, filename):
        with open(filename) as fin:
            pass


if __name__ == "__main__":
    import sys
    with open(sys.argv[1]) as fin:
        s = fin.read()

    d = simple_shell_parser(s)
    print(
        replace_shell_vars(d["pkgname"], d),
        replace_shell_vars(d['pkgver'], d),
    )
