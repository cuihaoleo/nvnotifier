import smtplib
from email.mime.multipart import MIMEMultipart
from nvnotifier import git
import logging
import time
from .lib import convert_timeout_to_second

logger = logging.getLogger(__name__)


def send_mail(host, port, sendto, sendfrom, subject, text):
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = sendfrom
    msg['To'] = sendto
    msg.preamble = text

    logger.info("Send Email to %s" % sendto)
    s = smtplib.SMTP(host, port)
    s.send_message(msg)
    s.quit()


class Notifier:
    def __init__(self, *args, timeout, sendfrom, saved={}, **kwargs):
        self.host = kwargs.get("host", "localhost")
        self.port = kwargs.get("port", 0)
        self.default_to = kwargs.get("defaultmail", None)
        self.sendfrom = sendfrom

        timeout = convert_timeout_to_second(timeout)
        self.yuz = int(time.time()) - int(timeout if timeout else 0)

        self.record = saved.copy()

    def send(self, pac, outtime):
        if outtime > self.yuz:
            return False

        objhash = pac.info
        if self.record.get(pac.name) == objhash:
            logger.info("Already sent mail to %s maintainer"
                        % pac.name)
            return False

        sendto = git.git_latest_commiter(pac.path) or self.default_to
        if sendto:
            send_mail(
                host=self.host,
                port=self.port,
                sendto=sendto,
                sendfrom=self.sendfrom,
                subject="Package %s is out-of-date" % pac.name,
                text=("Local: %s\n" % pac.local_version) +
                    ("Remote: %s" % pac.remote_version))
        else:
            logger.warning("Don't know send email to whom (%s)" % pac)
            return False

        self.record[pac.name] = objhash
        return True

    def finish(self):
        return self.record
