import logging
import datetime
import subprocess
from .lib import convert_timeout_to_second

logger = logging.getLogger(__name__)


def send_notify(title, body):
    subprocess.call(["notify-send", title, body, "--icon=face-sad"])


class Notifier:
    def __init__(self, *args, timeout="0s", **kwargs):
        timeout_seconds = convert_timeout_to_second(timeout)
        now = datetime.datetime.now()
        self.deadline = now - datetime.timedelta(seconds=timeout_seconds)

    def send(self, pac, outtime):
        if outtime > self.deadline:
            return False

        send_notify('%s is out-of-date' % pac.name,
                    'Local: %s\nRemote: %s' %
                    (pac.local_version, pac.remote_version))
        logger.debug("Notify %r via desktop notification", pac)

        return True

    def finish(self):
        pass
