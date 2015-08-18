import time
from .lib import convert_timeout_to_second

class Notifier:
    def __init__(self, timeout="0s", **kwargs):
        timeout = convert_timeout_to_second(timeout)
        self.yuz = int(time.time()) - int(timeout if timeout else 0)
    def send(self, pac, outtime):
        if outtime <= self.yuz:
            print("OUTDATED: %s (L: %s, R: %s)" 
                  % (pac.name, pac.local_version, pac.remote_version))
    def finish(self):
        pass
