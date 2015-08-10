import re
import shlex
import subprocess
import os
from collections import defaultdict

BASEDIR = os.path.dirname(os.path.abspath(__file__))


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


def shell_safe_parser(path):
    with open(sys.argv[1]) as fin:
        s = fin.read()

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
                d[key] = replace_shell_vars(value, d)
            else:
                d[key] = []
                for v in split:
                    d[key].append(replace_shell_vars(v.strip(), d))
        else:
            try:
                shlex.split(value)[0]
            except (ValueError, IndexError):
                pass
            finally:
                value = re.sub(r'^[\'"]|[\'"]$', '', value)
                d[key] = replace_shell_vars(value, d)

    return d


def shell_nosafe_parser(path):
    script = os.path.join(BASEDIR, "pkgbuild_reader.sh")
    p = subprocess.Popen(["bash", script, path],
                         stdout=subprocess.PIPE,
                         universal_newlines=True)
    if p.wait() != 0:
        return {}

    last_is_blank = True
    d = {}
    key = None
    array = False

    for line in p.stdout:
        line = line.strip()
        if line == "":
            last_is_blank = True
        elif last_is_blank and line.startswith("<") and line.endswith(">"):
            key = line[1:-1]
            array = False
        elif last_is_blank and line.startswith("[") and line.endswith("]"):
            key = line[1:-1]
            array = True
            d[key] = []
        else:
            if array:
                d[key].append(line)
            elif key not in d:
                d[key] = line

    return d


def pkgbuild_parser(path, safe=False):
    accept_list = ["pkgbase" "pkgname", "source"]
    accept_str = ["epoch", "pkgver", "pkgrel", "source"]

    if safe:
        d = shell_safe_parser(path)
    else:
        d = shell_nosafe_parser(path)
        if not d:
            d = shell_safe_parser(path)

    ret = {}
    for key in d:
        if key in accept_list:
            if isinstance(d[key], list):
                ret[key] = [str(elem) for elem in d[key]]
            elif isinstance(d[key], str):
                ret[key] = [d[key]]
            else:
                ret[key] = []
        elif key in accept_str:
            ret[key] = d[key] if isinstance(d[key], str) else ""

    return ret


if __name__ == "__main__":
    import sys
    d = pkgbuild_parser(sys.argv[1])
    print(d)
