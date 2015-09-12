# nvnotifier

**nvnotifer** is a wrapper of [nvchecker](https://github.com/lilydjwg/nvchecker). The script reads version from local PKGBUILDs and compares it with upstream versions, then report out-of-date via various notifiers (such as Email or GitHub issue).

I try to make it easy to extend the script. Writing new notifier should be easy. You can even write new subclasses of Pac to make it work with other package systems.

## 一言以概

Forgive my poor English.

诶，文档很难看的。直接看 ```examples/``` 目录里的配置文件示例吧，给 Arch 中文社区源用的。

程序有些复杂，为了避免出现 BUG 刷别人的邮箱/Repo，最好自己开个不管用的 SMTP 服务器和没用的 GitHub repo 测试一下。

## Dependency

* Python 3.4+
* python-requests
* nvchecker
* bash

## Running

Currently the script isn't well packaged. Just download and run it.

```
$ ./main.py -h
usage: main.py [-h] [-v] config

positional arguments:
  config         INI format config file

optional arguments:
  -h, --help     show this help message and exit
  -v, --verbose  increase output verbosity
```

Set up your PKGBUILD repository. Write a config file for it. And run:
```
$ ./main.py config.ini
```

## PKGBUILD Repository

Your repository should have such a structure:
```
reporoot/
├── 115wangpan
│   ├── ...
│   └── PKGBUILD
├── acpi_call-pf
│   ├── ...
│   └── PKGBUILD
├── ...
├── ...
```

i.e, a PKGBUILD inside a subdir.

## Version Checking Mechanism

Local PKGBUILD version is from PKGBUILD. The format is always a pacman package version (```epoch:pkgver-pkgrel```). If epoch is not set, default to 0 (int). If pkgrel is not set, default to '0' (str).

Remote version is fetched by nvchecker.

Usually you cannot compare two version directly. I design a version patch mechanism, so you can modify the two version string to the same format. See **_lvpatch** and **_rvpatch** setting in the config file.

You may use part of raw version string or other PKGBUILD infomations to replace the version string. The final version string should be a pacman package version as well. But you may ignore epoch and pkgrel. If ignored, this part won't be compared (for example, *1.2.3* == *1:1.2.3-4*).


## Repository Config File

Repository config file is in INI format. There are some amazing config examples in ```examples/``` directory.

### meta section

Some global config for the script.

* **name** (required)

A name to identify this repository. Please make it unique.

* **root** (required)

The relative path to the PKGBUILD repository (relative to this config file).

* **blacklist** (optional, default="")

Multiple lines of regex. If the name of PKGBUILD's parent directory (this is assigned as the PKGBUILD's name) match any regex, it will be ignored by the script.

### notifier:*name* section

The *name* notifier will be enabled for out-of-date package notificaion. The config in the section will be applied to notifier object. Currently I have written three notifier:

#### *print* notifier

A dummy notifier who output out-of-date package info to STDIN.

* **timeout** (optional, default=0)

Only packages that has been out-of-date for that much time will be output.

#### *githubissue* notifier

This notifier will submit a issue to GitHub repo when a package is out-of-date.

* **token** (optional if NVCHECKER_GITHUB_TOKEN envvar is set)

GitHub OAuth token for submit issue. If you don't want to write token here, specity it via NVCHECKER_GITHUB_TOKEN envvar also works (and latter method will apply to nvchecker as well).

* **repo** (required)

The repo that the notifier submit issue to.

#### *mail2committer* notifier

This notifier will send an Email to the last committer of out-of-date PKGBUILD. (So the PKGBUILD repository must be a git repository except when **default_receiver** is set)

* **timeout** (optional, default=0)

* **host** (optional, default="localhost")
* **port** (optional, default=0)

SMTP server, you know.

* **default_receiver**

When the script failed to get git committer's Email, send Email to this address.

* **sender** (required)

Use this address to send Email.


### pkg:*regex* section

The config will be apply to any PKGBUILD match the regex. If there are many pkg:*regex* sections, they will be applied in order.

* **_lvpatch** (optional)

Patch local version read from PKGBUILD.

If the value is one line, use this line as local version (placeholder will be replaced by PKGBUILD info).

If the value is two line, the first line will be a regex to capture strings from raw local version (get from PKGBULD). The placeholder "$*N*" in the second line will be replaced by the captured strings (and other placeholder will be replaced as above).

For example, if a PKGBUILD has version **1:r12345.678-2** (*epoch:pkgver-pkgrel*), and its modify time is 2015/8/19 17:00:00. This patch:
```
_lvpatch = [^:]+:r(\d+\).\d+-[^-]+
           $1.{mtime:%Y%m%d}
```
will turn local version into **\*:12345.20150819-\***.

If not specified, use raw local version as local version.

* **_rvpatch** (optional)

Patch remote version fetched by nvchecker. Similar to _lvpatch.

* **_op** (optional)

Use what operator to judge if the PKGBUILD is out-of-date.

If set to **lt** (default), the PKGBUILD will be mark out-of-date if local version is less than remote version.

If set to **ne**, the PKGBUILD will be mark out-of-date if local and remote version dismatch.

* *other fields*

Other fields in this section will be passed to nvchecker. Please see nvchecher's documentation. Placeholder in the value will be replaced.

#### Usable place holder

As you can see, those placeholder are in fact replaced via Python's  ```str.format(**pacinfo)```. I show a example of ```pacinfo``` here:

```
{
  'local_timestamp': datetime.datetime(2015, 8, 8, 9, 11, 21),
    # Local version update timestamp
  'sources': ('aurvote',),
  'mtime': datetime.datetime(2015, 8, 8, 11, 12, 44),
    # PKGBUILD modify time, acquire by git when possible
  'packages': ('aurvote',),
  'name': 'aurvote',
    # should be the same as os.path.dirname(pacinfo['path'])
  'path': '/home/cuihao/Development/fakerepo/aurvote/PKGBUILD',
    # absolute path to the PKGBUILD
  'remote_timestamp': datetime.datetime(2015, 8, 8, 9, 11, 21)
    # Remote version update timestamp
}

```

Note that local_timestamp and remote_timestamp will be set the same if they are updated in the same session.

These timestamps are useful. For example, if you don't know how to write version patch, just use:

```
_lvpatch = {local_timestamp}
_rvpatch = {remote_timestamp}
```

## Testing

To test your version patch, create a minimal PKGBUILD repository and write a minimal config (with no notifier), then run with:

```
./main.py config.ini -vvvvvvvvvvvvvvvvvvv
```

Detailed version info will be output.
