import time
import requests
import re
from urllib.parse import urljoin
from requests.auth import HTTPBasicAuth
import logging
from .lib import convert_timeout_to_second

logger = logging.getLogger(__name__)
GITHUB_API_BASE="https://api.github.com/"

class GitHubAPIException(Exception):
    pass

class Notifier:
    def __init__(self, *args, repo, user, token, timeout, **kwargs):
        timeout = convert_timeout_to_second(timeout)
        self.yuz = int(time.time()) - int(timeout if timeout else 0)
        self.repo = repo
        self.auth = HTTPBasicAuth(user, token)

        url = urljoin(GITHUB_API_BASE, "repos/%s/issues?state=open" % repo)
        req = requests.get(url, auth=self.auth)
        issue_list = req.json()

        if not isinstance(issue_list, list):
            raise GitHubAPIException(issue_list)

        regex = re.compile("out\W*of\W*date", re.I)
        self.odtitles = []
        for issue in issue_list:
            title = issue['title']
            if regex.search(title):
                self.odtitles.append(title)

    def send(self, pac, outtime):
        if outtime > self.yuz:
            return False

        regex = re.compile("(\s|^)%s(\s|$)" % pac.name)
        for title in self.odtitles:
            logger.info("%s has been marked out-of-date in GitHub" % pac.name)
            if regex.search(title):
                return False

        url = urljoin(GITHUB_API_BASE, "repos/%s/issues" % self.repo)
        data = {
            "title": "%s is out-of-date" % pac.name,
            "body": "Local version: %s\n"
                    "Remote version: %s"
                    % (pac.local_version, pac.remote_version)}
        req = requests.post(url, auth=self.auth, json=data)

        if "title" in req.json():
            return True

    def finish(self):
        pass
