import requests
import datetime
import re
import os
import logging
from urllib.parse import urljoin

from .lib import convert_timeout_to_second

logger = logging.getLogger(__name__)
GITHUB_API_BASE = "https://api.github.com/"


class GitHubAPIException(Exception):
    pass


class Notifier:
    def __init__(self, *args, repo, timeout="0s", saved={}, **kwargs):
        token = kwargs.get("token", None) or \
                os.environ.get("NVCHECKER_GITHUB_TOKEN", None)

        if token is None:
            raise GitHubAPIException("Need a token")

        timeout_seconds = convert_timeout_to_second(timeout)
        now = datetime.datetime.now()
        self.deadline = now - datetime.timedelta(seconds=timeout_seconds)

        self.session = requests.Session()
        self.session.headers.update({'Authorization': "token %s" % token})

        self.repo = repo
        self.record = saved.copy()

        url = urljoin(GITHUB_API_BASE, "repos/%s/issues?state=open" % repo)
        req = self.session.get(url)
        issue_list = req.json()

        if not isinstance(issue_list, list):
            raise GitHubAPIException("Failed to get issue list of %s" % repo)

        regex = re.compile("out\W*of\W*date", re.I)
        self.odtitles = []
        for issue in issue_list:
            title = issue['title']
            if regex.search(title):
                self.odtitles.append(title)

    def send(self, pac, outtime):
        if outtime > self.deadline:
            return False

        objhash = pac.info
        if self.record.get(pac.name) == objhash:
            logger.info("%r has been marked out-of-date in GitHub", pac.name)
            return False

        regex = re.compile("(\s|^)%s(\s|$)" % pac.name)
        for title in self.odtitles:
            if regex.search(title):
                logger.info("%r has been marked out-of-date in GitHub",
                            pac.name)
                return False

        url = urljoin(GITHUB_API_BASE, "repos/%s/issues" % self.repo)
        data = {
            "title": "%s is out-of-date" % pac.name,
            "body": "Local version: %s\n"
                    "Remote version: %s"
                    % (pac.local_version, pac.remote_version)}
        req = self.session.post(url, json=data)

        if "title" in req.json():
            logger.info("new issue: %r", data["title"])
            self.record[pac.name] = objhash
            return True

    def finish(self):
        return self.record
