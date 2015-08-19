from .lib import convert_timeout_to_second
import datetime


class Notifier:
    def __init__(self, timeout="0s", **kwargs):
        timeout_seconds = convert_timeout_to_second(timeout)
        now = datetime.datetime.now()
        self.deadline = now - datetime.timedelta(seconds=timeout_seconds)

    def send(self, pac, outtime):
        if outtime <= self.deadline:
            print("OUTDATED: %s (L: %s, R: %s)"
                  % (pac.name, pac.local_version, pac.remote_version))

    def finish(self):
        pass
