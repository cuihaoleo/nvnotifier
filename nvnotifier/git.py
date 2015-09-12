import subprocess
import fnmatch
import os
import datetime


def git_first_commit(repodir):
    cmd = ["git", "-C", repodir, "log", "--reverse", "-1", "--pretty=%h"]
    output = subprocess.check_output(cmd)
    return output.decode("utf8").strip()


def git_latest_committer(path):
    cmd = ["git", "-C", os.path.dirname(path), "log", "-1", 
           "--format=%ce", path]
    try:
        output = subprocess.check_output(cmd)
    except subprocess.CalledProcessError:
        return None
    else:
        return output.strip().decode("utf8")


def git_last_change(path):
    cmd = ["git", "-C", os.path.dirname(path), "log", "-1", 
           "--format=%cd", "--date=raw", path]

    try:
        output = subprocess.check_output(cmd)
        epoch = int(output.split()[0])
    except (subprocess.CalledProcessError, IndexError, ValueError):
        return None
    else:
        return datetime.datetime.fromtimestamp(epoch)


def git_diff_from_head(repodir, commit, filter=None):
    cmd = ["git", "-C", repodir, "diff", "--name-status", commit]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    
    deleted = set() 
    updated = set()
    new = set()
    for line in proc.stdout:
        line = line.strip().decode("utf8")
        status, path = line.split()

        if fnmatch.fnmatch(path, filter):
            if status == "D":
                deleted.add(path)
            elif status == "A":
                new.add(path)
            else:
                updated.add(path)

    if proc.wait() != 0:
        raise subprocess.CalledProcessError 

    return {
        "D": deleted,
        "A": new,
        "M": updated,
    }
